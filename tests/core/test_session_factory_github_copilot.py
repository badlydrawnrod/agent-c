"""Tests for GhCopilotSessionFactory."""

from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from agentc.core.backends.github_copilot.loop import GhAgentSession
from agentc.core.backends.github_copilot.session_factory import GhCopilotSessionFactory
from agentc.core.command_types import SessionConfig


@pytest.mark.anyio
async def test_gh_session_factory_creates_session() -> None:
    """Test that factory creates a valid GhAgentSession."""
    # Mock CopilotClient
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    # Create base config
    base_config = {
        "model": "gpt-4",
        "skill_directories": ["/default/skills"],
        "streaming": True,
        "system_message": "You are a helpful assistant",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(
        model_name=None,
        clear_history=True,
        skill_dirs=None,
    )
    
    session = await factory.create_session(config)
    
    assert isinstance(session, GhAgentSession)
    mock_client.create_session.assert_called_once()


@pytest.mark.anyio
async def test_gh_session_factory_with_model_override() -> None:
    """Test that factory respects model_name override."""
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": ["/default/skills"],
        "streaming": True,
        "system_message": "You are a helpful assistant",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(
        model_name="gpt-4o",
        clear_history=True,
    )
    
    session = await factory.create_session(config)
    
    assert isinstance(session, GhAgentSession)
    
    # Verify the model override was passed to create_session
    call_args = mock_client.create_session.call_args
    session_config = call_args[0][0]
    assert session_config["model"] == "gpt-4o"


@pytest.mark.anyio
async def test_gh_session_factory_with_skill_dirs_override() -> None:
    """Test that factory respects skill_dirs override."""
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": ["/default/skills"],
        "streaming": True,
        "system_message": "You are a helpful assistant",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    custom_skill_dirs = [Path("/custom/skills"), Path("/another/skills")]
    config = SessionConfig(
        model_name=None,
        clear_history=True,
        skill_dirs=custom_skill_dirs,
    )
    
    session = await factory.create_session(config)
    
    assert isinstance(session, GhAgentSession)
    
    # Verify skill directories override
    call_args = mock_client.create_session.call_args
    session_config = call_args[0][0]
    assert session_config["skill_directories"] == [str(d) for d in custom_skill_dirs]


@pytest.mark.anyio
async def test_gh_session_factory_uses_base_config_defaults() -> None:
    """Test that factory uses base config when no overrides provided."""
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    base_config = {
        "model": "gpt-4-turbo",
        "skill_directories": ["/base/skills"],
        "streaming": True,
        "system_message": "Base system message",
        "on_permission_request": MagicMock(),
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(
        model_name=None,
        clear_history=True,
        skill_dirs=None,
    )
    
    session = await factory.create_session(config)
    
    assert isinstance(session, GhAgentSession)
    
    # Verify base config is used
    call_args = mock_client.create_session.call_args
    session_config = call_args[0][0]
    assert session_config["model"] == "gpt-4-turbo"
    assert session_config["skill_directories"] == ["/base/skills"]
    assert session_config["streaming"] is True
    assert session_config["system_message"] == "Base system message"
    assert session_config["on_permission_request"] is base_config["on_permission_request"]


@pytest.mark.anyio
async def test_gh_session_factory_destroys_old_session() -> None:
    """Test that factory destroys old session before creating new one."""
    mock_client = MagicMock()
    
    # Create two different mock sessions
    first_session = MagicMock()
    first_session.destroy = AsyncMock()
    second_session = MagicMock()
    second_session.destroy = AsyncMock()
    
    mock_client.create_session = AsyncMock(side_effect=[first_session, second_session])
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": [],
        "streaming": True,
        "system_message": "Test",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(model_name=None, clear_history=True)
    
    # Create first session
    session1 = await factory.create_session(config)
    assert isinstance(session1, GhAgentSession)
    first_session.destroy.assert_not_called()
    
    # Create second session - should destroy first
    session2 = await factory.create_session(config)
    assert isinstance(session2, GhAgentSession)
    first_session.destroy.assert_called_once()
    second_session.destroy.assert_not_called()


@pytest.mark.anyio
async def test_gh_session_factory_handles_destroy_error() -> None:
    """Test that factory handles errors during session destruction gracefully."""
    mock_client = MagicMock()
    
    first_session = MagicMock()
    # Make destroy raise an exception
    first_session.destroy = AsyncMock(side_effect=Exception("Destroy failed"))
    second_session = MagicMock()
    second_session.destroy = AsyncMock()
    
    mock_client.create_session = AsyncMock(side_effect=[first_session, second_session])
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": [],
        "streaming": True,
        "system_message": "Test",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(model_name=None, clear_history=True)
    
    # Create first session
    await factory.create_session(config)
    
    # Create second session - should handle destroy error gracefully
    session2 = await factory.create_session(config)
    assert isinstance(session2, GhAgentSession)
    first_session.destroy.assert_called_once()


@pytest.mark.anyio
async def test_gh_session_factory_cleanup() -> None:
    """Test that cleanup properly destroys the current session."""
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": [],
        "streaming": True,
        "system_message": "Test",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(model_name=None, clear_history=True)
    
    # Create a session
    await factory.create_session(config)
    
    # Cleanup should destroy it
    await factory.cleanup()
    mock_copilot_session.destroy.assert_called_once()


@pytest.mark.anyio
async def test_gh_session_factory_cleanup_without_session() -> None:
    """Test that cleanup works when no session exists."""
    mock_client = MagicMock()
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": [],
        "streaming": True,
        "system_message": "Test",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    
    # Cleanup without creating a session should not raise
    await factory.cleanup()


@pytest.mark.anyio
async def test_gh_session_factory_cleanup_handles_error() -> None:
    """Test that cleanup handles destruction errors gracefully."""
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock(side_effect=Exception("Cleanup failed"))
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    base_config = {
        "model": "gpt-4",
        "skill_directories": [],
        "streaming": True,
        "system_message": "Test",
        "on_permission_request": None,
    }
    
    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(model_name=None, clear_history=True)
    
    # Create a session
    await factory.create_session(config)
    
    # Cleanup should handle error gracefully and not raise
    await factory.cleanup()
    mock_copilot_session.destroy.assert_called_once()


@pytest.mark.anyio
async def test_gh_session_factory_registers_user_input_handler() -> None:
    """Test that factory registers a user input handler in the SDK config."""
    mock_client = MagicMock()
    mock_copilot_session = MagicMock()
    mock_copilot_session.destroy = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)

    base_config = {
        "model": "gpt-4",
        "skill_directories": ["/default/skills"],
        "streaming": True,
        "system_message": "You are a helpful assistant",
        "on_permission_request": None,
    }

    factory = GhCopilotSessionFactory(mock_client, base_config)
    config = SessionConfig(model_name=None, clear_history=True)

    session = await factory.create_session(config)
    assert isinstance(session, GhAgentSession)

    # Verify on_user_input_request was set in the SDK config
    call_args = mock_client.create_session.call_args
    session_config = call_args[0][0]
    assert "on_user_input_request" in session_config
    assert callable(session_config["on_user_input_request"])
