from types import SimpleNamespace


def test_discover_only_first_line():
    """ToolRegistry.discover() should only include the first line of each
    tool.description and trim surrounding whitespace.
    """
    from agentc.core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry._tools = [
        SimpleNamespace(name="tool1", description="first line\nsecond line\nthird"),
        SimpleNamespace(name="tool2", description=" single line "),
        SimpleNamespace(name="tool3", description=None),
    ]

    result = registry.discover()

    expected = "- tool1: first line\n- tool2: single line\n- tool3: "
    assert result == expected
