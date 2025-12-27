"""
Common types and dataclasses for Agent C Next.

This module provides a central location for types shared between the agentic loop,
adapters, and the UI, helping to prevent circular dependencies and architectural leaks.
"""

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol, TypeAlias, Union

from pydantic_ai import Agent, DeferredToolRequests


@dataclass
class RunDeps:
    """Dependencies for the agent run context."""

    pass


NextAgent: TypeAlias = Agent[RunDeps, Union[str, DeferredToolRequests]]


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
class AgentDone:
    """Yielded when the agentic loop completes successfully."""

    history: Any


AgentEvent: TypeAlias = AgentChunk | ToolCallInfo | ApprovalRequest | AgentDone


class AgentSessionProtocol(Protocol):
    """Protocol defining the interface for an agentic session."""

    def run(
        self,
        prompt: str,
        deps: Any,
        cancellation_event: Any | None = None,
    ) -> AsyncGenerator[AgentEvent, ApprovalResponse | None]:
        """Run the agentic session with the given prompt and dependencies."""
        ...
