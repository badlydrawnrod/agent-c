import asyncio
from asyncio import Event, AbstractEventLoop
from typing import Any, Optional

from copilot import CopilotSession
from copilot.generated.session_events import SessionEvent, SessionEventType

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


class GhAgentSession(AgentSessionProtocol):
    """
    Encapsulates the state of a GitHub agentic session.

    This class keeps the history and agent implementation details opaque to the UI.
    """

    def __init__(
        self,
        session: CopilotSession,
    ):
        self._session = session
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

    def _parse_user_input_options(self, data: Any) -> list[UserInputOption]:
        raw_options = self._get_event_field(data, "options", [])
        if not isinstance(raw_options, list):
            return []
        options: list[UserInputOption] = []
        for opt in raw_options:
            if isinstance(opt, dict):
                label = opt.get("label")
                description = opt.get("description")
            else:
                label = str(opt)
                description = None
            if label:
                options.append(UserInputOption(label=str(label), description=description))
        return options

    def _build_user_input_request(self, event: SessionEvent) -> UserInputRequest:
        data = event.data
        question = self._get_event_field(data, "question", "")
        if not isinstance(question, str):
            question = str(question)
        allow_freeform = bool(self._get_event_field(data, "allow_freeform", False))
        placeholder = self._get_event_field(data, "placeholder", None)
        request_id = self._get_event_field(data, "request_id", None)
        options = self._parse_user_input_options(data)
        return UserInputRequest(
            question=question,
            options=options,
            allow_freeform=allow_freeform,
            placeholder=placeholder if isinstance(placeholder, str) else None,
            request_id=request_id if isinstance(request_id, str) else None,
        )

    async def _send_user_input_response(self, response: UserInputResponse) -> None:
        send_method = getattr(self._session, "send_user_input_response", None)
        payload = {
            "request_id": response.request_id,
            "response": response.response,
        }
        if callable(send_method):
            try:
                result = send_method(response.request_id, response.response)
            except TypeError:
                result = send_method(payload)
            if asyncio.iscoroutine(result):
                await result
            return
        await self._session.send({"user_input_response": payload})

    async def run(
        self,
        prompt: str,
        cancellation_event: Event | None = None,
    ) -> AgentEventStream:
        """Run the agentic session with the given prompt."""
        await self._session.send({"prompt": prompt})

        # Yield events from the queue until SESSION_IDLE.
        while True:
            if cancellation_event is not None and cancellation_event.is_set():
                break

            event = await self._event_queue.get()

            match event.type:
                case SessionEventType.ASSISTANT_MESSAGE_DELTA:
                    delta = event.data.delta_content or ""
                    yield AgentChunk(content=delta, is_thought=False)
                case SessionEventType.ASSISTANT_REASONING_DELTA:
                    delta = event.data.delta_content or ""
                    yield AgentChunk(content=delta, is_thought=True)
                case _ if getattr(SessionEventType, "USER_INPUT_REQUEST", None) == event.type:
                    request = self._build_user_input_request(event)
                    response: UserInputResponse | None = yield request
                    if response is None:
                        break
                    await self._send_user_input_response(response)
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
                    yield AgentDone(history=None)  # TOOD: populate history
                    break
