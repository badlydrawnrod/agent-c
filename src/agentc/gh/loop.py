import asyncio
from asyncio import Event
import asyncio
import shutil
from typing import Dict

from copilot import CopilotClient, CopilotSession
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    ProviderConfig,
    SessionConfig,
)
from copilot.generated.session_events import SessionEvent, SessionEventType


from ..core.types import (
    AgentChunk,
    AgentDone,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolResult,
    AgentEventStream,
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
        self._event_queue = asyncio.Queue()
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
                case SessionEventType.TOOL_EXECUTION_START:
                    internal_tools = {"report_intent"}
                    if event.data.tool_name not in internal_tools:
                        yield ToolCallInfo(
                            tool_name=event.data.tool_name,
                            args=event.data.arguments,
                            tool_call_id=event.data.tool_call_id,
                        )
                case SessionEventType.TOOL_EXECUTION_COMPLETE:
                    yield ToolCallResultInfo(
                        tool_call_id=event.data.tool_call_id,
                        result=ToolResult(
                            success=event.data.success,
                            content=event.data.result,
                            error=event.data.error,
                        ),
                    )
                case SessionEventType.SESSION_IDLE:
                    yield AgentDone(history=None)  # TOOD: populate history
                    break
