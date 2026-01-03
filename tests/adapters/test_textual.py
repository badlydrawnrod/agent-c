import asyncio
from unittest.mock import MagicMock

from textual.app import App
from agentc.adapters.textual import TextualAgentAdapter
from agentc.core.types import (
    AgentChunk,
    AgentDone as AgentDoneEvent,
    AgentSessionProtocol,
    ApprovalRequest,
    ToolCallResultInfo,
    ToolResult,
)
from agentc.adapters.textual_messages import (
    AgentTextMessage,
    AgentDoneMessage,
    AgentApprovalRequestMessage,
    AgentToolResultMessage,
)


def extract_posted_messages(app_mock):
    """Extract the actual message objects from post_message call args.
    
    Args:
        app_mock: A MagicMock of the Textual App with post_message called.
        
    Returns:
        List of message objects passed to post_message.
    """
    return [call.args[0] for call in app_mock.post_message.call_args_list]


async def _test_textual_adapter_run():
    app = MagicMock(spec=App)
    session = MagicMock(spec=AgentSessionProtocol)
    
    async def mock_run(*args, **kwargs):
        yield AgentChunk(content="Hello", is_thought=False)
        yield AgentDoneEvent(history=["msg1"])
    
    session.run = mock_run
    
    adapter = TextualAgentAdapter(app=app, session=session, prompt="test")
    await adapter.run()
    
    # Verify messages posted to app
    messages = extract_posted_messages(app)
    assert len(messages) == 2
    
    # First message: AgentTextMessage with content
    first_msg = messages[0]
    assert isinstance(first_msg, AgentTextMessage)
    assert first_msg.text == "Hello"
    
    # Second message: AgentDoneMessage with history
    second_msg = messages[1]
    assert isinstance(second_msg, AgentDoneMessage)
    assert second_msg.history == ["msg1"]

def test_textual_adapter_run():
    asyncio.run(_test_textual_adapter_run())

async def _test_textual_adapter_approval():
    app = MagicMock(spec=App)
    session = MagicMock(spec=AgentSessionProtocol)
    
    async def mock_run(*args, **kwargs):
        # Yield ApprovalRequest
        resp = yield ApprovalRequest(tool_calls=[])
        assert resp.approved is True
        yield AgentChunk(content="Done", is_thought=False)
    
    session.run = mock_run
    
    adapter = TextualAgentAdapter(app=app, session=session, prompt="test")
    
    # Set up post_message with side_effect to auto-approve approval requests
    def post_message_side_effect(msg):
        if isinstance(msg, AgentApprovalRequestMessage):
            msg.resolve(True, "Approved")
        
    app.post_message.side_effect = post_message_side_effect
    
    await adapter.run()
    
    # Verify that AgentApprovalRequestMessage was posted
    messages = extract_posted_messages(app)
    approval_msgs = [msg for msg in messages if isinstance(msg, AgentApprovalRequestMessage)]
    assert len(approval_msgs) == 1, "Expected an approval request to be posted"

def test_textual_adapter_approval():
    asyncio.run(_test_textual_adapter_approval())


async def _test_textual_adapter_tool_result():
    """Test that TextualAgentAdapter maps ToolCallResultInfo to AgentToolResultMessage."""
    app = MagicMock(spec=App)
    session = MagicMock(spec=AgentSessionProtocol)
    
    async def mock_run(*args, **kwargs):
        # Yield a tool result
        tool_result = ToolResult(success=True, content="Tool output")
        yield ToolCallResultInfo(tool_call_id="call1", result=tool_result)
        yield AgentDoneEvent(history=["msg1"])
    
    session.run = mock_run
    
    adapter = TextualAgentAdapter(app=app, session=session, prompt="test")
    await adapter.run()
    
    # Verify messages posted to app
    messages = extract_posted_messages(app)
    
    # Should have tool result message and done message
    tool_result_msgs = [msg for msg in messages if isinstance(msg, AgentToolResultMessage)]
    assert len(tool_result_msgs) == 1
    
    tool_result_msg = tool_result_msgs[0]
    assert tool_result_msg.tool_call_id == "call1"
    # Result can be ToolResult or dict
    if isinstance(tool_result_msg.result, dict):
        assert tool_result_msg.result.get("success") is True
    else:
        assert tool_result_msg.result.success is True

def test_textual_adapter_tool_result():
    asyncio.run(_test_textual_adapter_tool_result())
