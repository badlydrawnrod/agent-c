"""Tests for command execution tool (run_command)."""

import asyncio
from unittest.mock import MagicMock

from pydantic_ai import RunContext

from agentc.core.tools.execution import run_command
from agentc.core.types import RunDeps, ToolResult


def create_mock_context() -> RunContext[RunDeps]:
    """Create a mock RunContext for testing."""
    ctx = MagicMock(spec=RunContext)
    ctx.deps = RunDeps(root_dirs=[])
    return ctx


def test_run_command_success() -> None:
    """Test successful command execution."""
    ctx = create_mock_context()
    result = asyncio.run(run_command(ctx, "echo hello"))

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "hello" in result.content


def test_run_command_failure() -> None:
    """Test command execution failure."""
    ctx = create_mock_context()
    result = asyncio.run(run_command(ctx, "nonexistent_command_12345"))

    assert isinstance(result, ToolResult)
    assert result.success is False
