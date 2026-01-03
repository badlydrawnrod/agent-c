import asyncio

from pydantic_ai import ToolDenied

from agentc_legacy.core.runner import AgentRunner


class _FakeCall:
    def __init__(self, tool_name, tool_call_id, args):
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        self.args = args


class _FakeDeferred:
    def __init__(self, approvals):
        self.approvals = approvals


def test_approval_handler_used_when_callbacks_missing():
    # When no callbacks are provided, tool approvals should default to
    # denial (guarding against headless accidental execution).
    runner = AgentRunner(None, "", [], None)

    fake = _FakeDeferred([_FakeCall("tool", "call-1", {"x": 1})])

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(runner._collect_tool_approvals(fake))
    finally:
        loop.close()

    # We expect a ToolDenied result for the approval entry.
    assert "call-1" in res.approvals
    assert isinstance(res.approvals["call-1"], ToolDenied)
