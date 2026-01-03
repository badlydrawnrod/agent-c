"""Tests for the ConsoleAgentAdapter.

Tests that the console adapter correctly maps AgentEvent objects to
console-specific event types and handles the approval handshake.
"""

import asyncio
from unittest.mock import MagicMock

from agentc.adapters.console import ConsoleAgentAdapter
from agentc.adapters.console_messages import (
    ConsoleApprovalRequestEvent,
    ConsoleDoneEvent,
    ConsoleErrorEvent,
    ConsoleTextEvent,
    ConsoleThinkingEvent,
    ConsoleToolCallEvent,
    ConsoleToolResultEvent,
)
from agentc.core.types import (
    AgentChunk,
    AgentDone as AgentDoneEvent,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolResult,
)


async def _test_console_adapter_run():
    """Test that ConsoleAgentAdapter dispatches text and done events."""
    session = MagicMock(spec=AgentSessionProtocol)
    received_events: list = []

    async def mock_run(*args, **kwargs):
        yield AgentChunk(content="Hello", is_thought=False)
        yield AgentDoneEvent(history=["msg1"])

    session.run = mock_run

    def on_event(event):
        received_events.append(event)

    async def on_approval(event):
        return ApprovalResponse(approved=True)

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt="test",
        on_event=on_event,
        on_approval=on_approval,
    )
    await adapter.run()

    # Verify events received
    assert len(received_events) == 2

    # First event: ConsoleTextEvent with content
    first_event = received_events[0]
    assert isinstance(first_event, ConsoleTextEvent)
    assert first_event.text == "Hello"

    # Second event: ConsoleDoneEvent with history
    second_event = received_events[1]
    assert isinstance(second_event, ConsoleDoneEvent)
    assert second_event.history == ["msg1"]


def test_console_adapter_run():
    asyncio.run(_test_console_adapter_run())


async def _test_console_adapter_thinking():
    """Test that ConsoleAgentAdapter dispatches thinking events."""
    session = MagicMock(spec=AgentSessionProtocol)
    received_events: list = []

    async def mock_run(*args, **kwargs):
        yield AgentChunk(content="Thinking...", is_thought=True)
        yield AgentDoneEvent(history=[])

    session.run = mock_run

    def on_event(event):
        received_events.append(event)

    async def on_approval(event):
        return ApprovalResponse(approved=True)

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt="test",
        on_event=on_event,
        on_approval=on_approval,
    )
    await adapter.run()

    # First event should be thinking
    assert len(received_events) == 2
    assert isinstance(received_events[0], ConsoleThinkingEvent)
    assert received_events[0].text == "Thinking..."


def test_console_adapter_thinking():
    asyncio.run(_test_console_adapter_thinking())


async def _test_console_adapter_approval():
    """Test that ConsoleAgentAdapter handles approval requests correctly."""
    session = MagicMock(spec=AgentSessionProtocol)
    received_events: list = []
    approval_events: list = []

    async def mock_run(*args, **kwargs):
        # Yield ApprovalRequest
        tool_call = ToolCallInfo(tool_name="test_tool", args={"arg": "value"}, tool_call_id="call1")
        resp = yield ApprovalRequest(tool_calls=[tool_call])
        assert resp.approved is True
        assert resp.reason == "Approved by test"
        yield AgentChunk(content="Done", is_thought=False)
        yield AgentDoneEvent(history=[])

    session.run = mock_run

    def on_event(event):
        received_events.append(event)

    async def on_approval(event):
        approval_events.append(event)
        return ApprovalResponse(approved=True, reason="Approved by test")

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt="test",
        on_event=on_event,
        on_approval=on_approval,
    )
    await adapter.run()

    # Verify approval callback was called
    assert len(approval_events) == 1
    approval_event = approval_events[0]
    assert isinstance(approval_event, ConsoleApprovalRequestEvent)
    assert len(approval_event.tool_calls) == 1
    assert approval_event.tool_calls[0].tool_name == "test_tool"


def test_console_adapter_approval():
    asyncio.run(_test_console_adapter_approval())


async def _test_console_adapter_tool_call():
    """Test that ConsoleAgentAdapter maps ToolCallInfo to ConsoleToolCallEvent."""
    session = MagicMock(spec=AgentSessionProtocol)
    received_events: list = []

    async def mock_run(*args, **kwargs):
        yield ToolCallInfo(tool_call_id="call1", tool_name="read_file", args={"path": "/tmp/test.txt"})
        yield AgentDoneEvent(history=[])

    session.run = mock_run

    def on_event(event):
        received_events.append(event)

    async def on_approval(event):
        return ApprovalResponse(approved=True)

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt="test",
        on_event=on_event,
        on_approval=on_approval,
    )
    await adapter.run()

    # Verify tool call event
    tool_call_events = [e for e in received_events if isinstance(e, ConsoleToolCallEvent)]
    assert len(tool_call_events) == 1
    assert tool_call_events[0].tool_call_id == "call1"
    assert tool_call_events[0].tool_name == "read_file"
    assert tool_call_events[0].args == {"path": "/tmp/test.txt"}


def test_console_adapter_tool_call():
    asyncio.run(_test_console_adapter_tool_call())


async def _test_console_adapter_tool_result():
    """Test that ConsoleAgentAdapter maps ToolCallResultInfo to ConsoleToolResultEvent."""
    session = MagicMock(spec=AgentSessionProtocol)
    received_events: list = []

    async def mock_run(*args, **kwargs):
        tool_result = ToolResult(success=True, content="Tool output")
        yield ToolCallResultInfo(tool_call_id="call1", result=tool_result)
        yield AgentDoneEvent(history=[])

    session.run = mock_run

    def on_event(event):
        received_events.append(event)

    async def on_approval(event):
        return ApprovalResponse(approved=True)

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt="test",
        on_event=on_event,
        on_approval=on_approval,
    )
    await adapter.run()

    # Verify tool result event
    tool_result_events = [e for e in received_events if isinstance(e, ConsoleToolResultEvent)]
    assert len(tool_result_events) == 1
    assert tool_result_events[0].tool_call_id == "call1"
    assert tool_result_events[0].result.success is True
    assert tool_result_events[0].result.content == "Tool output"


def test_console_adapter_tool_result():
    asyncio.run(_test_console_adapter_tool_result())


async def _test_console_adapter_error():
    """Test that ConsoleAgentAdapter dispatches error events on exception."""
    session = MagicMock(spec=AgentSessionProtocol)
    received_events: list = []

    async def mock_run(*args, **kwargs):
        yield AgentChunk(content="Starting", is_thought=False)
        raise ValueError("Test error")

    session.run = mock_run

    def on_event(event):
        received_events.append(event)

    async def on_approval(event):
        return ApprovalResponse(approved=True)

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt="test",
        on_event=on_event,
        on_approval=on_approval,
    )
    await adapter.run()

    # Verify error event was dispatched
    error_events = [e for e in received_events if isinstance(e, ConsoleErrorEvent)]
    assert len(error_events) == 1
    assert "Test error" in error_events[0].error


def test_console_adapter_error():
    asyncio.run(_test_console_adapter_error())
