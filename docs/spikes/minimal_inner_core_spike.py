from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeAlias, cast
from uuid import uuid4


@dataclass(slots=True)
class AgentChunk:
    """Streamed content produced by a backend."""

    content: str
    is_thought: bool = False


@dataclass(slots=True)
class ToolCallInfo:
    """A request to execute a named tool."""

    tool_name: str
    args: Mapping[str, Any]
    tool_call_id: str


@dataclass(slots=True)
class ToolResult:
    """Canonical tool execution result."""

    success: bool
    content: str
    error: str | None = None


@dataclass(slots=True)
class ToolCallResultInfo:
    """Post-tool observation event."""

    tool_call_id: str
    result: ToolResult


@dataclass(slots=True)
class AgentDone:
    """Completion signal for one turn."""


@dataclass(slots=True)
class InteractionRequest:
    """Base type for loop -> external authority requests."""

    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(slots=True)
class InteractionResponse:
    """Base type for external authority -> loop responses."""

    request_id: str


@dataclass(slots=True)
class ApprovalRequest(InteractionRequest):
    """A request for authorization before tool execution."""

    tool_calls: list[ToolCallInfo] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalResponse(InteractionResponse):
    """Authorization response for a prior approval request."""

    approved: bool
    reason: str | None = None


@dataclass(slots=True)
class UserInputOption:
    """A selectable option for user-input requests."""

    label: str
    description: str | None = None


@dataclass(slots=True)
class UserInputRequest(InteractionRequest):
    """A request for external freeform or option-based input."""

    question: str = ""
    options: list[UserInputOption] = field(default_factory=list)
    allow_freeform: bool = False
    placeholder: str | None = None


@dataclass(slots=True)
class UserInputResponse(InteractionResponse):
    """A response to a user-input request."""

    response: str


AgentEvent: TypeAlias = (
    AgentChunk
    | ToolCallInfo
    | ToolCallResultInfo
    | InteractionRequest
    | AgentDone
)

AgentEventStream: TypeAlias = AsyncGenerator[AgentEvent, InteractionResponse | None]

BackendModelEvent: TypeAlias = AgentChunk | ToolCallInfo | AgentDone


class BackendSessionProtocol(Protocol):
    """Backend contract consumed by the core loop.

    A backend receives session history and streams backend-model events.
    """

    def stream_turn(
        self,
        history: Sequence[Mapping[str, Any]],
    ) -> AsyncIterator[BackendModelEvent]:
        """Stream one model step using current history."""

        ...


ToolHandler: TypeAlias = (
    Callable[[Mapping[str, Any]], ToolResult | Awaitable[ToolResult]]
)


@dataclass(slots=True)
class RegisteredTool:
    """Tool metadata and executable binding."""

    name: str
    handler: ToolHandler
    requires_approval: bool = False


class ToolRegistry:
    """Minimal registry satisfying register/remove/resolve lifecycle."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        """Register or replace a tool binding by name."""

        self._tools[tool.name] = tool

    def remove(self, tool_name: str) -> None:
        """Disable or remove a tool binding by name."""

        self._tools.pop(tool_name, None)

    def resolve(self, tool_name: str) -> RegisteredTool | None:
        """Resolve a tool by name, if available."""

        return self._tools.get(tool_name)


@dataclass(slots=True)
class SessionConfig:
    """Pure data used to create a session."""

    model_name: str | None = None
    clear_history: bool = False


class AgentSessionProtocol(Protocol):
    """Core session protocol."""

    @property
    def history(self) -> Sequence[Mapping[str, Any]]:
        """Return read-only history for inspection."""

        ...

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        """Run one turn and stream typed events."""

        ...


class SessionFactoryProtocol(Protocol):
    """Backend-agnostic session factory protocol."""

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        """Create a session configured for a model or mode."""

        ...


class MinimalAgentSession:
    """Single-file spike implementation of the inner-core loop.

    This loop is backend-agnostic and delegates model behavior to a backend
    implementation that satisfies `BackendSessionProtocol`.
    """

    def __init__(self, backend: BackendSessionProtocol, tools: ToolRegistry) -> None:
        self._backend = backend
        self._tools = tools
        self._history: list[dict[str, Any]] = []
        self._run_active = False

    @property
    def history(self) -> Sequence[Mapping[str, Any]]:
        """Return immutable-view history."""

        return tuple(self._history)

    async def _execute_tool(self, call: ToolCallInfo) -> ToolResult:
        """Resolve and execute one tool call."""

        tool = self._tools.resolve(call.tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                content="",
                error=f"Tool '{call.tool_name}' is not registered.",
            )

        outcome = tool.handler(call.args)
        if inspect.isawaitable(outcome):
            awaited = cast(Awaitable[ToolResult], outcome)
            return await awaited

        return cast(ToolResult, outcome)

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        """Run one turn with gate + tool observation + completion invariants."""

        return self._run_impl(prompt=prompt, cancellation_event=cancellation_event)

    async def _run_impl(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None,
    ) -> AgentEventStream:
        """Internal async-generator implementation of `run`."""

        if self._run_active:
            raise RuntimeError("Only one active run is allowed per session.")

        self._run_active = True
        self._history.append({"role": "user", "content": prompt})

        try:
            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    return

                saw_tool_call = False
                saw_done = False

                async for event in self._backend.stream_turn(self._history):
                    if cancellation_event is not None and cancellation_event.is_set():
                        return

                    if isinstance(event, AgentChunk):
                        yield event
                        continue

                    if isinstance(event, ToolCallInfo):
                        saw_tool_call = True
                        yield event

                        tool = self._tools.resolve(event.tool_name)
                        approval_required = tool.requires_approval if tool else False

                        if approval_required:
                            request = ApprovalRequest(tool_calls=[event])
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

                            if not response.approved:
                                result = ToolResult(
                                    success=False,
                                    content="",
                                    error=response.reason or "Tool execution denied.",
                                )
                            else:
                                result = await self._execute_tool(event)
                        else:
                            result = await self._execute_tool(event)

                        self._history.append(
                            {
                                "role": "tool",
                                "tool_call_id": event.tool_call_id,
                                "tool_name": event.tool_name,
                                "result": {
                                    "success": result.success,
                                    "content": result.content,
                                    "error": result.error,
                                },
                            }
                        )
                        yield ToolCallResultInfo(tool_call_id=event.tool_call_id, result=result)
                        break

                    if isinstance(event, AgentDone):
                        saw_done = True
                        yield event
                        return

                if saw_done:
                    return

                if saw_tool_call:
                    continue

                yield AgentDone()
                return
        finally:
            self._run_active = False


class MinimalSessionFactory:
    """Factory that creates minimal sessions without backend assumptions."""

    def __init__(self, backend: BackendSessionProtocol, tools: ToolRegistry) -> None:
        self._backend = backend
        self._tools = tools

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        """Create a new session from pure config data."""

        _ = config
        return MinimalAgentSession(backend=self._backend, tools=self._tools)


class ScriptedDemoBackend:
    """Example backend implementing the backend protocol for demo purposes."""

    async def stream_turn(
        self,
        history: Sequence[Mapping[str, Any]],
    ) -> AsyncIterator[BackendModelEvent]:
        """Emit one tool call, then complete after tool result appears in history."""

        tool_seen = any(item.get("role") == "tool" for item in history)
        if not tool_seen:
            yield AgentChunk("Checking local clock...")
            yield ToolCallInfo(tool_name="current_time", args={}, tool_call_id="tool-1")
            return

        tool_rows = [item for item in history if item.get("role") == "tool"]
        latest = tool_rows[-1]["result"]["content"] if tool_rows else "unknown"
        yield AgentChunk(f"Tool result received: {latest}")
        yield AgentDone()


def current_time_tool(_: Mapping[str, Any]) -> ToolResult:
    """Return a simple UTC timestamp."""

    now = asyncio.get_event_loop().time()
    return ToolResult(success=True, content=f"monotonic={now:.3f}")


async def run_demo() -> None:
    """Run a tiny end-to-end spike with auto-approval authority."""

    tools = ToolRegistry()
    tools.register(
        RegisteredTool(
            name="current_time",
            handler=current_time_tool,
            requires_approval=True,
        )
    )

    factory = MinimalSessionFactory(backend=ScriptedDemoBackend(), tools=tools)
    session = await factory.create_session(SessionConfig())

    stream = session.run("What time is it?")
    event = await stream.__anext__()

    while True:
        if isinstance(event, ApprovalRequest):
            event = await stream.asend(
                ApprovalResponse(request_id=event.request_id, approved=True)
            )
            continue

        print(event)
        event = await stream.__anext__()


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except StopAsyncIteration:
        pass
