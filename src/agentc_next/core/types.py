"""Common types and dataclasses for Agent C Next.

This module provides a central location for types shared between the agentic loop,
adapters, and the UI, helping to prevent circular dependencies and architectural leaks.
"""

from __future__ import annotations

from asyncio import Event
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Protocol

from pydantic_ai import Agent, DeferredToolRequests


@dataclass
class ProviderConfig:
    """Configuration for a provider loaded from TOML."""

    name: str
    provider_cls_path: str  # e.g., "pydantic_ai.providers.anthropic.AnthropicProvider"
    model_cls_path: str  # e.g., "pydantic_ai.models.anthropic.AnthropicModel"
    model_name: str
    api_key_env: str | None = None
    base_url: str | None = None


@dataclass
class SkillMetadata:
    """Metadata for an agent skill."""

    name: str
    description: str
    path: Path
    body: str


@dataclass
class RunDeps:
    """Dependencies for the agent run context."""

    pass


type NextAgent = Agent[RunDeps, str | DeferredToolRequests]


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
        deps: RunDeps,
        cancellation_event: Event | None = None,
    ) -> AgentEventStream:
        """Run the agentic session with the given prompt and dependencies."""
        ...
