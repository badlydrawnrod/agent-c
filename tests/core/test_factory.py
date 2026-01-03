import pytest
from pydantic_ai import Agent
from agentc.core.factory import create_agent


def test_create_agent():
    """Test that create_agent() returns a valid Agent instance."""
    agent = create_agent()
    assert isinstance(agent, Agent)


def test_create_agent_explicit_provider():
    """Test creating an agent with an explicit valid provider."""
    # We use 'ollama' as it's the default and should be available in TOML
    agent = create_agent(provider_name="ollama")
    assert isinstance(agent, Agent)


def test_create_agent_unknown_provider():
    """Test that an unknown provider raises ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        create_agent(provider_name="non-existent")

