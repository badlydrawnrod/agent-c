import asyncio
from asyncio import Event, AbstractEventLoop
from typing import Any, Optional, cast

from copilot import CopilotSession
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.types import (
    UserInputRequest as CopilotUserInputRequest,
    UserInputResponse as CopilotUserInputResponse,
)

from ...types import (
    AgentChunk,
    AgentDone,
    AgentSessionProtocol,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolResult,
    AgentEventStream,
    UserInputOption,
    UserInputRequest,
    UserInputResponse,
)


class GhUserInputBroker:
    """Bridge between the SDK's callback-based user input and our async generator.

    The GitHub Copilot SDK delivers user input requests via a registered
    callback (``on_user_input_request``).  This broker converts that callback
    into an item on an :class:`asyncio.Queue` so the ``GhAgentSession.run``
    loop can yield it through the event stream and receive a response.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[
            tuple[UserInputRequest, asyncio.Future[CopilotUserInputResponse]]
        ] = asyncio.Queue()

    async def handle_sdk_request(
        self,
        sdk_request: CopilotUserInputRequest,
        context: dict[str, str],
    ) -> CopilotUserInputResponse:
        """Called by the SDK on the application event loop.

        Enqueues the request for the ``run`` loop and suspends until the UI
        provides a response.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[CopilotUserInputResponse] = loop.create_future()
        our_request = _convert_sdk_request(sdk_request)
        await self._queue.put((our_request, future))
        return await future

    async def next_request(
        self,
    ) -> tuple[UserInputRequest, asyncio.Future[CopilotUserInputResponse]]:
        """Wait for the next pending user input request."""
        return await self._queue.get()


def _convert_sdk_request(sdk_request: CopilotUserInputRequest) -> UserInputRequest:
    """Map a Copilot SDK ``UserInputRequest`` to our core type."""
    question = sdk_request.get("question", "")
    choices = sdk_request.get("choices", [])
    allow_freeform = sdk_request.get("allowFreeform", True)
    options = [UserInputOption(label=choice) for choice in choices]
    return UserInputRequest(
        question=question,
        options=options,
        allow_freeform=allow_freeform,
    )


class GhAgentSession(AgentSessionProtocol):
    """
    Encapsulates the state of a GitHub agentic session.

    This class keeps the history and agent implementation details opaque to the UI.
    """

    def __init__(
        self,
        session: CopilotSession,
        user_input_broker: GhUserInputBroker | None = None,
    ):
        self._session = session
        self._user_input_broker = user_input_broker
        self._event_queue: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._loop: Optional[AbstractEventLoop]
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        def _on_event(event: SessionEvent):
            # Ensure we enqueue events on the asyncio event loop thread-safely.
            if self._loop and self._loop.is_running():
                try:
                    self._loop.call_soon_threadsafe(self._event_queue.put_nowait, event)
                except Exception:
                    # Fallback to direct put if scheduling fails.
                    try:
                        self._event_queue.put_nowait(event)
                    except Exception:
                        pass
            else:
                try:
                    self._event_queue.put_nowait(event)
                except Exception:
                    pass

        self._session.on(_on_event)

    def _on_event(self, event: SessionEvent):
        self._event_queue.put_nowait(event)

    def _get_event_field(self, data: Any, field: str, default: Any = None) -> Any:
        """Extract a field from event data supporting dicts and objects."""
        if isinstance(data, dict):
            return data.get(field, default)
        return getattr(data, field, default)

    async def run(
        self,
        prompt: str,
        cancellation_event: Event | None = None,
    ) -> AgentEventStream:
        """Run the agentic session with the given prompt.

        Monitors both the SDK event queue *and* the user-input broker (if
        present) so that ``ask_user`` tool calls from the SDK surface as
        :class:`UserInputRequest` events in the stream.
        """
        await self._session.send({"prompt": prompt})

        event_task: asyncio.Task[SessionEvent] | None = None
        request_task: asyncio.Task[
            tuple[UserInputRequest, asyncio.Future[CopilotUserInputResponse]]
        ] | None = None

        try:
            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    break

                if event_task is None:
                    event_task = asyncio.create_task(self._event_queue.get())
                if request_task is None and self._user_input_broker is not None:
                    request_task = asyncio.create_task(
                        self._user_input_broker.next_request()
                    )

                tasks: set[asyncio.Task[Any]] = {event_task}
                if request_task is not None:
                    tasks.add(request_task)

                done, _ = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )

                # --- User-input request from the SDK broker ---
                if request_task is not None and request_task in done:
                    our_request, future = request_task.result()
                    request_task = None
                    response = cast(UserInputResponse | None, (yield our_request))
                    if response is None:
                        future.set_exception(
                            RuntimeError("User cancelled input request")
                        )
                        break
                    sdk_response: CopilotUserInputResponse = {
                        "answer": response.response,
                        "wasFreeform": True,
                    }
                    future.set_result(sdk_response)
                    continue

                # --- SDK session events ---
                if event_task in done:
                    event = event_task.result()
                    event_task = None

                    match event.type:
                        case SessionEventType.ASSISTANT_MESSAGE_DELTA:
                            delta = event.data.delta_content or ""
                            yield AgentChunk(content=delta, is_thought=False)
                        case SessionEventType.ASSISTANT_REASONING_DELTA:
                            delta = event.data.delta_content or ""
                            yield AgentChunk(content=delta, is_thought=True)
                        case SessionEventType.TOOL_EXECUTION_START:
                            internal_tools = {"report_intent"}
                            if event.data.tool_name not in internal_tools:
                                yield ToolCallInfo(
                                    tool_name=event.data.tool_name or "unknown",
                                    args=event.data.arguments,
                                    tool_call_id=event.data.tool_call_id or "unknown",
                                )
                        case SessionEventType.TOOL_EXECUTION_COMPLETE:
                            yield ToolCallResultInfo(
                                tool_call_id=event.data.tool_call_id or "unknown",
                                result=ToolResult(
                                    success=event.data.success if event.data.success is not None else False,
                                    content=str(event.data.result) if event.data.result is not None else "",
                                    error=str(event.data.error) if event.data.error else None,
                                ),
                            )
                        case SessionEventType.SESSION_IDLE:
                            yield AgentDone(history=None)
                            break
        finally:
            if event_task is not None:
                event_task.cancel()
            if request_task is not None:
                request_task.cancel()
