from pydantic_ai import Agent
from agentc_next.core.factory import create_agent


def test_create_agent():
    """Test that create_agent() returns a valid Agent instance."""
    agent = create_agent()
    assert isinstance(agent, Agent)
