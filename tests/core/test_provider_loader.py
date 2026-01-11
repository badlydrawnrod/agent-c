from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentc.core.provider_loader import (
    build_model,
    get_default_provider_dirs,
    load_providers,
)
from agentc.core.types import BackendConfig, ModelConfig


def test_get_default_provider_dirs(tmp_path: Path) -> None:
    """Verify default provider directories are correct and in order."""

    with patch("pathlib.Path.home", return_value=tmp_path / "home"):
        dirs = get_default_provider_dirs()

    assert len(dirs) >= 3
    assert dirs[0] == Path(".agentc")
    assert dirs[1] == tmp_path / "home" / ".agentc"
    assert "agentc" in str(dirs[-1])


def test_load_providers_returns_backends_and_models() -> None:
    """Default load returns at least one backend and model preset."""

    backends, models = load_providers()

    assert backends
    assert models
    assert "ollama" in backends
    assert "ollama-gpt-oss-120b" in models
    assert models["ollama-gpt-oss-120b"].backend == "ollama"


def test_load_providers_merges_with_priority(tmp_path: Path) -> None:
    """Higher priority directories override backends and models by name."""

    low_dir = tmp_path / "low"
    high_dir = tmp_path / "high"
    low_dir.mkdir()
    high_dir.mkdir()

    (low_dir / "providers.toml").write_text(
        """
[backends.ollama]
provider_cls = "pydantic_ai.providers.ollama.OllamaProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
base_url = "http://low"

[backends.other]
provider_cls = "OtherProvider"
model_cls = "OtherModel"

[models.local]
backend = "ollama"
model_name = "ollama-low"
params = {temperature = 0.5}

[models.other-model]
backend = "other"
model_name = "something"
        """,
        encoding="utf-8",
    )

    (high_dir / "providers.toml").write_text(
        """
[backends.ollama]
provider_cls = "pydantic_ai.providers.ollama.OllamaProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
base_url = "http://high"

[models.local]
backend = "ollama"
model_name = "ollama-high"
params = {temperature = 0.1}
        """,
        encoding="utf-8",
    )

    backends, models = load_providers([high_dir, low_dir])

    assert backends["ollama"].base_url == "http://high"
    assert models["local"].model_name == "ollama-high"
    assert models["local"].params["temperature"] == 0.1

    # Lower priority entries still present
    assert "other" in backends
    assert "other-model" in models


def test_build_model_prefers_model_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model-specific api_key_env/base_url override backend settings and params pass through."""

    backend = BackendConfig(
        name="backend",
        provider_cls_path="provider.Path",
        model_cls_path="model.Path",
        api_key_env="BACKEND_KEY",
        base_url="http://backend",
    )
    model = ModelConfig(
        name="preset",
        backend="backend",
        model_name="model-str",
        api_key_env="MODEL_KEY",
        base_url="http://model",
        params={"temperature": 0.3},
    )

    mock_provider_cls = MagicMock()
    mock_model_cls = MagicMock()

    def get_class_side_effect(path: str) -> MagicMock:
        if path == backend.provider_cls_path:
            return mock_provider_cls
        if path == backend.model_cls_path:
            return mock_model_cls
        raise AssertionError("Unexpected class path")

    monkeypatch.setenv("MODEL_KEY", "model-secret")
    monkeypatch.setenv("BACKEND_KEY", "backend-secret")

    with patch("agentc.core.provider_loader._get_class", side_effect=get_class_side_effect):
        provider, _ = build_model(model, backend)

    mock_provider_cls.assert_called_once_with(
        api_key="model-secret",
        base_url="http://model",
    )
    mock_model_cls.assert_called_once()
    kwargs = mock_model_cls.call_args.kwargs
    assert kwargs["provider"] is provider
    assert kwargs["model_name"] == "model-str"
    assert kwargs["temperature"] == 0.3


def test_build_model_invalid_class_path() -> None:
    """Invalid import paths raise a ValueError."""

    backend = BackendConfig(
        name="backend",
        provider_cls_path="invalid.path.Class",
        model_cls_path="another.bad.Path",
    )
    model = ModelConfig(name="preset", backend="backend", model_name="foo")

    with pytest.raises(ValueError, match="Could not import class"):
        build_model(model, backend)
