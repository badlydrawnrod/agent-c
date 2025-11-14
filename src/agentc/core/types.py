"""Type definitions and data models for Agent C.

This module defines the core data structures used throughout the agent,
including configuration models for agents and personalities, as well as
the dependencies injected into the agent's run context.
"""

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Configuration for an agent provider.

    Attributes:
        provider_cls: The provider class (e.g., AnthropicProvider).
        model_cls: The model class (e.g., AnthropicModel).
        api_key_env: Environment variable name for API key (optional).
        base_url: Custom base URL for the provider (optional).
        model_name: Name of the model to use.
    """

    provider_cls: Any
    model_cls: Any
    api_key_env: str | None = None
    base_url: str | None = None
    model_name: str


class PersonalityConfig(BaseModel):
    """Configuration for an agent personality.

    Attributes:
        provider: Name of the provider to use (e.g., 'anthropic').
        model: Optional override for the model name.
        prompt_file: Path to the prompt file (relative to prompts/).
        description: Human-readable description of this personality.
    """

    provider: str
    model: str | None = None
    prompt_file: str
    description: str


@dataclass
class RunDeps:
    """Dependencies for the agent run context.

    Attributes:
        info: Callable to display informational messages to the user.
    """

    info: Callable[[str], None]
