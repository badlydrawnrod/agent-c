"""Event-stream types and session protocol for Agent C.

This module defines the event union produced by the agentic loop and consumed by
middleware/adapters, plus the session protocol. Configuration and command-related
types live in dedicated modules for cohesion.
"""

from __future__ import annotations

from asyncio import Event
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from .patching.types import (
    FilePatch,
    FilePatchResult,
    HunkApplyResult,
    HunkMatchOptions,
    PatchApplySummary,
    PatchHunk,
    PatchPlan,
)


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
