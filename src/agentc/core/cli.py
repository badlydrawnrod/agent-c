"""Command-line argument parsing for Agent C.

This module handles CLI argument parsing and validation, keeping
command-line concerns separate from agent creation logic.
"""

import argparse

from .types import AgentConfig, PersonalityConfig


def parse_args(
    personalities: dict[str, PersonalityConfig],
    agent_configs: dict[str, AgentConfig],
) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        personalities: Available personalities for choice validation.
        agent_configs: Available agent configurations for provider validation.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run the agent with different personalities."
    )
    parser.add_argument(
        "--personality",
        choices=list(personalities.keys()),
        default="coder",
        help="Personality to use (default: coder)",
    )
    parser.add_argument(
        "--model",
        help="Override the default model for the selected personality",
    )
    parser.add_argument(
        "--provider",
        choices=list(agent_configs.keys()),
        help="Override the default provider for the selected personality",
    )
    return parser.parse_args()
