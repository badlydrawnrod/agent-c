"""Adapter bridging the agentic event stream to console events.

Applies optional debouncing, translates agnostic events into
console-specific event dataclasses, and manages tool approval
handshakes required by the UI. This adapter uses a callback-based
approach suitable for console applications.
"""

import asyncio
from collections.abc import Awaitable, Callable

from ..core.types import (
    AgentChunk,
    AgentDone as AgentDoneEvent,
    AgentEventStream,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    RunDeps,
    ToolCallInfo,
    ToolCallResultInfo,
)
from ..middleware.debouncing import DebouncingMiddleware
from .console_messages import (
    ConsoleApprovalRequestEvent,
    ConsoleCancelledEvent,
    ConsoleDoneEvent,
    ConsoleErrorEvent,
    ConsoleEvent,
    ConsoleTextEvent,
    ConsoleThinkingEvent,
    ConsoleToolCallEvent,
    ConsoleToolResultEvent,
)


# Type aliases for callback functions
type EventCallback = Callable[[ConsoleEvent], None]
type ApprovalCallback = Callable[[ConsoleApprovalRequestEvent], Awaitable[ApprovalResponse]]


class ConsoleAgentAdapter:
    """Adapts the agentic event stream to console events via callbacks.

    This adapter translates `AgentEvent` objects from the core loop into
    console-specific event dataclasses. It uses a callback-based pattern
    suitable for console applications, where events are dispatched via
    a synchronous callback and approval requests use an async callback
    that returns the user's decision.
    """

    def __init__(
        self,
        session: AgentSessionProtocol,
        prompt: str,
        on_event: EventCallback,
        on_approval: ApprovalCallback,
        cancellation_event: asyncio.Event | None = None,
        debounce_threshold: int = 40,
    ) -> None:
        """Initialize the console adapter.

        Args:
            session: The agent session implementing `AgentSessionProtocol`.
            prompt: The user prompt to send to the agent.
            on_event: Callback invoked for each console event (text, thinking, etc.).
            on_approval: Async callback invoked when approval is needed.
                         Must return an `ApprovalResponse`.
            cancellation_event: Optional event to signal cancellation.
            debounce_threshold: Threshold for debouncing text deltas.
        """
        self._session = session
        self._prompt = prompt
        self._on_event = on_event
        self._on_approval = on_approval
        self._cancellation_event = cancellation_event
        self._debounce_threshold = debounce_threshold

    def _is_cancelled(self) -> bool:
        """Check if the operation has been cancelled."""
        if isinstance(self._cancellation_event, asyncio.Event):
            return self._cancellation_event.is_set()
        return bool(self._cancellation_event)

    def _get_event_stream(self) -> AgentEventStream:
        """Create the debounced event stream from the session."""
        raw_events = self._session.run(
            prompt=self._prompt,
            cancellation_event=self._cancellation_event,
        )
        middleware = DebouncingMiddleware(threshold=self._debounce_threshold)
        return middleware.process(raw_events)

    async def run(self) -> None:
        """Run the adapter loop, dispatching events via callbacks."""
        try:
            events = self._get_event_stream()
            response: ApprovalResponse | None = None

            while True:
                if self._is_cancelled():
                    self._on_event(ConsoleCancelledEvent())
                    return

                try:
                    event = await events.asend(response)
                    response = None

                    match event:
                        case AgentChunk(content=text, is_thought=True):
                            self._on_event(ConsoleThinkingEvent(text))

                        case AgentChunk(content=text, is_thought=False):
                            self._on_event(ConsoleTextEvent(text))

                        case ToolCallInfo(
                            tool_call_id=id, tool_name=name, args=args
                        ):
                            self._on_event(ConsoleToolCallEvent(id, name, args))

                        case ToolCallResultInfo(tool_call_id=id, result=result):
                            self._on_event(ConsoleToolResultEvent(id, result))

                        case ApprovalRequest() as request:
                            response = await self._handle_approval_request(request)

                        case AgentDoneEvent(history=history):
                            self._on_event(ConsoleDoneEvent(history))
                            return

                except StopAsyncIteration:
                    return

        except Exception as exc:  # noqa: BLE001
            self._on_event(ConsoleErrorEvent(str(exc)))

    async def _handle_approval_request(
        self, request: ApprovalRequest
    ) -> ApprovalResponse:
        """Invoke the approval callback and return the user's decision."""
        console_event = ConsoleApprovalRequestEvent(request.tool_calls)
        return await self._on_approval(console_event)
