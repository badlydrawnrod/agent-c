"""Command parsing and effect types.

Isolates command-related data structures from the shared event types to
improve cohesion and keep responsibilities clear.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .deps import RunDeps


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
class SessionConfig:
    """Backend-agnostic session configuration.

    Pure data describing what kind of session to create, without
    knowing how to create it. The session factory translates this
    into backend-specific session construction.

    Attributes:
        model_name: Model preset name (e.g., "claude-sonnet", "gpt-4o").
        clear_history: Whether to start with empty conversation history.
        skill_dirs: Directories to scan for SKILL.md files.
        deps: Runtime dependencies (root_dirs, skill_dirs).
    """

    model_name: str | None = None
    clear_history: bool = False
    skill_dirs: list[Path] | None = None
    deps: "RunDeps" | None = None


@dataclass
class CommandEffect:
    """Effect produced by executing a command.

    Represents the pure data outcome of a command execution. The UI layer
    is responsible for interpreting and applying these effects using its
    injected session factory. Commands like EXIT and UNKNOWN are handled
    directly by the UI since they require framework-specific actions.

    Attributes:
        session_config: Configuration for creating a new session, or None.
        notification: A message to display to the user, or None.
        should_reset_ui: Whether the UI should clear its state.
    """

    session_config: SessionConfig | None = None
    notification: str | None = None
    should_reset_ui: bool = False


__all__ = ["CommandType", "CommandResult", "SessionConfig", "CommandEffect"]
