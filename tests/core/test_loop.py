import asyncio
from typing import Any
from unittest.mock import MagicMock

from pydantic_ai import (
    AgentRunResultEvent,
    DeferredToolRequests,
)
from pydantic_ai.messages import (
    PartStartEvent,
    TextPart,
    ToolCallPart,
)

from agentc.core.backends.pydantic_ai.loop import AgentSession
from agentc.core.backends.pydantic_ai.types import NextAgent
from agentc.core.deps import RunDeps
from agentc.core.types import (
    AgentChunk,
    AgentDone,
    ApprovalRequest,
    ApprovalResponse,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolResult,
    UserInputRequest,
    UserInputResponse,
)


def create_mock_agent_run_result(output: Any, history: list[str]) -> MagicMock:
    """Create a mock AgentRunResultEvent with the given output and history.
    
    Args:
        output: The output to include in the result.
        history: The message history list.
        
    Returns:
        A MagicMock AgentRunResultEvent.
    """
    result_mock = MagicMock()
    result_mock.output = output
    result_mock.all_messages.return_value = history
    
    event_mock = MagicMock(spec=AgentRunResultEvent)
    event_mock.result = result_mock
    return event_mock


def create_mock_approval_result(tool_name: str, tool_id: str) -> MagicMock:
    """Create a mock AgentRunResultEvent with a deferred tool request.
    
    Args:
        tool_name: The name of the tool to approve.
        tool_id: The tool call ID.
        
    Returns:
        A MagicMock AgentRunResultEvent representing an approval request.
    """
    output_mock = MagicMock(spec=DeferredToolRequests)
    approval_mock = MagicMock()
    approval_mock.tool_name = tool_name
    approval_mock.args = '{"a": 1}'
    approval_mock.tool_call_id = tool_id
    output_mock.approvals = [approval_mock]
    
    result_mock = MagicMock()
    result_mock.output = output_mock
    result_mock.all_messages.return_value = ["call_msg"]
    
    event_mock = MagicMock(spec=AgentRunResultEvent)
    event_mock.result = result_mock
    return event_mock


async def _test_agent_session_history():
    """Test that AgentSession maintains conversation history."""
    agent = MagicMock(spec=NextAgent)
    deps = RunDeps(root_dirs=[])
    session = AgentSession(agent=agent, deps=deps)
    
    # Initially empty
    assert session.history == []
    
    # Update and verify
    session.update_history(["msg1"])
    assert session.history == ["msg1"]


def test_agent_session_history():
    asyncio.run(_test_agent_session_history())


async def _test_agent_session_run_text():
    """Test that AgentSession yields text chunks and completion event."""
    agent = MagicMock(spec=NextAgent)
    
    # Mock agent to yield text and completion
    async def mock_run_stream_events(*args, **kwargs):
        yield PartStartEvent(part=TextPart(content="Hello"), index=0)
        yield create_mock_agent_run_result(output="Final response", history=["msg1", "msg2"])

    agent.run_stream_events = mock_run_stream_events
    
    # Run session and collect events
    deps = RunDeps(root_dirs=[])
    session = AgentSession(agent=agent, deps=deps)
    gen = session.run("Hi")
    
    results = []
    async for event in gen:
        results.append(event)
    
    # Verify events
    assert len(results) == 2
    
    text_chunk = results[0]
    assert isinstance(text_chunk, AgentChunk)
    assert text_chunk.content == "Hello"
    
    completion = results[1]
    assert isinstance(completion, AgentDone)
    assert completion.history == ["msg1", "msg2"]


def test_agent_session_run_text():
    asyncio.run(_test_agent_session_run_text())


async def _test_agent_session_run_approval_handshake():
    """Test that AgentSession handles tool approval requests and responses."""
    agent = MagicMock(spec=NextAgent)
    
    # Mock agent to yield approval request, then final response
    async def mock_run_stream_events(*args, **kwargs):
        if kwargs.get('deferred_tool_results') is None:
            # Initial request: yield approval request
            yield create_mock_approval_result(tool_name="test_tool", tool_id="call1")
        else:
            # After approval: yield final response
            yield create_mock_agent_run_result(output="Approved!", history=["call_msg", "resp_msg"])

    agent.run_stream_events = mock_run_stream_events
    
    # Run session with manual async iteration for handshake
    deps = RunDeps(root_dirs=[])
    session = AgentSession(agent=agent, deps=deps)
    gen = session.run("Run tool")
    
    it = aiter(gen)
    
    # Receive approval request
    approval_request = await anext(it)
    assert isinstance(approval_request, ApprovalRequest)
    assert approval_request.tool_calls[0].tool_name == "test_tool"
    
    # Send approval response
    completion = await it.asend(ApprovalResponse(approved=True))
    assert isinstance(completion, AgentDone)
    assert completion.history == ["call_msg", "resp_msg"]


def test_agent_session_run_approval_handshake():
    asyncio.run(_test_agent_session_run_approval_handshake())


async def _test_agent_session_run_tool_call():
    """Test that AgentSession detects and yields tool calls."""
    agent = MagicMock(spec=NextAgent)
    
    # Mock agent to yield a tool call and completion
    async def mock_run_stream_events(*args, **kwargs):
        yield PartStartEvent(
            part=ToolCallPart(tool_name="my_tool", args={"x": 1}, tool_call_id="call1"),
            index=0
        )
        yield create_mock_agent_run_result(output="Finished tool", history=["msg1"])

    agent.run_stream_events = mock_run_stream_events
    
    # Run session and collect events
    deps = RunDeps(root_dirs=[])
    session = AgentSession(agent=agent, deps=deps)
    gen = session.run("Use tool")
    
    results = []
    async for event in gen:
        results.append(event)
    
    # Verify events
    assert len(results) == 2
    
    tool_call = results[0]
    assert isinstance(tool_call, ToolCallInfo)
    assert tool_call.tool_name == "my_tool"
    assert tool_call.tool_call_id == "call1"
    
    completion = results[1]
    assert isinstance(completion, AgentDone)


def test_agent_session_run_tool_call():
    asyncio.run(_test_agent_session_run_tool_call())


async def _test_agent_session_run_tool_result():
    """Test that AgentSession detects and yields tool results."""
    from pydantic_ai import FunctionToolResultEvent
    from pydantic_ai.messages import ToolReturnPart
    
    agent = MagicMock(spec=NextAgent)
    
    # Mock agent to yield a tool call, then a tool result, then completion
    async def mock_run_stream_events(*args, **kwargs):
        yield PartStartEvent(
            part=ToolCallPart(tool_name="my_tool", args={"x": 1}, tool_call_id="call1"),
            index=0
        )
        
        # Yield a tool result event
        tool_result = ToolResult(success=True, content="Tool executed successfully")
        result_event = MagicMock(spec=FunctionToolResultEvent)
        result_event.result = MagicMock(spec=ToolReturnPart)
        result_event.result.tool_call_id = "call1"
        result_event.result.content = tool_result
        yield result_event
        
        yield create_mock_agent_run_result(output="Finished", history=["msg1"])

    agent.run_stream_events = mock_run_stream_events
    
    # Run session and collect events
    deps = RunDeps(root_dirs=[])
    session = AgentSession(agent=agent, deps=deps)
    gen = session.run("Use tool")
    
    results = []
    async for event in gen:
        results.append(event)
    
    # Verify events
    assert len(results) == 3
    
    tool_call = results[0]
    assert isinstance(tool_call, ToolCallInfo)
    assert tool_call.tool_name == "my_tool"
    
    tool_result_info = results[1]
    assert isinstance(tool_result_info, ToolCallResultInfo)
    assert tool_result_info.tool_call_id == "call1"
    assert isinstance(tool_result_info.result, ToolResult)
    assert tool_result_info.result.success is True
    
    completion = results[2]
    assert isinstance(completion, AgentDone)


def test_agent_session_run_tool_result():
    asyncio.run(_test_agent_session_run_tool_result())


async def _test_agent_session_run_user_input_handshake():
    """Test that AgentSession handles user input requests and responses."""
    agent = MagicMock(spec=NextAgent)

    async def mock_run_stream_events(*args, **kwargs):
        deps = kwargs.get("deps")
        assert deps is not None
        response = await deps.user_input_handler.request_user_input(
            UserInputRequest(
                question="Pick a value",
                options=[],
                allow_freeform=True,
            )
        )
        yield create_mock_agent_run_result(
            output=f"Selected {response.response}",
            history=["msg1", "msg2"],
        )

    agent.run_stream_events = mock_run_stream_events

    deps = RunDeps(root_dirs=[])
    session = AgentSession(agent=agent, deps=deps)
    gen = session.run("Ask user")

    it = aiter(gen)

    request = await anext(it)
    assert isinstance(request, UserInputRequest)

    completion = await it.asend(UserInputResponse(response="choice"))
    assert isinstance(completion, AgentDone)
    assert completion.history == ["msg1", "msg2"]


def test_agent_session_run_user_input_handshake():
    asyncio.run(_test_agent_session_run_user_input_handshake())
