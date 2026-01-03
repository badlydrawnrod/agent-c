from agentc.core.tool_parsing import parse_tool_args


def test_parse_tool_args_string():
    """Test parsing a JSON string into a dictionary."""
    assert parse_tool_args('{"a": 1, "b": "test"}') == {"a": 1, "b": "test"}


def test_parse_tool_args_dict():
    """Test that a dict argument passes through unchanged."""
    args = {"a": 1, "b": "test"}
    assert parse_tool_args(args) == args


def test_parse_tool_args_invalid():
    """Test that invalid JSON is wrapped in a dict with 'value' key."""
    assert parse_tool_args('invalid json') == {"value": "invalid json"}
