# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from copilot import CopilotClient
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    SessionConfig as CopilotSessionConfig,
    SessionHooks,
    SystemMessageReplaceConfig,
)
from pydantic_ai import Agent, DeferredToolRequests, Tool
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.tools import RunContext
from tool_pipeline_backend_copilot import CopilotToolPipelineFactory
from tool_pipeline_backend_pydantic import PydanticAIToolPipelineFactory
from tool_pipeline_common import (
    AutoAllowAndRememberInteractionResponder,
    BlockedToolStage,
    InteractiveApprovalStage,
    SessionConfig,
    SessionFactoryProtocol,
    ToolPipeline,
    ToolResult,
    iter_events_with_interaction_responder,
)


@dataclass(slots=True)
class SpikeDeps:
    project_name: str = "agent-c"


def project_name_tool(ctx: RunContext[SpikeDeps]) -> ToolResult:
    return ToolResult(success=True, content=ctx.deps.project_name)


def build_pydantic_agent(
    model_name: str,
    ollama_base_url: str,
) -> Agent[SpikeDeps, str | DeferredToolRequests]:
    model = OpenAIChatModel(
        provider=OllamaProvider(base_url=ollama_base_url),
        model_name=model_name,
    )

    tools: list[Tool[SpikeDeps]] = [
        Tool(project_name_tool, takes_ctx=True, requires_approval=True)
    ]

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
    model_name: str | None,
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
            skill_directories=[str(Path.cwd() / ".github" / "skills")],
            system_message=SystemMessageReplaceConfig(
                mode="replace",
                content=(
                    "You are a coding spike agent with a backend-agnostic tool pipeline. "
                    "To answer project name questions, run a shell command like "
                    "`echo agent-c` and report the result."
                ),
            ),
        )

    factory = CopilotToolPipelineFactory(
        client=client,
        pipeline=pipeline,
        session_config_builder=build_session_config,
    )
    return factory, client


async def create_pydantic_factory(
    pipeline: ToolPipeline,
    model_name: str | None,
) -> SessionFactoryProtocol:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ensure_ollama_is_running(ollama_base_url)

    def build_agent(session_config: SessionConfig) -> Agent[SpikeDeps, str | DeferredToolRequests]:
        return build_pydantic_agent(
            model_name=model_name or session_config.model_name or "gpt-oss:20b",
            ollama_base_url=ollama_base_url,
        )

    return PydanticAIToolPipelineFactory(
        deps=SpikeDeps(project_name="agent-c"),
        pipeline=pipeline,
        agent_builder=build_agent,
    )


async def run_spike(backend: str, prompt: str, model_name: str | None) -> None:
    pipeline = build_pipeline()
    cleanup_client: CopilotClient | None = None

    try:
        if backend == "copilot":
            factory, cleanup_client = await create_copilot_factory(pipeline, model_name)
        elif backend == "pydantic":
            factory = await create_pydantic_factory(pipeline, model_name)
        else:
            raise ValueError(f"Unknown backend: {backend}")

        session = await factory.create_session(SessionConfig(model_name=model_name))
        stream = session.run(prompt)

        async for event in iter_events_with_interaction_responder(
            stream,
            AutoAllowAndRememberInteractionResponder(),
        ):
            print(event)
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
