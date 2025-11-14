"""Command handling and parsing for Agent C.

This module centralizes command semantics, ensuring consistent behavior
across all command invocations. It provides a single source of truth for
what commands exist and what they do.

Design:
- Parse: User input → CommandType + args
- Validate: Check personality names, etc.
- Return: Structured result for callers to act on

Example:
    handler = CommandHandler({'coder': ..., 'reviewer': ...})
    cmd_type, args = handler.parse("/personality reviewer")
    # Returns CommandResult(CommandType.PERSONALITY_SWITCH, {'personality': 'reviewer'})
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CommandType(Enum):
    """Types of user commands."""

    NORMAL_INPUT = "normal"  # Regular agent input (not a command)
    CLEAR = "clear"  # Clear conversation context
    EXIT = "exit"  # Exit application
    PERSONALITY_SWITCH = "switch"  # Switch to different personality
    UNKNOWN = "unknown"  # Unknown command (error)


@dataclass
class CommandResult:
    """Result of parsing a user command.

    Attributes:
        command_type: Type of command parsed.
        args: Dictionary of parsed arguments specific to command type.
              Examples:
              - NORMAL_INPUT: {} (no args)
              - CLEAR: {} (no args)
              - EXIT: {} (no args)
              - PERSONALITY_SWITCH: {'personality': 'reviewer'}
              - UNKNOWN: {'input': '/badcommand', 'error': 'Unknown command...'}
    """

    command_type: CommandType
    args: dict[str, Any]


class CommandHandler:
    """Centralized command parsing and validation.

    This class is the single source of truth for all command semantics.
    Both the main event loop (agent.py) and the UI (console.py) use this
    same handler, ensuring consistent behavior across the application.

    Responsibilities:
    - Parse user input into structured commands
    - Validate commands (e.g., personality names)
    - Return structured results for callers to act on
    - Provide error messages for invalid commands
    """

    def __init__(self, personalities: dict[str, Any]):
        """Initialize handler with available personalities.

        Args:
            personalities: Dict of personality names to PersonalityConfig.
                          Used to validate /personality commands.
        """
        self.personalities = personalities

    def parse(self, user_input: str) -> CommandResult:
        """Parse user input into structured command.

        Handles these command formats:
        - /clear or /reset: Clear conversation context
        - /exit, /quit, or /bye: Exit application
        - /personality <name>: Switch to personality
        - Anything else: Normal user input (not a command)

        Args:
            user_input: Raw user input from prompt.

        Returns:
            CommandResult with command type and arguments.

        Examples:
            >>> handler = CommandHandler({'coder': ..., 'reviewer': ...})
            >>> handler.parse("hello world")
            CommandResult(command_type=CommandType.NORMAL_INPUT, args={})

            >>> handler.parse("/clear")
            CommandResult(command_type=CommandType.CLEAR, args={})

            >>> handler.parse("/personality reviewer")
            CommandResult(
                command_type=CommandType.PERSONALITY_SWITCH,
                args={'personality': 'reviewer'}
            )

            >>> handler.parse("/personality invalid")
            CommandResult(
                command_type=CommandType.UNKNOWN,
                args={
                    'input': '/personality invalid',
                    'error': 'Unknown personality: invalid'
                }
            )
        """
        # Normalize input
        command = user_input.strip().lower()

        # Empty input is normal input
        if not command:
            return CommandResult(CommandType.NORMAL_INPUT, {})

        # Check for exit commands
        if command in ("/exit", "/quit", "/bye"):
            return CommandResult(CommandType.EXIT, {})

        # Check for clear commands
        if command in ("/clear", "/reset"):
            return CommandResult(CommandType.CLEAR, {})

        # Check for personality switch command
        parts = command.split(maxsplit=1)
        if len(parts) >= 2 and parts[0] == "/personality":
            personality_name = parts[1].strip()
            if personality_name in self.personalities:
                return CommandResult(
                    CommandType.PERSONALITY_SWITCH,
                    {"personality": personality_name},
                )
            else:
                return CommandResult(
                    CommandType.UNKNOWN,
                    {
                        "input": command,
                        "error": f"Unknown personality: {personality_name}",
                    },
                )

        # Unknown command (starts with / but not recognized)
        if command.startswith("/"):
            return CommandResult(
                CommandType.UNKNOWN,
                {"input": command, "error": f"Unknown command: {command}"},
            )

        # Regular input (not a command)
        return CommandResult(CommandType.NORMAL_INPUT, {})
