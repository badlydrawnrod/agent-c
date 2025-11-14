"""Configuration loading and building for Agent C.

This module handles loading configuration from TOML files and building
typed configuration objects. Configuration is loaded in the following
precedence order:

1. providers.toml (bundled with the application)
2. config.toml (optional, in package directory or current working directory)
3. personalities.toml (bundled with the application)

User overrides in config.toml take precedence over default provider settings.
"""

from importlib import import_module

from ._config import ConfigLocator
from .types import AgentConfig, PersonalityConfig


def get_class(class_path: str) -> type:
    """Dynamically import and return the class based on its full path.

    Args:
        class_path: Full path to class (e.g., 'pydantic_ai.AnthropicModel').

    Returns:
        The imported class.

    Raises:
        ValueError: If import fails or class not found.
    """
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise ValueError(f"Could not import class from {class_path}: {e}")


def load_providers() -> dict:
    """Load providers configuration from providers.toml.

    Returns:
        Dictionary of provider configurations.
    """
    locator = ConfigLocator()
    return locator.load_providers()


def load_config_overrides() -> dict:
    """Load configuration overrides from config.toml.

    Checks both the package directory and current working directory.
    Returns empty dict if file not found.

    Returns:
        Dictionary of configuration overrides.
    """
    locator = ConfigLocator()
    return locator.load_config_overrides()


def load_personalities_data() -> dict:
    """Load personalities configuration from personalities.toml.

    Returns:
        Dictionary of personality configurations.
    """
    locator = ConfigLocator()
    return locator.load_personalities()


def build_agent_configs(
    providers_data: dict, config_data: dict
) -> dict[str, AgentConfig]:
    """Build agent configurations by merging providers and overrides.

    Configuration precedence (highest to lowest):
    1. config.toml overrides
    2. providers.toml defaults
    3. Validation defaults

    Args:
        providers_data: Provider definitions from providers.toml.
        config_data: User overrides from config.toml.

    Returns:
        Dictionary of AgentConfig objects keyed by provider name.
    """
    agent_configs = {}
    for agent_type, data in providers_data.items():
        provider_config = AgentConfig(
            provider_cls=get_class(data["provider_cls"]),
            model_cls=get_class(data["model_cls"]),
            api_key_env=data.get("api_key_env"),
            base_url=data.get("base_url"),
            model_name=data["model_name"],
        )

        if agent_type in config_data:
            user_config = config_data[agent_type]
            provider_config.api_key_env = user_config.get(
                "api_key_env", provider_config.api_key_env
            )
            provider_config.base_url = user_config.get(
                "base_url", provider_config.base_url
            )
            provider_config.model_name = user_config.get(
                "model_name", provider_config.model_name
            )

        agent_configs[agent_type] = provider_config

    return agent_configs


def build_personalities(personalities_data: dict) -> dict[str, PersonalityConfig]:
    """Build personalities configuration.

    Args:
        personalities_data: Raw personality data from personalities.toml.

    Returns:
        Dictionary of PersonalityConfig objects keyed by personality name.
    """
    personalities = {}
    for personality_name, data in personalities_data.items():
        personalities[personality_name] = PersonalityConfig(**data)

    return personalities


def load_configs() -> tuple[dict[str, AgentConfig], dict[str, PersonalityConfig]]:
    """Load and build agent configurations and personalities.

    This is the main entry point for loading all configuration. It handles
    loading from providers.toml, applying overrides from config.toml, and
    loading personality definitions from personalities.toml.

    Returns:
        Tuple of (agent_configs, personalities).
    """
    providers = load_providers()
    overrides = load_config_overrides()
    personalities_data = load_personalities_data()
    agent_configs = build_agent_configs(providers, overrides)
    personalities = build_personalities(personalities_data)
    return agent_configs, personalities
