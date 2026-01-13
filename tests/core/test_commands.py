from unittest.mock import MagicMock, patch

import pytest

from agentc.core.commands import CommandParser, execute_command
from agentc.core.types import CommandResult, CommandType, ModelConfig


@pytest.fixture
def mock_models():
    return {
        "ollama-gpt-oss-120b": ModelConfig(
            name="ollama-gpt-oss-120b",
            backend="ollama",
            model_name="gpt-oss",
        ),
        "claude": ModelConfig(
            name="claude",
            backend="anthropic",
            model_name="claude-3",
        ),
    }


@pytest.fixture
def parser(mock_models):
    return CommandParser(mock_models)

def test_parse_normal_input(parser):
    result = parser.parse("hello agent")
    assert result.command_type == CommandType.NORMAL_INPUT
    assert result.args == {}

def test_parse_empty_input(parser):
    result = parser.parse("  ")
    assert result.command_type == CommandType.NORMAL_INPUT

def test_parse_exit(parser):
    for cmd in ["/exit", "/quit", "/bye"]:
        result = parser.parse(cmd)
        assert result.command_type == CommandType.EXIT

def test_parse_clear(parser):
    for cmd in ["/clear", "/reset"]:
        result = parser.parse(cmd)
        assert result.command_type == CommandType.CLEAR

def test_parse_model_switch_success(parser):
    result = parser.parse("/model claude")
    assert result.command_type == CommandType.MODEL_SWITCH
    assert result.args["model"] == "claude"

def test_parse_model_switch_unknown(parser):
    result = parser.parse("/model unknown-llm")
    assert result.command_type == CommandType.UNKNOWN
    assert "Unknown model" in result.args["error"]

def test_parse_unknown_command(parser):
    result = parser.parse("/invalid command")
    assert result.command_type == CommandType.UNKNOWN
    assert "Unknown command" in result.args["error"]

def test_parse_case_insensitivity(parser):
    result = parser.parse("/EXIT")
    assert result.command_type == CommandType.EXIT
    
    result = parser.parse("/MODEL Claude")
    assert result.command_type == CommandType.MODEL_SWITCH
    assert result.args["model"] == "claude"

def test_parse_help(parser):
    for cmd in ["/help", "/?"]:
        result = parser.parse(cmd)
        assert result.command_type == CommandType.HELP

def test_command_metadata_structure():
    from agentc.core.commands import COMMAND_METADATA
    for cmd in COMMAND_METADATA:
        assert "command" in cmd
        assert "description" in cmd


# --- Tests for execute_command ---


class TestExecuteCommand:
    """Tests for the execute_command function."""

    @patch("agentc.core.commands.create_agent")
    def test_execute_clear_returns_effect(self, mock_create_agent):
        """CLEAR command should return effect with new session and notification."""
        mock_create_agent.return_value = MagicMock()
        
        result = CommandResult(CommandType.CLEAR, {})
        effect = execute_command(result)

        assert effect is not None
        assert effect.new_session is not None
        assert effect.notification == "Conversation cleared"
        assert effect.should_reset_ui is True
        mock_create_agent.assert_called_once()

    @patch("agentc.core.commands.create_agent")
    def test_execute_model_switch_returns_effect(self, mock_create_agent):
        """MODEL_SWITCH command should return effect with new session."""
        mock_create_agent.return_value = MagicMock()

        result = CommandResult(CommandType.MODEL_SWITCH, {"model": "claude"})
        effect = execute_command(result)

        assert effect is not None
        assert effect.new_session is not None
        assert effect.notification == "Switched to model: claude"
        assert effect.should_reset_ui is True
        
        # Verify create_agent was called with correct model
        call_kwargs = mock_create_agent.call_args.kwargs
        assert call_kwargs.get("model_name") == "claude"

    def test_execute_exit_returns_none(self):
        """EXIT command should return None (handled by UI)."""
        result = CommandResult(CommandType.EXIT, {})
        effect = execute_command(result)

        assert effect is None

    def test_execute_unknown_returns_none(self):
        """UNKNOWN command should return None (handled by UI)."""
        result = CommandResult(
            CommandType.UNKNOWN,
            {"input": "/invalid", "error": "Unknown command"},
        )
        effect = execute_command(result)

        assert effect is None

    def test_execute_normal_input_returns_none(self):
        """NORMAL_INPUT should return None (not a command)."""
        result = CommandResult(CommandType.NORMAL_INPUT, {})
        effect = execute_command(result)

        assert effect is None

    def test_execute_help_returns_effect(self):
        """HELP command should return effect with notification listing commands."""
        result = CommandResult(CommandType.HELP, {})
        effect = execute_command(result)

        assert effect is not None
        assert "Available Commands" in effect.notification
        assert "/clear" in effect.notification
        assert "/help" in effect.notification
        assert effect.should_reset_ui is False

    @patch("agentc.core.commands.create_agent")
    def test_execute_model_switch_missing_api_key(self, mock_create_agent):
        """MODEL_SWITCH with missing API key should return error notification."""
        from agentc.core.provider_loader import MissingAPIKeyError

        mock_create_agent.side_effect = MissingAPIKeyError(
            "GOOGLE_API_KEY", "gemini-flash"
        )

        result = CommandResult(CommandType.MODEL_SWITCH, {"model": "gemini-flash"})
        effect = execute_command(result)

        assert effect is not None
        assert effect.new_session is None
        assert "GOOGLE_API_KEY" in effect.notification
        assert effect.should_reset_ui is False

