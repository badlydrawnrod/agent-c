"""
Provider loading and model building for Agent C Next.
"""

from importlib import import_module
from pathlib import Path
from typing import Any

import os
import tomllib

from .types import ProviderConfig


def load_providers(path: Path | None = None) -> dict[str, ProviderConfig]:
    """Load providers from TOML file.

    Args:
        path: Path to providers.toml. Defaults to src/agentc_next/providers.toml.

    Returns:
        Dictionary of provider name to ProviderConfig.

    Raises:
        FileNotFoundError: If providers.toml is not found.
    """
    if path is None:
        path = Path(__file__).parent.parent / "providers.toml"

    if not path.exists():
        raise FileNotFoundError(f"Providers configuration not found at {path}")

    with path.open("rb") as f:
        data = tomllib.load(f)

    providers = {}
    for name, config in data.items():
        providers[name] = ProviderConfig(
            name=name,
            provider_cls_path=config["provider_cls"],
            model_cls_path=config["model_cls"],
            model_name=config["model_name"],
            api_key_env=config.get("api_key_env"),
            base_url=config.get("base_url"),
        )
    return providers


def _get_class(class_path: str) -> type:
    """Dynamically import a class from a module path."""
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise ValueError(f"Could not import class from {class_path}: {e}")


def build_model(config: ProviderConfig) -> tuple[Any, Any]:
    """Build provider and model instances from configuration.

    Returns:
        Tuple of (provider instance, model instance).
    """
    provider_cls = _get_class(config.provider_cls_path)
    model_cls = _get_class(config.model_cls_path)

    provider_kwargs = {}
    if config.api_key_env:
        api_key = os.getenv(config.api_key_env)
        if api_key:
            provider_kwargs["api_key"] = api_key
    if config.base_url:
        provider_kwargs["base_url"] = config.base_url

    provider = provider_cls(**provider_kwargs)
    model = model_cls(provider=provider, model_name=config.model_name)

    return provider, model
