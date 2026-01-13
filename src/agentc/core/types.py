"""Common types and dataclasses for Agent C Next.

This module provides a central location for types shared between the agentic loop,
adapters, and the UI, helping to prevent circular dependencies and architectural leaks.
"""

from __future__ import annotations

from asyncio import Event
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Protocol

from pydantic_ai import Agent, DeferredToolRequests


@dataclass
class BackendConfig:
    """Configuration for a model backend loaded from TOML."""

    name: str
    provider_cls_path: str  # e.g., "pydantic_ai.providers.anthropic.AnthropicProvider"
    model_cls_path: str  # e.g., "pydantic_ai.models.anthropic.AnthropicModel"
    api_key_env: str | None = None
    base_url: str | None = None


@dataclass
class ModelConfig:
    """Configuration for a model preset bound to a backend."""

    name: str
    backend: str
    model_name: str
    api_key_env: str | None = None
    base_url: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


class CommandType(Enum):
    """Types of user commands."""

    NORMAL_INPUT = "normal"  # Regular agent input (not a command)
    CLEAR = "clear"  # Clear conversation context
    EXIT = "exit"  # Exit application
    MODEL_SWITCH = "switch"  # Switch to different model preset
    HELP = "help"  # Show available commands
    UNKNOWN = "unknown"  # Unknown command (error)


@dataclass
class CommandResult:
    """Result of parsing a user command."""

    command_type: CommandType
    args: dict[str, Any]


@dataclass
class CommandEffect:
    """Effect produced by executing a command.

    This dataclass represents the pure data outcome of a command execution.
    The UI layer is responsible for interpreting and applying these effects.
    Commands like EXIT and UNKNOWN are handled directly by the UI since they
    require framework-specific actions.

    Attributes:
        new_session: A new agent session to replace the current one, or None.
        notification: A message to display to the user, or None.
        should_reset_ui: Whether the UI should clear its state.
    """

    new_session: AgentSessionProtocol | None = None
    notification: str | None = None
    should_reset_ui: bool = False


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

    root_dirs: list[Path] = field(default_factory=list)
    skill_dirs: list[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Consolidate root_dirs and skill_dirs.

        Removes redundant paths (descendants) and duplicates.
        Ensures skill_dirs are included in root_dirs so tools can access them.
        """
        # Ensure all skill_dirs are covered by root_dirs
        self.root_dirs.extend(self.skill_dirs)

        self.root_dirs = self._consolidate_paths(self.root_dirs)
        self.skill_dirs = self._consolidate_paths(self.skill_dirs)

    def _consolidate_paths(self, paths: list[Path]) -> list[Path]:
        if not paths:
            return []
        # Resolve, remove duplicates, and sort by length (shallowest first)
        resolved = sorted({p.resolve() for p in paths}, key=lambda p: len(p.parts))
        unique: list[Path] = []
        for p in resolved:
            if not any(p.is_relative_to(parent) for parent in unique):
                unique.append(p)
        return unique


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
        cancellation_event: Event | None = None,
    ) -> AgentEventStream:
        """Run the agentic session with the given prompt."""
        ...
