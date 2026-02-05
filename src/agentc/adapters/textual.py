"""Adapter bridging the agentic event stream to Textual messages.

Applies optional debouncing, translates agnostic events into
`textual.message.Message` subclasses, and manages tool approval
handshakes required by the UI.
"""

import asyncio

from textual.app import App

from ..core.types import (
    AgentChunk,
    AgentDone as AgentDoneEvent,
    AgentEventStream,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    ToolCallInfo,
    ToolCallResultInfo,
    UserInputRequest,
    UserInputResponse,
)
from ..middleware.debouncing import DebouncingMiddleware
from .textual_messages import (
    AgentApprovalRequestMessage,
    AgentCancelledMessage,
    AgentDoneMessage,
    AgentErrorMessage,
    AgentThinkingMessage,
    AgentTextMessage,
    AgentToolCallMessage,
    AgentToolResultMessage,
    AgentUserInputRequestMessage,
)


class TextualAgentAdapter:
    """Adapts the agentic event stream to Textual Messages."""

    def __init__(
        self,
        app: App,
        session: AgentSessionProtocol,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
        debounce_threshold: int = 1, # TODO: make configurable
    ):
        self._app = app
        self._session = session
        self._prompt = prompt
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
        """Run the adapter loop, dispatching events to the Textual app."""
        try:
            events = self._get_event_stream()
            response: ApprovalResponse | UserInputResponse | None = None

            while True:
                if self._is_cancelled():
                    self._app.post_message(AgentCancelledMessage())
                    return

                try:
                    event = await events.asend(response)
                    response = None

                    match event:
                        case AgentChunk(content=text, is_thought=True):
                            self._app.post_message(AgentThinkingMessage(text))

                        case AgentChunk(content=text, is_thought=False):
                            self._app.post_message(AgentTextMessage(text))

                        case ToolCallInfo(tool_call_id=id, tool_name=name, args=args):
                            self._app.post_message(AgentToolCallMessage(id, name, args))

                        case ToolCallResultInfo(tool_call_id=id, result=result):
                            self._app.post_message(AgentToolResultMessage(id, result))

                        case ApprovalRequest() as request:
                            response = await self._handle_approval_request(request)

                        case UserInputRequest() as request:
                            response = await self._handle_user_input_request(request)

                        case AgentDoneEvent(history=history):
                            self._app.post_message(AgentDoneMessage(history))
                            break

                except StopAsyncIteration:
                    break

        except Exception as exc:  # noqa: BLE001
            self._app.post_message(AgentErrorMessage(str(exc)))

    async def _handle_approval_request(
        self, request: ApprovalRequest
    ) -> ApprovalResponse:
        """Post an approval request to the UI and wait for the result."""
        future: asyncio.Future[tuple[bool, str | None]] = asyncio.Future()
        self._app.post_message(AgentApprovalRequestMessage(request.tool_calls, future))
        approved, reason = await future
        return ApprovalResponse(approved=approved, reason=reason)

    async def _handle_user_input_request(
        self, request: UserInputRequest
    ) -> UserInputResponse:
        """Post a user input request to the UI and wait for the response."""
        future: asyncio.Future[UserInputResponse] = asyncio.Future()
        self._app.post_message(AgentUserInputRequestMessage(request, future))
        return await future
