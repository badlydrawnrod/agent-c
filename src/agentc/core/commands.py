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

from .factory import create_agent
from .loop import AgentSession
from .types import CommandEffect, CommandResult, CommandType, ProviderConfig, RunDeps


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
    """Centralized command parsing and validation.

    Responsibilities:
    - Parse user input into structured commands
    - Validate commands (e.g., provider names)
    - Return structured results for callers to act on
    """

    def __init__(self, providers: dict[str, ProviderConfig]):
        """Initialize parser with available providers.

        Args:
            providers: Dict of provider names to ProviderConfig.
        """
        self.providers = providers

    def parse(self, user_input: str) -> CommandResult:
        """Parse user input into structured command.

        Handles these command formats:
        - /clear or /reset: Clear conversation context
        - /exit, /quit, or /bye: Exit application
        - /provider <name>: Switch to provider
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

        # Check for provider switch command
        parts = command.split(maxsplit=1)
        if len(parts) >= 2 and parts[0] == "/provider":
            provider_name = parts[1].strip()
            if provider_name in self.providers:
                return CommandResult(
                    CommandType.PROVIDER_SWITCH,
                    {"provider": provider_name},
                )
            else:
                return CommandResult(
                    CommandType.UNKNOWN,
                    {
                        "input": command,
                        "error": f"Unknown provider: {provider_name}",
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


def execute_command(
    result: CommandResult,
    provider_name: str | None = None,
    deps: RunDeps | None = None,
) -> CommandEffect | None:
    """Execute a command and return its effect.

    This is a pure function that takes a parsed command and returns
    the effect that should be applied by the UI. Commands that require
    framework-specific handling (EXIT, UNKNOWN, NORMAL_INPUT) return None.

    Args:
        result: The parsed command result from CommandParser.
        provider_name: Optional provider name for PROVIDER_SWITCH command.

    Returns:
        CommandEffect describing what should happen, or None if the
        command should be handled directly by the UI layer.
    """
    skill_dirs = _skill_dirs_from_deps(deps)

    match result.command_type:
        case CommandType.CLEAR:
            return CommandEffect(
                new_session=AgentSession(
                    agent=create_agent(skill_dirs=skill_dirs), deps=deps
                ),
                notification="Conversation cleared",
                should_reset_ui=True,
            )

        case CommandType.PROVIDER_SWITCH:
            provider = result.args.get("provider", provider_name)
            return CommandEffect(
                new_session=AgentSession(
                    agent=create_agent(provider_name=provider, skill_dirs=skill_dirs),
                    deps=deps,
                ),
                notification=f"Switched to provider: {provider}",
                should_reset_ui=True,
            )

        case _:
            # EXIT, UNKNOWN, NORMAL_INPUT are handled by the UI layer
            return None
