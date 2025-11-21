import asyncio
from dataclasses import dataclass
from typing import Any

from agentc.core.runner import AgentRunner
from agentc.core.types import ApprovalRequest, LoopCallbacks


class DummyCallbacks(LoopCallbacks):
    def __init__(self):
        self.requests = []

    def on_thinking(self) -> None:
        pass

    def on_stream_chunk(self, chunk) -> None:
        pass

    def on_stream_complete(self) -> None:
        pass

    def on_status_update(self, status: str) -> None:
        pass

    def on_cancelled(self, message: str) -> None:
        pass

    async def request_approval(self, req: ApprovalRequest) -> bool:
        self.requests.append(req)
        return True


@dataclass
class _FakeCall:
    tool_name: str
    tool_call_id: str
    args: Any


class _FakeDeferred:
    def __init__(self, approvals):
        self.approvals = approvals


def test_collect_tool_approvals_calls_callbacks() -> None:
    callbacks = DummyCallbacks()

    runner = AgentRunner(None, "", [], None, callbacks=callbacks)

    fake = _FakeDeferred([_FakeCall("tool", "call-1", {"x": 1})])

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(runner._collect_tool_approvals(fake))
    finally:
        loop.close()

    # our dummy callback should have recorded the approval request
    assert len(callbacks.requests) == 1
    assert "call-1" in res.approvals


def test_pause_resume_toggle():
    runner = AgentRunner(None, "", [], None)
    # Use public `is_paused` property rather than the removed `pause_event`.
    assert not runner.is_paused
    runner.pause()
    assert runner.is_paused
    runner.resume()
    assert not runner.is_paused


def test_consoleui_loopcallbacks_accumulates_and_clears():
    # Create without running __init__ to avoid prompt_toolkit trying to access
    # the tty in test environments.
    from rich.console import Console

    from agentc.core.types import StreamChunk
    from agentc.ui.console import ConsoleUI

    ui = ConsoleUI.__new__(ConsoleUI)
    ui.personalities = {}
    ui.console = Console()
    ui.session = None
    ui.style = None
    ui._status = None
    ui._live = None
    ui._accumulated_text = ""
    # New ConsoleUI loop-callbacks expect an accumulated thinking buffer.
    ui._accumulated_thinking = ""

    # Initially empty
    assert ui._accumulated_text == ""

    # Add a chunk
    ui.on_stream_chunk(StreamChunk("hello "))
    ui.on_stream_chunk(StreamChunk("world"))
    assert ui._accumulated_text == "hello world"

    # Complete should clear accumulated text
    ui.on_stream_complete()
    assert ui._accumulated_text == ""