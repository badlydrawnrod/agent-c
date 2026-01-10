import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os
import tomllib
from agentc.core.provider_loader import load_providers, build_model, get_default_provider_dirs
from agentc.core.types import ProviderConfig
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

def test_get_default_provider_dirs(tmp_path):
    """Verify default provider directories are correct and in order."""
    with patch("pathlib.Path.home", return_value=tmp_path / "home"):
        dirs = get_default_provider_dirs()
        
    assert len(dirs) >= 3
    # Repo-local first
    assert dirs[0] == Path(".agentc")
    # User-home second
    assert dirs[1] == tmp_path / "home" / ".agentc"
    # Bundled last
    assert "agentc" in str(dirs[-1])

def test_load_providers_returns_expected_count():
    """Verify that load_providers returns bundled providers by default."""
    providers = load_providers()
    assert len(providers) >= 1
    assert "ollama" in providers

def test_load_providers_merges_with_priority(tmp_path):
    """Verify that higher priority sources override lower priority ones."""
    # Create low priority config (mock bundled)
    low_priority_dir = tmp_path / "low"
    low_priority_dir.mkdir()
    (low_priority_dir / "providers.toml").write_text("""
[ollama]
provider_cls = "pydantic_ai.providers.ollama.OllamaProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
model_name = "low-priority-model"

[other]
provider_cls = "Other"
model_cls = "OtherModel"
model_name = "other-model"
    """, encoding="utf-8")

    # Create high priority config (mock repo)
    high_priority_dir = tmp_path / "high"
    high_priority_dir.mkdir()
    (high_priority_dir / "providers.toml").write_text("""
[ollama]
provider_cls = "pydantic_ai.providers.ollama.OllamaProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
model_name = "high-priority-model"
    """, encoding="utf-8")

    # Load with explicit order: High, then Low
    # Current implementation: earlier in list = higher priority
    # So we pass [High, Low] -> High overrides Low
    dirs = [high_priority_dir, low_priority_dir]
    providers = load_providers(dirs)
    
    # Check override
    assert providers["ollama"].model_name == "high-priority-model"
    # Check merge (preserved from low priority)
    assert providers["other"].model_name == "other-model"

def test_load_providers_skips_missing_files(tmp_path):
    """Verify that execution continues if a path doesn't exist."""
    # Provide a non-existent dir and a valid one
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    (valid_dir / "providers.toml").write_text("""
[test]
provider_cls = "Test"
model_cls = "TestModel"
model_name = "test"
    """, encoding="utf-8")
    
    dirs = [tmp_path / "missing", valid_dir]
    providers = load_providers(dirs)
    
    assert "test" in providers

def test_build_model_ollama():
    """Verify that build_model instantiates correct types for Ollama."""
    providers = load_providers()
    if "ollama" not in providers:
        pytest.skip("Ollama provider not found in default config")
        
    ollama_config = providers["ollama"]
    provider, model = build_model(ollama_config)
    
    assert isinstance(provider, OllamaProvider)
    assert isinstance(model, OpenAIChatModel)

def test_build_model_base_url():
    """Verify base_url is passed to provider."""
    config = ProviderConfig(
        name="test",
        provider_cls_path="pydantic_ai.providers.openai.OpenAIProvider",
        model_cls_path="pydantic_ai.models.openai.OpenAIChatModel",
        model_name="test",
        base_url="http://custom.url"
    )
    
    with patch("agentc.core.provider_loader._get_class") as mock_get_class:
        mock_provider_cls = MagicMock()
        mock_model_cls = MagicMock()
        
        def get_class_side_effect(path):
            if path == config.provider_cls_path:
                return mock_provider_cls
            return mock_model_cls
            
        mock_get_class.side_effect = get_class_side_effect
        
        build_model(config)
        
        # Verify provider was intialized with base_url
        mock_provider_cls.assert_called_once()
        call_kwargs = mock_provider_cls.call_args.kwargs
        assert call_kwargs.get("base_url") == "http://custom.url"

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
