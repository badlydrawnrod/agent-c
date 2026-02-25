# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from pydantic_core import to_jsonable_python
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
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
class AgentChunk:
    content: str
    is_thought: bool = False


@dataclass(slots=True)
class ToolCallInfo:
    tool_name: str
    args: Mapping[str, Any]
    tool_call_id: str


@dataclass(slots=True)
class ToolResult:
    success: bool
    content: str
    error: str | None = None


@dataclass(slots=True)
class ToolCallResultInfo:
    tool_call_id: str
    result: ToolResult


@dataclass(slots=True)
class AgentDone:
    pass


@dataclass(slots=True)
class InteractionRequest:
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(slots=True)
class InteractionResponse:
    request_id: str


@dataclass(slots=True)
class ApprovalRequest(InteractionRequest):
    tool_calls: list[ToolCallInfo] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalResponse(InteractionResponse):
    approved: bool
    reason: str | None = None


class ApprovalAuthority(Protocol):
    async def decide(self, request: ApprovalRequest) -> ApprovalResponse:
        ...


class AutoApproveAuthority:
    async def decide(self, request: ApprovalRequest) -> ApprovalResponse:
        return ApprovalResponse(request_id=request.request_id, approved=True)


AgentEvent: TypeAlias = (
    AgentChunk | ToolCallInfo | ToolCallResultInfo | InteractionRequest | AgentDone
)
AgentEventStream: TypeAlias = AsyncGenerator[AgentEvent, InteractionResponse | None]


async def iter_events_with_approval_authority(
    stream: AgentEventStream,
    approval_authority: ApprovalAuthority,
) -> AsyncGenerator[AgentEvent, None]:
    pending_response: InteractionResponse | None = None

    while True:
        try:
            if pending_response is None:
                event = await anext(stream)
            else:
                event = await stream.asend(pending_response)
        except StopAsyncIteration:
            return

        pending_response = None

        if isinstance(event, ApprovalRequest):
            pending_response = await approval_authority.decide(event)
            continue

        yield event


@dataclass(slots=True)
class SessionConfig:
    model_name: str | None = None
    initial_history: Sequence[Any] | None = None


class AgentSessionProtocol(Protocol):
    @property
    def history(self) -> Sequence[Any]:
        ...

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        ...


class SessionFactoryProtocol(Protocol):
    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        ...


@dataclass(slots=True)
class SpikeDeps:
    project_name: str = "agent-c"


def project_name_tool(ctx: RunContext[SpikeDeps]) -> ToolResult:
    return ToolResult(success=True, content=ctx.deps.project_name)


class NativeMessageHistoryStore:
    """Persist Pydantic AI native message history as JSON on disk."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, messages: Sequence[Any]) -> None:
        as_jsonable = to_jsonable_python(messages)
        self._file_path.write_text(
            json.dumps(as_jsonable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self) -> list[Any]:
        if not self._file_path.exists():
            return []

        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        loaded = ModelMessagesTypeAdapter.validate_python(payload)
        return list(loaded)


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
            "You are a spike backend. Use the project_name_tool to answer questions "
            "about the project name."
        ),
    )


class PydanticAICoreSession(AgentSessionProtocol):
    def __init__(
        self,
        agent: Agent[SpikeDeps, str | DeferredToolRequests],
        deps: SpikeDeps,
        history: Sequence[Any] | None = None,
    ) -> None:
        self._agent = agent
        self._deps = deps
        self._history = list(history or [])
        self._run_active = False

    @property
    def history(self) -> Sequence[Any]:
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
                return ToolCallInfo(
                    tool_name=name,
                    args=mapped_args,
                    tool_call_id=call_id or "unknown",
                )
        return None

    def _map_tool_result(self, event: Any) -> ToolCallResultInfo | None:
        if not isinstance(event, FunctionToolResultEvent):
            return None
        if not isinstance(event.result, ToolReturnPart):
            return None

        content = event.result.content
        if isinstance(content, ToolResult):
            result = content
        else:
            result = ToolResult(success=True, content=str(content), error=None)

        return ToolCallResultInfo(tool_call_id=event.result.tool_call_id, result=result)

    def _build_approval_request(
        self,
        deferred: DeferredToolRequests,
    ) -> ApprovalRequest:
        return ApprovalRequest(
            tool_calls=[
                ToolCallInfo(
                    tool_name=call.tool_name,
                    args=call.args if isinstance(call.args, Mapping) else {},
                    tool_call_id=call.tool_call_id,
                )
                for call in deferred.approvals
            ]
        )

    def _build_deferred_results(
        self,
        deferred: DeferredToolRequests,
        response: ApprovalResponse,
    ) -> DeferredToolResults:
        results = DeferredToolResults()
        for call in deferred.approvals:
            results.approvals[call.tool_call_id] = (
                response.approved
                if response.approved
                else ToolDenied(
                    response.reason
                    or "Denied by approval authority. Do not retry without new approval."
                )
            )
        return results

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

                    tool_result = self._map_tool_result(event)
                    if tool_result is not None:
                        yield tool_result
                        continue

                    if isinstance(event, AgentRunResultEvent):
                        self._history = list(event.result.all_messages())

                        if isinstance(event.result.output, DeferredToolRequests):
                            request = self._build_approval_request(event.result.output)
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

                            approval_results = self._build_deferred_results(
                                event.result.output,
                                response,
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


class PydanticAISpikeFactory(SessionFactoryProtocol):
    def __init__(self, deps: SpikeDeps) -> None:
        self._deps = deps

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        model_name = config.model_name or "gpt-oss:20b"
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        agent = build_pydantic_agent(model_name, ollama_base_url)
        return PydanticAICoreSession(
            agent=agent,
            deps=self._deps,
            history=config.initial_history,
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


async def run_and_print(
    session: AgentSessionProtocol,
    prompt: str,
    approval_authority: ApprovalAuthority,
    label: str,
) -> None:
    stream = session.run(prompt)
    async for event in iter_events_with_approval_authority(stream, approval_authority):
        print(f"[{label}] {event}")


async def demo_native_history_resume() -> None:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ensure_ollama_is_running(ollama_base_url)

    history_file = Path(
        os.getenv(
            "SPIKE_NATIVE_HISTORY_FILE",
            "docs/spikes/pydantic_native_history.json",
        )
    )
    first_prompt = os.getenv("SPIKE_FIRST_PROMPT", "What is the project name?")
    second_prompt = os.getenv(
        "SPIKE_SECOND_PROMPT",
        "Great. Remind me what project we are discussing.",
    )

    approval_authority: ApprovalAuthority = AutoApproveAuthority()
    store = NativeMessageHistoryStore(history_file)
    factory = PydanticAISpikeFactory(deps=SpikeDeps(project_name="agent-c"))

    session_1 = await factory.create_session(SessionConfig())
    await run_and_print(session_1, first_prompt, approval_authority, label="run1")

    store.save(session_1.history)
    print(f"[persist] Saved {len(session_1.history)} native messages to {history_file}")

    del session_1

    loaded_history = store.load()
    print(f"[resume] Loaded {len(loaded_history)} native messages from {history_file}")

    session_2 = await factory.create_session(
        SessionConfig(initial_history=loaded_history)
    )
    await run_and_print(session_2, second_prompt, approval_authority, label="run2")


if __name__ == "__main__":
    try:
        asyncio.run(demo_native_history_resume())
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
