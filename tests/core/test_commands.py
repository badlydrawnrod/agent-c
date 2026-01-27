import pytest

from agentc.core.commands import CommandParser, execute_command
from agentc.core.command_types import CommandResult, CommandType, SessionConfig


@pytest.fixture
def parser():
    return CommandParser()

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


def test_parse_model_switch_any_name(parser):
    """Test /model accepts any model name (validation happens in factory)."""
    result = parser.parse("/model any-model-name")
    assert result.command_type == CommandType.MODEL_SWITCH
    assert result.args["model"] == "any-model-name"

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

    def test_execute_clear_returns_effect(self):
        """CLEAR command should return effect with session config and notification."""
        result = CommandResult(CommandType.CLEAR, {})
        effect = execute_command(result)

        assert effect is not None
        assert effect.session_config is not None
        assert isinstance(effect.session_config, SessionConfig)
        assert effect.session_config.clear_history is True
        assert effect.notification == "Conversation cleared"
        assert effect.should_reset_ui is True

    def test_execute_model_switch_returns_effect(self):
        """MODEL_SWITCH command should return effect with session config."""
        result = CommandResult(CommandType.MODEL_SWITCH, {"model": "claude"})
        effect = execute_command(result)

        assert effect is not None
        assert effect.session_config is not None
        assert isinstance(effect.session_config, SessionConfig)
        assert effect.session_config.model_name == "claude"
        assert effect.session_config.clear_history is True
        assert effect.notification == "Switched to model: claude"
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


def test_session_config_structure():
    """Test SessionConfig dataclass structure."""
    from pathlib import Path

    from agentc.core.deps import RunDeps

    deps = RunDeps(root_dirs=[Path("/tmp")])
    config = SessionConfig(
        model_name="test-model",
        clear_history=True,
        skill_dirs=[Path("/skills")],
        deps=deps,
    )

    assert config.model_name == "test-model"
    assert config.clear_history is True
    assert config.skill_dirs == [Path("/skills")]
    assert config.deps == deps

