"""System prompt building for Agent C."""

from pathlib import Path

from .types import PersonalityConfig


def load_system_prompt(personality: PersonalityConfig) -> str:
    """Load the system prompt from file.

    Args:
        personality: PersonalityConfig containing the prompt file name.

    Returns:
        System prompt content.
    """
    with open(
        Path(__file__).parent.parent / "prompts" / personality.prompt_file,
        "r",
        encoding="utf-8",
    ) as f:
        return f.read()


def build_delegation_info(
    personality_name: str, personalities: dict[str, PersonalityConfig]
) -> str:
    """Build delegation instructions.

    This creates instructions informing the agent about available personalities
    it can delegate tasks to.

    Args:
        personality_name: Name of the current personality.
        personalities: All available personalities.

    Returns:
        Formatted delegation instructions.
    """
    return (
        "\n\nDelegation Instructions:\nYou can delegate tasks to other personalities using the delegate_to_agent tool if the task better fits their expertise.\n\nAvailable personalities:\n"
        + "\n".join(
            f"- {name}: {config.description}"
            for name, config in personalities.items()
            if name != personality_name
        )
    )


def build_system_prompt(
    personality: PersonalityConfig,
    personality_name: str,
    personalities: dict[str, PersonalityConfig],
) -> str:
    """Build complete system prompt with base prompt and delegation info.

    Args:
        personality: PersonalityConfig for current personality.
        personality_name: Name of current personality.
        personalities: All available personalities.

    Returns:
        Complete system prompt.
    """
    base_prompt = load_system_prompt(personality)
    delegation_info = build_delegation_info(personality_name, personalities)
    return base_prompt + delegation_info
