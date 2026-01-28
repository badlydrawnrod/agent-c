"""Tests for PydanticAISessionFactory."""

from pathlib import Path

import pytest

from agentc.core.backends.pydantic_ai.loop import AgentSession
from agentc.core.backends.pydantic_ai.session_factory import PydanticAISessionFactory
from agentc.core.command_types import SessionConfig
from agentc.core.deps import RunDeps


@pytest.mark.anyio
async def test_pydantic_session_factory_creates_session() -> None:
    """Test that factory creates a valid AgentSession."""
    factory = PydanticAISessionFactory()
    config = SessionConfig(
        model_name=None,
        clear_history=True,
        skill_dirs=None,
        deps=RunDeps(root_dirs=[Path.cwd()]),
    )

    session = await factory.create_session(config)

    assert isinstance(session, AgentSession)
    assert session.history == []


@pytest.mark.anyio
async def test_pydantic_session_factory_with_model_override() -> None:
    """Test that factory respects model_name override."""
    factory = PydanticAISessionFactory()
    config = SessionConfig(
        model_name="ollama-gpt-oss-120b",
        clear_history=True,
    )

    session = await factory.create_session(config)

    assert isinstance(session, AgentSession)


@pytest.mark.anyio
async def test_pydantic_session_factory_unknown_model_raises() -> None:
    """Test that unknown model raises ValueError."""
    factory = PydanticAISessionFactory()
    config = SessionConfig(model_name="nonexistent-model")

    with pytest.raises(ValueError, match="Unknown model preset"):
        await factory.create_session(config)
