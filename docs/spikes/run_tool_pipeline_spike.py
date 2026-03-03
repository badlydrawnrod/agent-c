# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Protocol

from tool_pipeline_backend_copilot import CopilotBackendConfig, create_copilot_factory
from tool_pipeline_backend_pydantic import PydanticBackendConfig, create_pydantic_factory
from tool_pipeline_common import (
    AutoAllowAndRememberInteractionResponder,
    BlockedToolStage,
    InteractiveApprovalStage,
    RegisteredTool,
    SessionConfig,
    ToolCallResultInfo,
    ToolRegistry,
    ToolPipeline,
    ToolResult,
    iter_events_with_interaction_responder,
)


@dataclass(slots=True)
class SpikeDeps:
    project_name: str = "agent-c"


class AsyncStoppable(Protocol):
    async def stop(self) -> None:
        ...


def project_name_tool(args: Mapping[str, object], deps: SpikeDeps) -> ToolResult:
    override_name = args.get("project_name")
    if isinstance(override_name, str) and override_name.strip():
        return ToolResult(success=True, content=override_name.strip())
    return ToolResult(success=True, content=deps.project_name)


def report_intent_tool(args: Mapping[str, object], deps: SpikeDeps) -> ToolResult:
    del deps
    intent = args.get("intent")
    if isinstance(intent, str) and intent.strip():
        return ToolResult(success=True, content=f"Intent acknowledged: {intent.strip()}")
    return ToolResult(success=True, content="Intent acknowledged.")


def build_tool_registry() -> ToolRegistry[SpikeDeps]:
    registry = ToolRegistry[SpikeDeps]()
    registry.register(
        RegisteredTool[SpikeDeps](
            name="report_intent",
            description="Report your current intent before taking tool actions.",
            handler=report_intent_tool,
            parameters={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Short description of planned action.",
                    }
                },
                "additionalProperties": False,
            },
            requires_approval=False,
        )
    )
    registry.register(
        RegisteredTool[SpikeDeps](
            name="project_name_tool",
            description="Return the current project name.",
            handler=project_name_tool,
            parameters={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Optional project name override for testing.",
                    }
                },
                "additionalProperties": False,
            },
            requires_approval=True,
        )
    )
    return registry


def build_pipeline() -> ToolPipeline:
    return ToolPipeline(
        stages=[
            BlockedToolStage(blocked_tools={"dangerous_tool"}),
            InteractiveApprovalStage(auto_allow_tools={"report_intent"}),
        ]
    )


def ensure_copilot_cli_available() -> str:
    cli_path = shutil.which("copilot")
    if not cli_path:
        raise RuntimeError(
            "GitHub Copilot CLI was not found in PATH. Install it and sign in first."
        )
    return cli_path


def build_copilot_backend_config(enable_post_hook_mutation: bool) -> CopilotBackendConfig:
    return CopilotBackendConfig(
        cli_path=ensure_copilot_cli_available(),
        model_name="gpt-5 mini",
        system_message=(
            "You are a coding spike agent with a backend-agnostic tool pipeline. "
            "To answer project name questions, call `project_name_tool` and report the result."
        ),
        skill_directories=(str(Path.cwd() / ".github" / "skills"),),
        enable_post_hook_mutation=enable_post_hook_mutation,
    )


def build_pydantic_backend_config() -> PydanticBackendConfig:
    return PydanticBackendConfig(
        model_name="gpt-oss:20b",
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        system_prompt=(
            "You are a spike backend with a backend-agnostic tool pipeline. "
            "Use project_name_tool to answer project-name questions."
        ),
        ensure_ollama_available=True,
    )


async def run_spike(backend: str, prompt: str, model_name: str | None) -> None:
    pipeline = build_pipeline()
    deps = SpikeDeps(project_name="agent-c")
    registry = build_tool_registry()
    max_events = int(os.getenv("SPIKE_MAX_EVENTS", "0") or "0")
    max_seconds = float(os.getenv("SPIKE_MAX_SECONDS", "0") or "0")
    fail_fast_tool_failure = os.getenv("SPIKE_FAIL_FAST_TOOL_FAILURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    cleanup_client: AsyncStoppable | None = None

    try:
        if backend == "copilot":
            debug_copilot = os.getenv("SPIKE_DEBUG_COPILOT", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            enable_post_hook_mutation = os.getenv(
                "SPIKE_ENABLE_COPILOT_POST_HOOK_MUTATION",
                "",
            ).strip().lower() in {"1", "true", "yes", "on"}
            copilot_backend_config = build_copilot_backend_config(
                enable_post_hook_mutation=enable_post_hook_mutation,
            )

            diagnostic_logger = None
            if debug_copilot:

                def _logger(message: str) -> None:
                    print(f"[copilot-debug] {message}", file=sys.stderr)

                diagnostic_logger = _logger

            factory, cleanup_client = await create_copilot_factory(
                pipeline,
                deps,
                registry,
                backend_config=copilot_backend_config,
                diagnostic_logger=diagnostic_logger,
            )
        elif backend == "pydantic":
            pydantic_backend_config = build_pydantic_backend_config()
            factory = await create_pydantic_factory(
                pipeline,
                deps,
                registry,
                backend_config=pydantic_backend_config,
            )
        else:
            raise ValueError(f"Unknown backend: {backend}")

        session = await factory.create_session(SessionConfig(model_name=model_name))
        stream = session.run(prompt)
        event_stream = iter_events_with_interaction_responder(
            stream,
            AutoAllowAndRememberInteractionResponder(),
        )

        async def _drain_events() -> None:
            event_count = 0
            async for event in event_stream:
                print(event)
                event_count += 1
                if (
                    fail_fast_tool_failure
                    and isinstance(event, ToolCallResultInfo)
                    and not event.result.success
                ):
                    raise RuntimeError(
                        "Fail-fast: tool execution failed "
                        f"(tool_call_id={event.tool_call_id}, error={event.result.error!r}, "
                        f"content={event.result.content!r})"
                    )
                if max_events > 0 and event_count >= max_events:
                    print(
                        f"[spike] Stopping after {event_count} events due to SPIKE_MAX_EVENTS.",
                        file=sys.stderr,
                    )
                    return

        if max_seconds > 0:
            try:
                async with asyncio.timeout(max_seconds):
                    await _drain_events()
            except TimeoutError:
                print(
                    f"[spike] Stopping after {max_seconds:.1f}s due to SPIKE_MAX_SECONDS.",
                    file=sys.stderr,
                )
        else:
            await _drain_events()
    finally:
        if cleanup_client is not None:
            await cleanup_client.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backend-agnostic tool-pipeline spike with selectable backend."
    )
    parser.add_argument(
        "--backend",
        choices=["copilot", "pydantic"],
        required=True,
        help="Backend implementation to run.",
    )
    parser.add_argument(
        "--prompt",
        default="What is the project name? Use a tool if needed and then answer.",
        help="Prompt to send to the selected backend.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional backend model override.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(run_spike(args.backend, args.prompt, args.model))
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
    except StopAsyncIteration:
        pass
