"""Tests for command parsing and handling."""

import pytest

from agentc_legacy.core.commands import CommandHandler, CommandType


@pytest.fixture
def handler() -> CommandHandler:
    """Create a command handler with test personalities."""
    return CommandHandler(
        {
            "coder": {"description": "Code expert"},
            "reviewer": {"description": "Code reviewer"},
            "debugger": {"description": "Debugging expert"},
        }
    )


class TestCommandParsing:
    """Test command parsing functionality."""

    def test_normal_input(self, handler: CommandHandler) -> None:
        """Regular input should be parsed as NORMAL_INPUT."""
        result = handler.parse("hello world")
        assert result.command_type == CommandType.NORMAL_INPUT
        assert result.args == {}

    def test_empty_input(self, handler: CommandHandler) -> None:
        """Empty input should be NORMAL_INPUT."""
        result = handler.parse("")
        assert result.command_type == CommandType.NORMAL_INPUT

    def test_whitespace_only(self, handler: CommandHandler) -> None:
        """Whitespace-only input should be NORMAL_INPUT."""
        result = handler.parse("   \t  ")
        assert result.command_type == CommandType.NORMAL_INPUT

    def test_clear_command(self, handler: CommandHandler) -> None:
        """Parse /clear command."""
        result = handler.parse("/clear")
        assert result.command_type == CommandType.CLEAR
        assert result.args == {}

    def test_reset_command(self, handler: CommandHandler) -> None:
        """/reset is alias for /clear."""
        result = handler.parse("/reset")
        assert result.command_type == CommandType.CLEAR
        assert result.args == {}

    def test_exit_command(self, handler: CommandHandler) -> None:
        """Parse /exit command."""
        result = handler.parse("/exit")
        assert result.command_type == CommandType.EXIT
        assert result.args == {}

    def test_quit_command(self, handler: CommandHandler) -> None:
        """/quit is alias for /exit."""
        result = handler.parse("/quit")
        assert result.command_type == CommandType.EXIT

    def test_bye_command(self, handler: CommandHandler) -> None:
        """/bye is alias for /exit."""
        result = handler.parse("/bye")
        assert result.command_type == CommandType.EXIT

    def test_personality_switch_valid(self, handler: CommandHandler) -> None:
        """Parse valid personality switch."""
        result = handler.parse("/personality reviewer")
        assert result.command_type == CommandType.PERSONALITY_SWITCH
        assert result.args == {"personality": "reviewer"}

    def test_personality_switch_case_insensitive(self, handler: CommandHandler) -> None:
        """Personality switch should be case-insensitive."""
        result = handler.parse("/PERSONALITY REVIEWER")
        assert result.command_type == CommandType.PERSONALITY_SWITCH
        assert result.args == {"personality": "reviewer"}

    def test_personality_switch_with_spaces(self, handler: CommandHandler) -> None:
        """Personality switch should handle extra spaces."""
        result = handler.parse("/personality   reviewer")
        assert result.command_type == CommandType.PERSONALITY_SWITCH
        assert result.args == {"personality": "reviewer"}

    def test_personality_switch_invalid(self, handler: CommandHandler) -> None:
        """Invalid personality should return UNKNOWN."""
        result = handler.parse("/personality invalid")
        assert result.command_type == CommandType.UNKNOWN
        assert "Unknown personality" in result.args["error"]
        assert result.args["input"] == "/personality invalid"

    def test_unknown_command(self, handler: CommandHandler) -> None:
        """Unknown slash command should be UNKNOWN."""
        result = handler.parse("/unknown")
        assert result.command_type == CommandType.UNKNOWN
        assert "Unknown command" in result.args["error"]

    def test_command_case_insensitive(self, handler: CommandHandler) -> None:
        """Commands should be case-insensitive."""
        result1 = handler.parse("/CLEAR")
        result2 = handler.parse("/Clear")
        result3 = handler.parse("/clear")
        assert result1.command_type == CommandType.CLEAR
        assert result2.command_type == CommandType.CLEAR
        assert result3.command_type == CommandType.CLEAR

    def test_slash_at_end_of_normal_input(self, handler: CommandHandler) -> None:
        """Text that contains slash but doesn't start with it should be normal input."""
        result = handler.parse("ask about forward slashes / in code")
        assert result.command_type == CommandType.NORMAL_INPUT


class TestCommandIntegration:
    """Test command handling in context."""

    def test_personality_switch_flow(self, handler: CommandHandler) -> None:
        """Simulate switching personalities."""
        # Start with normal input
        result1 = handler.parse("write some code")
        assert result1.command_type == CommandType.NORMAL_INPUT

        # Switch personality
        result2 = handler.parse("/personality reviewer")
        assert result2.command_type == CommandType.PERSONALITY_SWITCH
        assert result2.args["personality"] == "reviewer"

        # More normal input
        result3 = handler.parse("review this code")
        assert result3.command_type == CommandType.NORMAL_INPUT

    def test_clear_preserves_personality(self, handler: CommandHandler) -> None:
        """Clearing context shouldn't change personality."""
        result = handler.parse("/clear")
        assert result.command_type == CommandType.CLEAR
        # No personality info in result - personality unchanged elsewhere

    def test_multiple_personalities(self, handler: CommandHandler) -> None:
        """Test switching between multiple personalities."""
        assert handler.parse("/personality coder").command_type == (
            CommandType.PERSONALITY_SWITCH
        )
        assert handler.parse("/personality reviewer").command_type == (
            CommandType.PERSONALITY_SWITCH
        )
        assert handler.parse("/personality debugger").command_type == (
            CommandType.PERSONALITY_SWITCH
        )

    def test_error_messages_contain_details(self, handler: CommandHandler) -> None:
        """Error messages should include the invalid input."""
        result = handler.parse("/personality nonexistent")
        assert result.command_type == CommandType.UNKNOWN
        assert "nonexistent" in result.args["error"]
        assert result.args["input"] == "/personality nonexistent"

    def test_personality_name_extracted_correctly(
        self, handler: CommandHandler
    ) -> None:
        """Personality name should be extracted from command."""
        # Different personality names
        for personality in ["coder", "reviewer", "debugger"]:
            result = handler.parse(f"/personality {personality}")
            assert result.command_type == CommandType.PERSONALITY_SWITCH
            assert result.args["personality"] == personality
