"""Console event types representing agent events.

Defines lightweight dataclasses used by the console adapter to represent
streamed text/thinking deltas, tool calls and approval requests, completion,
errors, and cancellation events. These are the console-specific equivalents
of the Textual `Message` types.
"""

from dataclasses import dataclass
from typing import Any

from ..core.types import ToolCallInfo, ToolResult


@dataclass
class ConsoleThinkingEvent:
    """Agent is thinking (streaming delta)."""

    text: str


@dataclass
class ConsoleTextEvent:
    """Agent text response (streaming delta)."""

    text: str


@dataclass
class ConsoleToolCallEvent:
    """Agent is calling a tool."""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any]


@dataclass
class ConsoleToolResultEvent:
    """Agent tool call completed with a result."""

    tool_call_id: str
    result: ToolResult


@dataclass
class ConsoleApprovalRequestEvent:
    """Agent requires approval for tool calls."""

    tool_calls: list[ToolCallInfo]


@dataclass
class ConsoleDoneEvent:
    """Agent run completed successfully."""

    history: Any = None


@dataclass
class ConsoleErrorEvent:
    """Agent encountered an error."""

    error: str


@dataclass
class ConsoleCancelledEvent:
    """Agent run was cancelled."""

    pass


# Type alias for all console events
type ConsoleEvent = (
    ConsoleThinkingEvent
    | ConsoleTextEvent
    | ConsoleToolCallEvent
    | ConsoleToolResultEvent
    | ConsoleApprovalRequestEvent
    | ConsoleDoneEvent
    | ConsoleErrorEvent
    | ConsoleCancelledEvent
)
