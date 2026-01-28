"""Event-stream types and session protocol for Agent C.

This module defines the event union produced by the agentic loop and consumed by
middleware/adapters, plus the session protocol. Configuration and command-related
types live in dedicated modules for cohesion.
"""

from __future__ import annotations

from asyncio import Event
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol, TYPE_CHECKING

from .patching.types import (
    FilePatch,
    FilePatchResult,
    HunkApplyResult,
    HunkMatchOptions,
    PatchApplySummary,
    PatchHunk,
    PatchPlan,
)

if TYPE_CHECKING:  # pragma: no cover
    from .command_types import SessionConfig

__all__ = [
    "AgentChunk",
    "ToolCallInfo",
    "ApprovalRequest",
    "ApprovalResponse",
    "ToolResult",
    "ToolCallResultInfo",
    "AgentDone",
    "AgentEvent",
    "AgentEventStream",
    "AgentSessionProtocol",
    "SessionFactoryProtocol",
    # Re-exported patching types
    "FilePatch",
    "FilePatchResult",
    "HunkApplyResult",
    "HunkMatchOptions",
    "PatchApplySummary",
    "PatchHunk",
    "PatchPlan",
]


@dataclass
class AgentChunk:
    """A chunk of content from the agent (either text or thinking)."""

    content: str
    is_thought: bool = False


@dataclass
class ToolCallInfo:
    """Information about a tool call for UI display."""

    tool_name: str
    args: dict[str, Any]
    tool_call_id: str


@dataclass
class ApprovalRequest:
    """Yielded when the agentic loop needs approval for tool calls."""

    tool_calls: list[ToolCallInfo]


@dataclass
class ApprovalResponse:
    """Sent back to the agentic loop with approval decision."""

    approved: bool
    reason: str | None = None


@dataclass
class ToolResult:
    """A structured result from a tool execution."""

    success: bool
    content: str
    error: str | None = None


@dataclass
class ToolCallResultInfo:
    """Detailed information about a completed tool call."""

    tool_call_id: str
    result: ToolResult


@dataclass
class AgentDone:
    """Yielded when the agentic loop completes successfully."""

    history: Any


type AgentEvent = (
    AgentChunk | ToolCallInfo | ToolCallResultInfo | ApprovalRequest | AgentDone
)

type AgentEventStream = AsyncGenerator[AgentEvent, ApprovalResponse | None]


class AgentSessionProtocol(Protocol):
    """Protocol defining the interface for an agentic session."""

    def run(
        self,
        prompt: str,
        cancellation_event: Event | None = None,
    ) -> AgentEventStream:
        """Run the agentic session with the given prompt."""
        ...


class SessionFactoryProtocol(Protocol):
    """Protocol for creating agent sessions.

    Each backend provides its own implementation that knows how to
    construct sessions using backend-specific machinery. The UI layer
    depends on this abstraction, not concrete implementations.
    """

    async def create_session(self, config: "SessionConfig") -> AgentSessionProtocol:
        """Create a new agent session with the given configuration.

        Args:
            config: Backend-agnostic configuration for the session.

        Returns:
            A new agent session ready to run.

        Raises:
            Backend-specific exceptions (e.g., MissingAPIKeyError).
        """
        ...
