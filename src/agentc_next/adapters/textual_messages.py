"""Textual `Message` types representing agent events.

Defines lightweight `textual.message.Message` subclasses used by the
UI to represent streamed text/thinking deltas, tool calls and approval
requests, completion, errors, and cancellation events.
"""

import asyncio
from typing import Any

from textual.message import Message

from ..core.types import ToolCallInfo, ToolResult


class AgentThinkingMessage(Message):
    """Agent is thinking (streaming delta)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class AgentTextMessage(Message):
    """Agent text response (streaming delta)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class AgentToolCallMessage(Message):
    """Agent is calling a tool."""

    def __init__(self, tool_call_id: str, tool_name: str, args: dict[str, Any]) -> None:
        super().__init__()
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.args = args


class AgentToolResultMessage(Message):
    """Agent tool call completed with a result."""

    def __init__(self, tool_call_id: str, result: ToolResult) -> None:
        super().__init__()
        self.tool_call_id = tool_call_id
        self.result = result


class AgentApprovalRequestMessage(Message):
    """Agent requires approval for tool calls."""

    def __init__(self, tool_calls: list[ToolCallInfo], future: asyncio.Future) -> None:
        super().__init__()
        self.tool_calls = tool_calls
        self._future = future

    def resolve(self, approved: bool, reason: str | None = None) -> None:
        if self._future.done():
            return
        self._future.set_result((approved, reason))


class AgentDoneMessage(Message):
    """Agent run completed successfully."""

    def __init__(self, history: Any = None) -> None:
        super().__init__()
        self.history = history


class AgentErrorMessage(Message):
    """Agent encountered an error."""

    def __init__(self, error: str) -> None:
        super().__init__()
        self.error = error


class AgentCancelledMessage(Message):
    """Agent run was cancelled."""

    def __init__(self) -> None:
        super().__init__()
