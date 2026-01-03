import pytest
from agentc_next.core.commands import CommandParser
from agentc_next.core.types import CommandType, ProviderConfig

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
