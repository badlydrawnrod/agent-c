"""Provider and model loading for the Pydantic_AI backend."""

import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

import tomllib

from ...config import DEFAULT_PROVIDER_DIRS
from ...config_types import BackendConfig, ModelConfig


class MissingAPIKeyError(ValueError):
    """Raised when a required API key is not set in the environment."""

    def __init__(self, env_var: str, model_name: str):
        self.env_var = env_var
        self.model_name = model_name
        super().__init__(
            f"API key for model '{model_name}' not found. "
            f"Please set the {env_var} environment variable."
        )


def _load_single_file(path: Path) -> tuple[dict[str, BackendConfig], dict[str, ModelConfig]]:
    """Load backends and models from a single TOML file."""

    with path.open("rb") as f:
        data = tomllib.load(f)

    raw_backends = data.get("backends", {})
    raw_models = data.get("models", {})

    backends: dict[str, BackendConfig] = {}
    for name, config in raw_backends.items():
        backends[name] = BackendConfig(
            name=name,
            provider_cls_path=config["provider_cls"],
            model_cls_path=config["model_cls"],
            api_key_env=config.get("api_key_env"),
            base_url_env=config.get("base_url_env"),
            base_url=config.get("base_url"),
        )

    models: dict[str, ModelConfig] = {}
    for name, config in raw_models.items():
        params = config.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("Model params must be a table/dict of keyword arguments")

        models[name] = ModelConfig(
            name=name,
            backend=config["backend"],
            model_name=config["model_name"],
            api_key_env=config.get("api_key_env"),
            base_url_env=config.get("base_url_env"),
            base_url=config.get("base_url"),
            params=params,
        )

    return backends, models


def get_default_provider_dirs() -> list[Path]:
    """Return provider directories in priority order: repo, user, bundled."""

    return [
        *DEFAULT_PROVIDER_DIRS,
        Path.home() / ".agentc",
        Path(__file__).parent.parent.parent.parent,
    ]


def load_providers(
    dirs: list[Path] | None = None,
) -> tuple[dict[str, BackendConfig], dict[str, ModelConfig]]:
    """Load and merge backends and models from multiple directories.

    Entries discovered in earlier directories in the list take precedence
    over those with the same name in later directories.
    """

    if dirs is None:
        dirs = get_default_provider_dirs()

    merged_backends: dict[str, BackendConfig] = {}
    merged_models: dict[str, ModelConfig] = {}

    # Process in reverse order so higher priority (earlier in list) overrides lower priority
    for directory in reversed(dirs):
        path = directory / "providers.toml" if directory.is_dir() else directory
        if not path.exists():
            continue

        backends, models = _load_single_file(path)
        merged_backends |= backends
        merged_models |= models

    if not merged_backends or not merged_models:
        default_bundled = Path(__file__).parent.parent.parent.parent / "providers.toml"
        if not default_bundled.exists():
            raise FileNotFoundError("Bundled providers.toml not found")
        if not merged_backends:
            raise ValueError("No backends were loaded from any providers.toml file")
        raise ValueError("No models were loaded from any providers.toml file")

    return merged_backends, merged_models


def _get_class(class_path: str) -> type:
    """Dynamically import a class from a module path."""

    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise ValueError(f"Could not import class from {class_path}: {e}")


def build_model(
    model_config: ModelConfig,
    backend_config: BackendConfig,
) -> tuple[Any, Any]:
    """Build provider and model instances from configuration."""

    get_class = _get_class
    shim = sys.modules.get("agentc.core.provider_loader")
    if shim and hasattr(shim, "_get_class"):
        get_class = getattr(shim, "_get_class")

    provider_cls = get_class(backend_config.provider_cls_path)
    model_cls = get_class(backend_config.model_cls_path)

    api_key_env = model_config.api_key_env or backend_config.api_key_env
    base_url_env = model_config.base_url_env or backend_config.base_url_env
    base_url_from_env: str | None = None
    if base_url_env:
        base_url_from_env = os.getenv(base_url_env)

    base_url: str | None
    if base_url_from_env is not None:
        base_url = base_url_from_env
    else:
        base_url = model_config.base_url or backend_config.base_url

    provider_kwargs: dict[str, Any] = {}
    if api_key_env:
        api_key = os.getenv(api_key_env)
        if api_key:
            provider_kwargs["api_key"] = api_key
        else:
            raise MissingAPIKeyError(api_key_env, model_config.model_name)
    if base_url:
        provider_kwargs["base_url"] = base_url

    provider = provider_cls(**provider_kwargs)
    model = model_cls(
        provider=provider,
        model_name=model_config.model_name,
        **model_config.params,
    )

    return provider, model


__all__ = [
    "MissingAPIKeyError",
    "get_default_provider_dirs",
    "load_providers",
    "build_model",
    "_get_class",
]
