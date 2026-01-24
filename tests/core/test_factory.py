from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import Agent

from agentc.core.backends.pydantic_ai.factory import create_agent
from agentc.core.config_types import BackendConfig, ModelConfig


def test_create_agent_returns_agent() -> None:
    """Factory returns an Agent using the default model preset."""

    agent = create_agent()
    assert isinstance(agent, Agent)


def test_create_agent_explicit_model() -> None:
    """Factory builds using a provided model preset name."""

    agent = create_agent(model_name="ollama-gpt-oss-120b")
    assert isinstance(agent, Agent)


def test_create_agent_unknown_model() -> None:
    """Unknown model preset raises a ValueError."""

    with pytest.raises(ValueError, match="Unknown model preset"):
        create_agent(model_name="does-not-exist")


@patch("agentc.core.backends.pydantic_ai.factory.Agent")
@patch("agentc.core.backends.pydantic_ai.factory.load_providers")
@patch("agentc.core.backends.pydantic_ai.factory.build_model")
def test_create_agent_merges_params(
    mock_build_model: MagicMock, mock_load: MagicMock, mock_agent: MagicMock
) -> None:
    """Runtime overrides merge with preset params and override model name."""

    backend_cfg = BackendConfig(
        name="backend",
        provider_cls_path="provider.Path",
        model_cls_path="model.Path",
    )
    model_cfg = ModelConfig(
        name="preset",
        backend="backend",
        model_name="original-name",
        params={"temperature": 0.2},
    )

    mock_load.return_value = ({"backend": backend_cfg}, {"preset": model_cfg})
    model_instance = MagicMock()
    model_instance.provider = MagicMock()
    model_instance.model_name = "original-name"
    mock_build_model.return_value = (MagicMock(), model_instance)

    agent = create_agent(
        model_name="preset",
        override_model_name="override-name",
        top_p=0.8,
    )

    assert agent is mock_agent.return_value

    called_model_cfg, called_backend_cfg = mock_build_model.call_args.args
    assert called_backend_cfg is backend_cfg
    assert called_model_cfg.model_name == "override-name"
    assert called_model_cfg.params["temperature"] == 0.2
    assert called_model_cfg.params["top_p"] == 0.8

