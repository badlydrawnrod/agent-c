import pytest
from pathlib import Path
from agentc_next.core.provider_loader import load_providers, build_model
from agentc_next.core.types import ProviderConfig
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

def test_load_providers_returns_expected_count():
    """Verify that load_providers parses all providers from the default TOML."""
    providers = load_providers()
    assert len(providers) >= 6
    assert "ollama" in providers
    assert "anthropic" in providers
    assert "openai" in providers

def test_load_providers_ollama_fields():
    """Spot-check Ollama configuration values."""
    providers = load_providers()
    ollama = providers["ollama"]
    assert ollama.name == "ollama"
    assert "OllamaProvider" in ollama.provider_cls_path
    assert "OpenAIChatModel" in ollama.model_cls_path
    assert ollama.base_url == "http://localhost:11434/v1"

def test_build_model_ollama():
    """Verify that build_model instantiates correct types for Ollama."""
    providers = load_providers()
    ollama_config = providers["ollama"]
    provider, model = build_model(ollama_config)
    
    assert isinstance(provider, OllamaProvider)
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == ollama_config.model_name

def test_load_providers_file_not_found():
    """Verify behavior when config file is missing."""
    with pytest.raises(FileNotFoundError):
        load_providers(Path("non_existent_file.toml"))

def test_build_model_invalid_path():
    """Verify error when class path is invalid."""
    config = ProviderConfig(
        name="bad",
        provider_cls_path="invalid.path.Class",
        model_cls_path="another.bad.Path",
        model_name="test"
    )
    with pytest.raises(ValueError, match="Could not import class"):
        build_model(config)
