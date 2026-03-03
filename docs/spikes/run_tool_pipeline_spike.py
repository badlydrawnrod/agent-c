# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from collections.abc import Mapping

from copilot import CopilotClient
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    SessionConfig as CopilotSessionConfig,
    SessionHooks,
    SystemMessageReplaceConfig,
    Tool as CopilotTool,
    ToolInvocation,
    ToolResult as CopilotToolResult,
)
from pydantic_ai import Agent, DeferredToolRequests, Tool as PydanticTool
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.tools import RunContext
from tool_pipeline_backend_copilot import CopilotToolPipelineFactory
from tool_pipeline_backend_pydantic import PydanticAIToolPipelineFactory
from tool_pipeline_common import (
    AutoAllowAndRememberInteractionResponder,
    BlockedToolStage,
    InteractiveApprovalStage,
    RegisteredTool,
    SessionConfig,
    SessionFactoryProtocol,
    ToolCallResultInfo,
    ToolRegistry,
    ToolPipeline,
    ToolResult,
    iter_events_with_interaction_responder,
)


@dataclass(slots=True)
class SpikeDeps:
    project_name: str = "agent-c"


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


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
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
        RegisteredTool(
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


def _to_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def build_pydantic_tools(registry: ToolRegistry) -> list[PydanticTool[SpikeDeps]]:
    built_tools: list[PydanticTool[SpikeDeps]] = []

    for tool in registry.tools:
        def _build_wrapped_tool(registered_tool: RegisteredTool) -> PydanticTool[SpikeDeps]:
            def _tool(ctx: RunContext[SpikeDeps]) -> ToolResult:
                return registered_tool.handler({}, ctx.deps)

            _tool.__name__ = registered_tool.name
            return PydanticTool(
                _tool,
                takes_ctx=True,
                requires_approval=registered_tool.requires_approval,
            )

        built_tools.append(_build_wrapped_tool(tool))

    return built_tools


def build_copilot_tools(
    registry: ToolRegistry,
    deps: SpikeDeps,
) -> list[CopilotTool]:
    built_tools: list[CopilotTool] = []

    for tool in registry.tools:
        def _build_handler(registered_tool: RegisteredTool):
            def _handler(invocation: ToolInvocation) -> CopilotToolResult:
                arguments = _to_mapping(invocation.get("arguments"))
                result = registered_tool.handler(arguments, deps)
                payload: CopilotToolResult = {
                    "resultType": "success" if result.success else "failure",
                    "textResultForLlm": result.content,
                }
                if result.error:
                    payload["error"] = result.error
                return payload

            return _handler

        built_tools.append(
            CopilotTool(
                name=tool.name,
                description=tool.description,
                handler=_build_handler(tool),
                parameters=dict(tool.parameters),
            )
        )

    return built_tools


def build_pydantic_agent(
    model_name: str,
    ollama_base_url: str,
    registry: ToolRegistry,
) -> Agent[SpikeDeps, str | DeferredToolRequests]:
    model = OpenAIChatModel(
        provider=OllamaProvider(base_url=ollama_base_url),
        model_name=model_name,
    )

    tools = build_pydantic_tools(registry)

    return Agent(
        model=model,
        deps_type=SpikeDeps,
        output_type=str | DeferredToolRequests,
        tools=tools,
        system_prompt=(
            "You are a spike backend with a backend-agnostic tool pipeline. "
            "Use project_name_tool to answer project-name questions."
        ),
    )


def _ollama_health_url(ollama_base_url: str) -> str:
    split = urlsplit(ollama_base_url)
    return f"{split.scheme}://{split.netloc}/api/tags"


def ensure_ollama_is_running(ollama_base_url: str) -> None:
    health_url = _ollama_health_url(ollama_base_url)
    try:
        with urlopen(health_url, timeout=2.0) as response:
            if response.status >= 400:
                raise URLError(f"HTTP {response.status}")
    except Exception as exc:
        raise RuntimeError(
            "Could not reach Ollama. Please start Ollama first (for example: `ollama serve`) "
            f"and ensure model `gpt-oss:20b` is available (`ollama pull gpt-oss:20b`). "
            f"Tried endpoint: {health_url}"
        ) from exc


def ensure_copilot_cli_available() -> str:
    cli_path = shutil.which("copilot")
    if not cli_path:
        raise RuntimeError(
            "GitHub Copilot CLI was not found in PATH. Install it and sign in first."
        )
    return cli_path


async def _always_approve_permission_request(
    permission_request: PermissionRequest,
    args: dict[str, str],
) -> PermissionRequestResult:
    del permission_request
    del args
    return PermissionRequestResult(kind="approved")


def build_pipeline() -> ToolPipeline:
    return ToolPipeline(
        stages=[
            BlockedToolStage(blocked_tools={"dangerous_tool"}),
            InteractiveApprovalStage(),
        ]
    )


async def create_copilot_factory(
    pipeline: ToolPipeline,
    deps: SpikeDeps,
    registry: ToolRegistry,
    model_name: str | None,
    debug_copilot: bool = False,
) -> tuple[SessionFactoryProtocol, CopilotClient]:
    cli_path = ensure_copilot_cli_available()
    client = CopilotClient({"cli_path": cli_path})
    await client.start()

    def build_session_config(
        session_config: SessionConfig,
        hooks: SessionHooks,
    ) -> CopilotSessionConfig:
        return CopilotSessionConfig(
            model=model_name or session_config.model_name or "gpt-5 mini",
            streaming=True,
            on_permission_request=_always_approve_permission_request,
            hooks=hooks,
            tools=build_copilot_tools(registry, deps),
            skill_directories=[str(Path.cwd() / ".github" / "skills")],
            system_message=SystemMessageReplaceConfig(
                mode="replace",
                content=(
                    "You are a coding spike agent with a backend-agnostic tool pipeline. "
                    "To answer project name questions, call `project_name_tool` and report the result."
                ),
            ),
        )

    diagnostic_logger = None
    if debug_copilot:
        def _logger(message: str) -> None:
            print(f"[copilot-debug] {message}", file=sys.stderr)

        diagnostic_logger = _logger

    factory = CopilotToolPipelineFactory(
        client=client,
        pipeline=pipeline,
        session_config_builder=build_session_config,
        diagnostic_logger=diagnostic_logger,
    )
    return factory, client


async def create_pydantic_factory(
    pipeline: ToolPipeline,
    deps: SpikeDeps,
    registry: ToolRegistry,
    model_name: str | None,
) -> SessionFactoryProtocol:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ensure_ollama_is_running(ollama_base_url)

    def build_agent(session_config: SessionConfig) -> Agent[SpikeDeps, str | DeferredToolRequests]:
        return build_pydantic_agent(
            model_name=model_name or session_config.model_name or "gpt-oss:20b",
            ollama_base_url=ollama_base_url,
            registry=registry,
        )

    return PydanticAIToolPipelineFactory(
        deps=deps,
        pipeline=pipeline,
        agent_builder=build_agent,
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
    cleanup_client: CopilotClient | None = None

    try:
        if backend == "copilot":
            debug_copilot = os.getenv("SPIKE_DEBUG_COPILOT", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            factory, cleanup_client = await create_copilot_factory(
                pipeline,
                deps,
                registry,
                model_name,
                debug_copilot=debug_copilot,
            )
        elif backend == "pydantic":
            factory = await create_pydantic_factory(
                pipeline,
                deps,
                registry,
                model_name,
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
