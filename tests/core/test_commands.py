import pytest
from agentc.core.commands import CommandParser, execute_command
from agentc.core.types import CommandResult, CommandType, ProviderConfig

@pytest.fixture
def mock_providers():
    return {
        "ollama": ProviderConfig(
            name="ollama",
            provider_cls_path="p.OllamaProvider",
            model_cls_path="m.OpenAIChatModel",
            model_name="test"
        ),
        "anthropic": ProviderConfig(
            name="anthropic",
            provider_cls_path="p.AnthropicProvider",
            model_cls_path="m.AnthropicModel",
            model_name="claude-3"
        )
    }

@pytest.fixture
def parser(mock_providers):
    return CommandParser(mock_providers)

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

def test_parse_provider_switch_success(parser):
    result = parser.parse("/provider anthropic")
    assert result.command_type == CommandType.PROVIDER_SWITCH
    assert result.args["provider"] == "anthropic"

def test_parse_provider_switch_unknown(parser):
    result = parser.parse("/provider unknown-llm")
    assert result.command_type == CommandType.UNKNOWN
    assert "Unknown provider" in result.args["error"]

def test_parse_unknown_command(parser):
    result = parser.parse("/invalid command")
    assert result.command_type == CommandType.UNKNOWN
    assert "Unknown command" in result.args["error"]

def test_parse_case_insensitivity(parser):
    result = parser.parse("/EXIT")
    assert result.command_type == CommandType.EXIT
    
    result = parser.parse("/PROVIDER Anthropic")
    assert result.command_type == CommandType.PROVIDER_SWITCH
    assert result.args["provider"] == "anthropic"

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

    def test_execute_clear_returns_effect(self):
        """CLEAR command should return effect with new session and notification."""
        result = CommandResult(CommandType.CLEAR, {})
        effect = execute_command(result)

        assert effect is not None
        assert effect.new_session is not None
        assert effect.notification == "Conversation cleared"
        assert effect.should_reset_ui is True

    def test_execute_provider_switch_returns_effect(self):
        """PROVIDER_SWITCH command should return effect with new session."""
        result = CommandResult(CommandType.PROVIDER_SWITCH, {"provider": "anthropic"})
        effect = execute_command(result)

        assert effect is not None
        assert effect.new_session is not None
        assert effect.notification == "Switched to provider: anthropic"
        assert effect.should_reset_ui is True

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
