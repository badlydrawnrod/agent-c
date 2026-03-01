# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from minimal_tool_pipeline_common import (
    AgentChunk,
    AgentDone,
    AgentEventStream,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    AutoApproveAuthority,
    BlockedToolStage,
    RequireApprovalStage,
    ResultPrefixStage,
    SessionConfig,
    SessionFactoryProtocol,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolPipeline,
    ToolResult,
    iter_events_with_approval_authority,
)
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    FunctionToolResultEvent,
    Tool,
    ToolDenied,
)
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.tools import RunContext


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


class PydanticAIToolPipelineSession(AgentSessionProtocol):
    def __init__(
        self,
        agent: Agent[SpikeDeps, str | DeferredToolRequests],
        deps: SpikeDeps,
        pipeline: ToolPipeline,
        history: list[Any] | None = None,
    ) -> None:
        self._agent = agent
        self._deps = deps
        self._pipeline = pipeline
        self._history = history or []
        self._run_active = False
        self._tool_calls_by_id: dict[str, ToolCallInfo] = {}

    @property
    def history(self) -> tuple[Any, ...]:
        return tuple(self._history)

    def _map_chunk(self, event: Any) -> AgentChunk | None:
        match event:
            case PartStartEvent(part=TextPart(content=text)) if text:
                return AgentChunk(content=text, is_thought=False)
            case PartStartEvent(part=ThinkingPart(content=thought)) if thought:
                return AgentChunk(content=thought, is_thought=True)
            case PartDeltaEvent(delta=TextPartDelta(content_delta=text)) if text:
                return AgentChunk(content=text, is_thought=False)
            case PartDeltaEvent(
                delta=ThinkingPartDelta(content_delta=thought)
            ) if thought:
                return AgentChunk(content=thought, is_thought=True)
        return None

    def _map_tool_call(self, event: Any) -> ToolCallInfo | None:
        match event:
            case PartStartEvent(
                part=ToolCallPart(tool_name=name, args=args, tool_call_id=call_id)
            ):
                mapped_args = args if isinstance(args, Mapping) else {}
                info = ToolCallInfo(
                    tool_name=name,
                    args=mapped_args,
                    tool_call_id=call_id or "unknown",
                )
                self._tool_calls_by_id[info.tool_call_id] = info
                return info
        return None

    async def _map_tool_result(self, event: Any) -> ToolCallResultInfo | None:
        if not isinstance(event, FunctionToolResultEvent):
            return None
        if not isinstance(event.result, ToolReturnPart):
            return None

        tool_call_id = event.result.tool_call_id
        content = event.result.content
        if isinstance(content, ToolResult):
            result = content
        else:
            result = ToolResult(success=True, content=str(content), error=None)

        tool_call = self._tool_calls_by_id.get(
            tool_call_id,
            ToolCallInfo(tool_name="unknown", args={}, tool_call_id=tool_call_id),
        )
        piped_result = await self._pipeline.after_tool_use(tool_call, result)
        self._tool_calls_by_id.pop(tool_call_id, None)
        return ToolCallResultInfo(tool_call_id=tool_call_id, result=piped_result)

    async def _evaluate_deferred_approvals(
        self,
        deferred: DeferredToolRequests,
    ) -> tuple[DeferredToolResults, list[ToolCallInfo]]:
        results = DeferredToolResults()
        calls_requiring_authority: list[ToolCallInfo] = []

        for call in deferred.approvals:
            args = call.args if isinstance(call.args, Mapping) else {}
            tool_call = ToolCallInfo(
                tool_name=call.tool_name,
                args=args,
                tool_call_id=call.tool_call_id,
            )
            self._tool_calls_by_id[tool_call.tool_call_id] = tool_call
            decision = await self._pipeline.before_tool_use(tool_call)

            if decision.kind == "deny":
                results.approvals[tool_call.tool_call_id] = ToolDenied(
                    decision.reason
                    or "Denied by tool pipeline policy. Do not retry without policy change."
                )
                continue

            if decision.kind == "allow":
                results.approvals[tool_call.tool_call_id] = True
                continue

            calls_requiring_authority.append(tool_call)

        return results, calls_requiring_authority

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        return self._run_impl(prompt=prompt, cancellation_event=cancellation_event)

    async def _run_impl(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None,
    ) -> AgentEventStream:
        if self._run_active:
            raise RuntimeError("Only one active run is allowed per session.")

        self._run_active = True
        approval_results: DeferredToolResults | None = None
        current_prompt: str | None = prompt

        try:
            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    return

                should_restart = False
                async for event in self._agent.run_stream_events(
                    current_prompt,
                    message_history=self._history,
                    deferred_tool_results=approval_results,
                    deps=self._deps,
                ):
                    if cancellation_event is not None and cancellation_event.is_set():
                        return

                    chunk = self._map_chunk(event)
                    if chunk is not None:
                        yield chunk
                        continue

                    tool_call = self._map_tool_call(event)
                    if tool_call is not None:
                        yield tool_call
                        continue

                    tool_result = await self._map_tool_result(event)
                    if tool_result is not None:
                        yield tool_result
                        continue

                    if isinstance(event, AgentRunResultEvent):
                        self._history = list(event.result.all_messages())

                        if isinstance(event.result.output, DeferredToolRequests):
                            (
                                approval_results,
                                calls_requiring_authority,
                            ) = await self._evaluate_deferred_approvals(
                                event.result.output
                            )

                            if calls_requiring_authority:
                                request = ApprovalRequest(tool_calls=calls_requiring_authority)
                                response = yield request
                                if response is None:
                                    return
                                if not isinstance(response, ApprovalResponse):
                                    raise TypeError(
                                        "Expected ApprovalResponse for ApprovalRequest."
                                    )
                                if response.request_id != request.request_id:
                                    raise ValueError(
                                        "ApprovalResponse.request_id does not match request."
                                    )

                                for tool_call_info in calls_requiring_authority:
                                    approval_results.approvals[tool_call_info.tool_call_id] = (
                                        True
                                        if response.approved
                                        else ToolDenied(
                                            response.reason
                                            or "Denied by approval authority."
                                        )
                                    )

                            current_prompt = None
                            should_restart = True
                            break

                        yield AgentDone()
                        return

                if should_restart:
                    continue

                yield AgentDone()
                return
        finally:
            self._run_active = False


class PydanticAIToolPipelineFactory(SessionFactoryProtocol):
    def __init__(self, deps: SpikeDeps, pipeline: ToolPipeline) -> None:
        self._deps = deps
        self._pipeline = pipeline

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        model_name = config.model_name or "gpt-oss:20b"
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        agent = build_pydantic_agent(model_name, ollama_base_url)
        return PydanticAIToolPipelineSession(
            agent=agent,
            deps=self._deps,
            pipeline=self._pipeline,
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


async def demo_auto_approval() -> None:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ensure_ollama_is_running(ollama_base_url)

    pipeline = ToolPipeline(
        stages=[
            BlockedToolStage(blocked_tools={"dangerous_tool"}),
            RequireApprovalStage(),
            ResultPrefixStage(),
        ]
    )

    factory = PydanticAIToolPipelineFactory(
        deps=SpikeDeps(project_name="agent-c"),
        pipeline=pipeline,
    )
    session = await factory.create_session(SessionConfig())
    stream = session.run("What is the project name?")

    async for event in iter_events_with_approval_authority(
        stream,
        AutoApproveAuthority(),
    ):
        print(event)


if __name__ == "__main__":
    try:
        asyncio.run(demo_auto_approval())
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
    except StopAsyncIteration:
        pass
