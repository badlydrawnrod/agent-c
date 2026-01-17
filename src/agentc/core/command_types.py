"""Command parsing and effect types.

Isolates command-related data structures from the shared event types to
improve cohesion and keep responsibilities clear.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .types import AgentSessionProtocol


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

    Represents the pure data outcome of a command execution. The UI layer
    is responsible for interpreting and applying these effects. Commands
    like EXIT and UNKNOWN are handled directly by the UI since they require
    framework-specific actions.

    Attributes:
        new_session: A new agent session to replace the current one, or None.
        notification: A message to display to the user, or None.
        should_reset_ui: Whether the UI should clear its state.
    """

    new_session: "AgentSessionProtocol" | None = None
    notification: str | None = None
    should_reset_ui: bool = False


__all__ = ["CommandType", "CommandResult", "CommandEffect"]
