# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    FunctionToolResultEvent,
    Tool as PydanticTool,
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
from spike_tool_pipeline_core import (
    AgentChunk,
    AgentDone,
    AgentEventStream,
    AgentSessionProtocol,
    SessionConfig,
    SessionFactoryProtocol,
    ToolRegistry,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolPipeline,
    ToolPipelineInteractionRequest,
    ToolPipelineInteractionResponse,
    ToolResult,
)
from pydantic_ai.tools import RunContext

DepsT = TypeVar("DepsT")


PydanticAgentBuilder = Callable[[SessionConfig], Agent[DepsT, str | DeferredToolRequests]]


@dataclass(slots=True)
class PydanticBackendConfig:
    model_name: str
    ollama_base_url: str
    system_prompt: str
    ensure_ollama_available: bool = True

def build_pydantic_tools(registry: ToolRegistry[DepsT]) -> list[PydanticTool[DepsT]]:
    built_tools: list[PydanticTool[DepsT]] = []

    for tool in registry.tools:

        def _build_wrapped_tool(registered_tool):
            def _tool(ctx: RunContext[DepsT]) -> ToolResult:
                return registered_tool.handler({}, ctx.deps)

            _tool.__name__ = registered_tool.name
            return PydanticTool(
                _tool,
                takes_ctx=True,
                requires_approval=registered_tool.requires_approval,
            )

        built_tools.append(_build_wrapped_tool(tool))

    return built_tools


def build_pydantic_agent(
    backend_config: PydanticBackendConfig,
    registry: ToolRegistry[DepsT],
) -> Agent[DepsT, str | DeferredToolRequests]:
    model = OpenAIChatModel(
        provider=OllamaProvider(base_url=backend_config.ollama_base_url),
        model_name=backend_config.model_name,
    )

    tools = build_pydantic_tools(registry)

    return Agent(
        model=model,
        deps_type=object,
        output_type=str | DeferredToolRequests,
        tools=tools,
        system_prompt=backend_config.system_prompt,
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


async def create_pydantic_factory(
    pipeline: ToolPipeline,
    deps: DepsT,
    registry: ToolRegistry[DepsT],
    backend_config: PydanticBackendConfig,
) -> SessionFactoryProtocol:
    if backend_config.ensure_ollama_available:
        ensure_ollama_is_running(backend_config.ollama_base_url)

    def build_agent(session_config: SessionConfig) -> Agent[DepsT, str | DeferredToolRequests]:
        effective_model_name = session_config.model_name or backend_config.model_name
        return build_pydantic_agent(
            backend_config=PydanticBackendConfig(
                model_name=effective_model_name,
                ollama_base_url=backend_config.ollama_base_url,
                system_prompt=backend_config.system_prompt,
                ensure_ollama_available=backend_config.ensure_ollama_available,
            ),
            registry=registry,
        )

    return PydanticAIToolPipelineFactory(
        deps=deps,
        pipeline=pipeline,
        agent_builder=build_agent,
    )


class PydanticAIToolPipelineSession(AgentSessionProtocol):
    def __init__(
        self,
        agent: Agent[DepsT, str | DeferredToolRequests],
        deps: DepsT,
        pipeline: ToolPipeline,
        history: list[object] | None = None,
    ) -> None:
        self._agent = agent
        self._deps = deps
        self._pipeline = pipeline
        self._history = history or []
        self._run_active = False
        self._tool_calls_by_id: dict[str, ToolCallInfo] = {}

    @property
    def history(self) -> tuple[object, ...]:
        return tuple(self._history)

    def _map_chunk(self, event: object) -> AgentChunk | None:
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

    def _map_tool_call(self, event: object) -> ToolCallInfo | None:
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

    async def _map_tool_result(self, event: object) -> ToolCallResultInfo | None:
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
                                request = self._pipeline.build_interaction_request(
                                    calls_requiring_authority[0],
                                    {"source": "pydantic_ai"},
                                )
                                if len(calls_requiring_authority) > 1:
                                    request = ToolPipelineInteractionRequest(
                                        request_id=request.request_id,
                                        stage=request.stage,
                                        tool_calls=calls_requiring_authority,
                                        context=request.context,
                                    )
                                response = yield request
                                if response is None:
                                    return
                                if not isinstance(response, ToolPipelineInteractionResponse):
                                    raise TypeError(
                                        "Expected ToolPipelineInteractionResponse for ToolPipelineInteractionRequest."
                                    )
                                if response.request_id != request.request_id:
                                    raise ValueError(
                                        "Interaction response request_id does not match request."
                                    )

                                for tool_call_info in calls_requiring_authority:
                                    decision = self._pipeline.resolve_interaction_response(
                                        tool_call_info,
                                        response,
                                    )
                                    approval_results.approvals[tool_call_info.tool_call_id] = (
                                        True
                                        if decision.kind == "allow"
                                        else ToolDenied(
                                            decision.reason
                                            or "Denied by pipeline authority."
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
    def __init__(
        self,
        deps: DepsT,
        pipeline: ToolPipeline,
        agent_builder: PydanticAgentBuilder,
    ) -> None:
        self._deps = deps
        self._pipeline = pipeline
        self._agent_builder = agent_builder

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        agent = self._agent_builder(config)
        return PydanticAIToolPipelineSession(
            agent=agent,
            deps=self._deps,
            pipeline=self._pipeline,
        )
