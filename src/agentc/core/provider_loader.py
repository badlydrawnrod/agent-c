"""
Provider loading and model building for Agent C Next.
"""

from importlib import import_module
from pathlib import Path
from typing import Any

import os
import tomllib

from .types import ProviderConfig


def _load_single_file(path: Path) -> dict[str, ProviderConfig]:
    """Load providers from a single TOML file."""
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

def get_default_provider_dirs() -> list[Path]:
    """Return provider directories in priority order: repo, user, bundled.
    
    Priority:
    1. Repo providers (.agentc/providers.toml)
    2. User providers (~/.agentc/providers.toml)
    3. Bundled providers (package/providers.toml)
    """
    from .config import DEFAULT_PROVIDER_DIRS
    return [
        *DEFAULT_PROVIDER_DIRS,
        Path.home() / ".agentc",
        Path(__file__).parent.parent,
    ]

def load_providers(dirs: list[Path] | None = None) -> dict[str, ProviderConfig]:
    """Load and merge providers from multiple directories.
    
    Providers discovered in earlier directories in the list take precedence
    over those with the same name in later directories.
    
    Args:
        dirs: List of directories to search. Defaults to get_default_provider_dirs().
        
    Returns:
        Dictionary of provider name to ProviderConfig.
    """
    if dirs is None:
        dirs = get_default_provider_dirs()
    
    merged: dict[str, ProviderConfig] = {}
    
    # Process in reverse order so higher priority (earlier in list) overrides lower priority
    for directory in reversed(dirs):
        path = directory / "providers.toml" if directory.is_dir() else directory
        if path.exists():
            merged |= _load_single_file(path)
            
    if not merged:
        # Fallback to raising error if absolutely nothing loaded and we expected something
        # checks if we are running from default paths or custom
        default_bundled = Path(__file__).parent.parent / "providers.toml"
        if not default_bundled.exists():
             raise FileNotFoundError("Bundled providers.toml not found")

    return merged


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
