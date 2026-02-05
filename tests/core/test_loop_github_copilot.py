"""Tests for GitHub Copilot SDK GhAgentSession."""

import asyncio
from typing import Any
from unittest.mock import MagicMock, AsyncMock

import pytest

from agentc.core.backends.github_copilot.loop import GhAgentSession, GhUserInputBroker
from agentc.core.types import (
    AgentChunk,
    AgentDone,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolResult,
    UserInputRequest,
    UserInputResponse,
)


def create_mock_session_event(event_type: str, data: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock SessionEvent with the given type and data.
    
    Args:
        event_type: The SessionEventType enum value (as string).
        data: Optional event data dictionary.
        
    Returns:
        A MagicMock SessionEvent.
    """
    from copilot.generated.session_events import SessionEventType
    
    event_mock = MagicMock()
    event_mock.type = getattr(SessionEventType, event_type)
    
    data_mock = MagicMock()
    if data:
        for key, value in data.items():
            setattr(data_mock, key, value)
    event_mock.data = data_mock
    
    return event_mock


async def _test_gh_agent_session_run_text():
    """Test that GhAgentSession yields text chunks and completion event."""
    # Create mock CopilotSession
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    # Create GhAgentSession
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate events by directly putting them in the queue
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "Hello"})
    )
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": " world"})
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    # Run session and collect events
    gen = session.run("Hi")
    
    results = []
    async for event in gen:
        results.append(event)
    
    # Verify events
    assert len(results) == 3
    
    # First two should be text chunks
    assert isinstance(results[0], AgentChunk)
    assert results[0].content == "Hello"
    assert results[0].is_thought is False
    
    assert isinstance(results[1], AgentChunk)
    assert results[1].content == " world"
    assert results[1].is_thought is False
    
    # Last should be completion
    assert isinstance(results[2], AgentDone)
    assert results[2].history is None


def test_gh_agent_session_run_text():
    asyncio.run(_test_gh_agent_session_run_text())


async def _test_gh_agent_session_run_thinking():
    """Test that GhAgentSession yields thinking chunks."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate thinking/reasoning events
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_REASONING_DELTA", {"delta_content": "Let me think..."})
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    gen = session.run("Analyze this")
    
    results = []
    async for event in gen:
        results.append(event)
    
    assert len(results) == 2
    
    # First should be thinking chunk
    assert isinstance(results[0], AgentChunk)
    assert results[0].content == "Let me think..."
    assert results[0].is_thought is True
    
    # Last should be completion
    assert isinstance(results[1], AgentDone)


def test_gh_agent_session_run_thinking():
    asyncio.run(_test_gh_agent_session_run_thinking())


async def _test_gh_agent_session_run_tool_call():
    """Test that GhAgentSession detects and yields tool calls."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate tool execution start
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_START",
            {
                "tool_name": "read_file",
                "arguments": {"path": "/test/file.py"},
                "tool_call_id": "call_123",
            }
        )
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    gen = session.run("Read file")
    
    results = []
    async for event in gen:
        results.append(event)
    
    assert len(results) == 2
    
    # First should be tool call
    tool_call = results[0]
    assert isinstance(tool_call, ToolCallInfo)
    assert tool_call.tool_name == "read_file"
    assert tool_call.args == {"path": "/test/file.py"}
    assert tool_call.tool_call_id == "call_123"
    
    # Last should be completion
    assert isinstance(results[1], AgentDone)


def test_gh_agent_session_run_tool_call():
    asyncio.run(_test_gh_agent_session_run_tool_call())


async def _test_gh_agent_session_run_tool_result():
    """Test that GhAgentSession detects and yields tool results."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate tool execution complete
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_COMPLETE",
            {
                "tool_call_id": "call_123",
                "success": True,
                "result": "File contents here",
                "error": None,
            }
        )
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    gen = session.run("Execute tool")
    
    results = []
    async for event in gen:
        results.append(event)
    
    assert len(results) == 2
    
    # First should be tool result
    tool_result_info = results[0]
    assert isinstance(tool_result_info, ToolCallResultInfo)
    assert tool_result_info.tool_call_id == "call_123"
    assert isinstance(tool_result_info.result, ToolResult)
    assert tool_result_info.result.success is True
    assert tool_result_info.result.content == "File contents here"
    assert tool_result_info.result.error is None
    
    # Last should be completion
    assert isinstance(results[1], AgentDone)


def test_gh_agent_session_run_tool_result():
    asyncio.run(_test_gh_agent_session_run_tool_result())


async def _test_gh_agent_session_run_tool_error():
    """Test that GhAgentSession handles tool execution errors."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate tool execution failure
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_COMPLETE",
            {
                "tool_call_id": "call_456",
                "success": False,
                "result": None,
                "error": "File not found",
            }
        )
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    gen = session.run("Execute tool")
    
    results = []
    async for event in gen:
        results.append(event)
    
    assert len(results) == 2
    
    # First should be tool result with error
    tool_result_info = results[0]
    assert isinstance(tool_result_info, ToolCallResultInfo)
    assert tool_result_info.result.success is False
    assert tool_result_info.result.error == "File not found"


def test_gh_agent_session_run_tool_error():
    asyncio.run(_test_gh_agent_session_run_tool_error())


async def _test_gh_agent_session_filters_internal_tools():
    """Test that GhAgentSession filters internal tools like report_intent."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate internal tool call (should be filtered)
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_START",
            {
                "tool_name": "report_intent",
                "arguments": {"intent": "reading file"},
                "tool_call_id": "call_internal",
            }
        )
    )
    # Simulate regular tool call (should be yielded)
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_START",
            {
                "tool_name": "read_file",
                "arguments": {"path": "/test.py"},
                "tool_call_id": "call_regular",
            }
        )
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    gen = session.run("Test")
    
    results = []
    async for event in gen:
        results.append(event)
    
    # Should only have the regular tool call + completion
    assert len(results) == 2
    assert isinstance(results[0], ToolCallInfo)
    assert results[0].tool_name == "read_file"
    assert isinstance(results[1], AgentDone)


def test_gh_agent_session_filters_internal_tools():
    asyncio.run(_test_gh_agent_session_filters_internal_tools())


async def _test_gh_agent_session_cancellation():
    """Test that GhAgentSession respects cancellation events."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    cancellation_event = asyncio.Event()
    
    # Queue an event
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "Starting..."})
    )
    
    # Start the generator but don't consume yet
    gen = session.run("Test", cancellation_event=cancellation_event)
    it = aiter(gen)
    
    # Get first event (cancellation not set yet)
    first_event = await anext(it)
    assert isinstance(first_event, AgentChunk)
    assert first_event.content == "Starting..."
    
    # Now set cancellation
    cancellation_event.set()
    
    # Queue more events (these should not be yielded)
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "This should not appear"})
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    # Try to get next event - should stop iteration
    with pytest.raises(StopAsyncIteration):
        await anext(it)


def test_gh_agent_session_cancellation():
    asyncio.run(_test_gh_agent_session_cancellation())


async def _test_gh_agent_session_mixed_events():
    """Test that GhAgentSession handles a realistic mix of events."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()
    
    session = GhAgentSession(mock_copilot_session)
    
    # Simulate a realistic event sequence
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_REASONING_DELTA", {"delta_content": "Planning..."})
    )
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "I'll read "})
    )
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "the file"})
    )
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_START",
            {"tool_name": "read_file", "arguments": {}, "tool_call_id": "call_1"}
        )
    )
    await session._event_queue.put(
        create_mock_session_event(
            "TOOL_EXECUTION_COMPLETE",
            {"tool_call_id": "call_1", "success": True, "result": "content", "error": None}
        )
    )
    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "Done!"})
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )
    
    gen = session.run("Test")
    
    results = []
    async for event in gen:
        results.append(event)
    
    # Verify event sequence
    assert len(results) == 7
    assert isinstance(results[0], AgentChunk) and results[0].is_thought is True
    assert isinstance(results[1], AgentChunk) and results[1].is_thought is False
    assert isinstance(results[2], AgentChunk) and results[2].is_thought is False
    assert isinstance(results[3], ToolCallInfo)
    assert isinstance(results[4], ToolCallResultInfo)
    assert isinstance(results[5], AgentChunk) and results[5].is_thought is False
    assert isinstance(results[6], AgentDone)


def test_gh_agent_session_mixed_events():
    asyncio.run(_test_gh_agent_session_mixed_events())


async def _test_gh_agent_session_user_input_handshake():
    """Test that GhAgentSession handles user input requests via the broker."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()

    broker = GhUserInputBroker()
    session = GhAgentSession(mock_copilot_session, user_input_broker=broker)

    # Queue an initial text chunk so the generator advances.
    await session._event_queue.put(
        create_mock_session_event(
            "ASSISTANT_MESSAGE_DELTA", {"delta_content": "Let me ask..."}
        )
    )

    gen = session.run("Ask me something")
    it = aiter(gen)

    # First yield: text chunk
    first = await anext(it)
    assert isinstance(first, AgentChunk)
    assert first.content == "Let me ask..."

    # Simulate the SDK calling the broker in the background (as it would when
    # the model invokes the ask_user tool).
    async def sdk_asks_user():
        return await broker.handle_sdk_request(
            {"question": "Pick a colour", "choices": ["red", "blue"], "allowFreeform": False},
            {"session_id": "test-session"},
        )

    sdk_task = asyncio.create_task(sdk_asks_user())
    # Yield control so the broker coroutine enqueues the request.
    await asyncio.sleep(0)

    # The generator should now yield a UserInputRequest.
    user_req = await anext(it)
    assert isinstance(user_req, UserInputRequest)
    assert user_req.question == "Pick a colour"
    assert len(user_req.options) == 2
    assert user_req.options[0].label == "red"
    assert user_req.options[1].label == "blue"
    assert user_req.allow_freeform is False

    # Queue a SESSION_IDLE event so the loop can finish after we respond.
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )

    # Send the user's response back into the generator.
    done_event = await gen.asend(UserInputResponse(response="blue"))
    assert isinstance(done_event, AgentDone)

    # The SDK handler should have received our answer.
    sdk_result = await sdk_task
    assert sdk_result["answer"] == "blue"
    assert sdk_result["wasFreeform"] is True


def test_gh_agent_session_user_input_handshake():
    asyncio.run(_test_gh_agent_session_user_input_handshake())


async def _test_gh_agent_session_user_input_cancellation():
    """Test that cancelling user input stops the generator and fails the SDK future."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()

    broker = GhUserInputBroker()
    session = GhAgentSession(mock_copilot_session, user_input_broker=broker)

    gen = session.run("Ask me something")
    it = aiter(gen)

    # Simulate the SDK calling the broker.
    async def sdk_asks_user():
        return await broker.handle_sdk_request(
            {"question": "Pick a colour", "choices": [], "allowFreeform": True},
            {"session_id": "test-session"},
        )

    sdk_task = asyncio.create_task(sdk_asks_user())
    await asyncio.sleep(0)

    # The generator should yield a UserInputRequest.
    user_req = await anext(it)
    assert isinstance(user_req, UserInputRequest)

    # Send None to cancel (simulates user cancellation).
    with pytest.raises(StopAsyncIteration):
        await gen.asend(None)

    # The SDK future should have been rejected.
    with pytest.raises(RuntimeError, match="User cancelled"):
        await sdk_task


def test_gh_agent_session_user_input_cancellation():
    asyncio.run(_test_gh_agent_session_user_input_cancellation())


async def _test_gh_agent_session_without_broker():
    """Test that GhAgentSession works normally when no broker is provided."""
    mock_copilot_session = MagicMock()
    mock_copilot_session.send = AsyncMock()

    # No broker — should behave exactly like before.
    session = GhAgentSession(mock_copilot_session)

    await session._event_queue.put(
        create_mock_session_event("ASSISTANT_MESSAGE_DELTA", {"delta_content": "Hi"})
    )
    await session._event_queue.put(
        create_mock_session_event("SESSION_IDLE", {})
    )

    results = []
    async for event in session.run("Hello"):
        results.append(event)

    assert len(results) == 2
    assert isinstance(results[0], AgentChunk)
    assert results[0].content == "Hi"
    assert isinstance(results[1], AgentDone)


def test_gh_agent_session_without_broker():
    asyncio.run(_test_gh_agent_session_without_broker())
