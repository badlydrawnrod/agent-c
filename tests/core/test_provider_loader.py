import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os
from agentc.core.provider_loader import load_providers, build_model
from agentc.core.types import ProviderConfig
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

def test_build_model_with_api_key():
    """Verify that API key is retrieved from environment and passed to provider."""
    config = ProviderConfig(
        name="test_openai",
        provider_cls_path="pydantic_ai.providers.openai.OpenAIProvider",
        model_cls_path="pydantic_ai.models.openai.OpenAIChatModel",
        model_name="gpt-4o",
        api_key_env="TEST_OPENAI_API_KEY"
    )

    with patch.dict(os.environ, {"TEST_OPENAI_API_KEY": "sk-test-key-123"}), \
         patch("agentc.core.provider_loader._get_class") as mock_get_class:
        
        # Mock the provider and model classes
        mock_provider_cls = MagicMock()
        mock_model_cls = MagicMock()
        
        # Configure _get_class to return our mocks
        def get_class_side_effect(path):
            if path == config.provider_cls_path:
                return mock_provider_cls
            if path == config.model_cls_path:
                return mock_model_cls
            return MagicMock()
            
        mock_get_class.side_effect = get_class_side_effect
        
        provider, model = build_model(config)
        
        # Verify provider was initialized with correct api_key
        mock_provider_cls.assert_called_once()
        call_kwargs = mock_provider_cls.call_args.kwargs
        assert call_kwargs.get("api_key") == "sk-test-key-123"

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
