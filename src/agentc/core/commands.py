"""
Command parsing and execution for Agent C Next.

This module centralizes command semantics, ensuring consistent behavior
across all UIs. It provides a single source of truth for what commands
exist and what they do.

The module follows an effect-based pattern:
- CommandParser: Parses user input into structured CommandResult
- execute_command: Produces CommandEffect from CommandResult (pure function)
- UI layer: Applies the effects (framework-specific)
"""

from pathlib import Path

from .command_types import CommandEffect, CommandResult, CommandType, SessionConfig
from .config_types import ModelConfig
from .deps import RunDeps

COMMAND_METADATA: list[dict[str, str]] = [
    {
        "command": "/clear",
        "aliases": "/reset",
        "description": "Clear conversation history",
    },
    {
        "command": "/exit",
        "aliases": "/quit, /bye",
        "description": "Exit the application",
    },
    {
        "command": "/model",
        "args": "<name>",
        "description": "Switch model preset",
    },
    {
        "command": "/help",
        "aliases": "",
        "description": "Show available commands",
    },
]


def _skill_dirs_from_deps(deps: RunDeps | None) -> list[Path] | None:
    """Derive skill directories from run dependencies.

    The `RunDeps.skill_dirs` list includes directories to scan for skills.
    Tools are restricted to `RunDeps.root_dirs`, which automatically
    includes `skill_dirs` during initialization.
    """

    if deps is None or not deps.skill_dirs:
        return None

    return deps.skill_dirs


class CommandParser:
    """Centralized command parsing.

    Responsibilities:
    - Parse user input into structured commands
    - Return structured results for callers to act on
    
    Note: Model name validation happens in the session factory,
    not during parsing. This keeps the parser pure and backend-agnostic.
    """

    def __init__(self) -> None:
        """Initialize the command parser."""
        pass

    def parse(self, user_input: str) -> CommandResult:
        """Parse user input into structured command.

        Handles these command formats:
        - /clear or /reset: Clear conversation context
        - /exit, /quit, or /bye: Exit application
        - /model <name>: Switch to model preset
        - Anything else: Normal user input (not a command)

        Args:
            user_input: Raw user input from prompt.

        Returns:
            CommandResult with command type and arguments.
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

        # Check for help commands
        if command in ("/help", "/?"):
            return CommandResult(CommandType.HELP, {})

        # Check for model switch command
        parts = command.split(maxsplit=1)
        if len(parts) >= 2 and parts[0] == "/model":
            model_name = parts[1].strip()
            # Model validation happens in session factory
            return CommandResult(
                CommandType.MODEL_SWITCH,
                {"model": model_name},
            )

        # Unknown command (starts with / but not recognized)
        if command.startswith("/"):
            return CommandResult(
                CommandType.UNKNOWN,
                {"input": command, "error": f"Unknown command: {command}"},
            )

        # Regular input (not a command)
        return CommandResult(CommandType.NORMAL_INPUT, {})


def execute_command(
    result: CommandResult,
    deps: RunDeps | None = None,
) -> CommandEffect | None:
    """Execute a command and return its effect.

    This is a pure function that takes a parsed command and returns
    the effect that should be applied by the UI. Commands that require
    framework-specific handling (EXIT, UNKNOWN, NORMAL_INPUT) return None.

    Args:
        result: The parsed command result from CommandParser.
        deps: Runtime dependencies (root_dirs, skill_dirs).

    Returns:
        CommandEffect describing what should happen, or None if the
        command should be handled directly by the UI layer.
    """
    skill_dirs = _skill_dirs_from_deps(deps)

    match result.command_type:
        case CommandType.CLEAR:
            return CommandEffect(
                session_config=SessionConfig(
                    clear_history=True,
                    skill_dirs=skill_dirs,
                    deps=deps,
                ),
                notification="Conversation cleared",
                should_reset_ui=True,
            )

        case CommandType.MODEL_SWITCH:
            model = result.args.get("model")
            return CommandEffect(
                session_config=SessionConfig(
                    model_name=model,
                    clear_history=True,
                    skill_dirs=skill_dirs,
                    deps=deps,
                ),
                notification=f"Switched to model: {model}",
                should_reset_ui=True,
            )

        case CommandType.HELP:
            help_lines = ["Available Commands:"]
            for cmd in COMMAND_METADATA:
                line = f"- {cmd['command']}"
                if cmd.get("args"):
                    line += f" {cmd['args']}"
                if cmd.get("aliases"):
                    line += f" (aliases: {cmd['aliases']})"
                line += f": {cmd['description']}"
                help_lines.append(line)

            return CommandEffect(
                notification="\n".join(help_lines),
                should_reset_ui=False,
            )

        case _:
            # EXIT, UNKNOWN, NORMAL_INPUT are handled by the UI layer
            return None
