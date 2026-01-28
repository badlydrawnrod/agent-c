"""Command execution tools for the Pydantic_AI backend."""

import asyncio
from asyncio.subprocess import PIPE

from pydantic_ai import ModelRetry

from ._shared import resolve_path, RunContext, RunDeps, ToolResult


async def _run_shell_command(command: str, cwd: str | None = None) -> tuple[str, int]:
    """Run a shell command asynchronously and capture output plus return code."""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=PIPE,
        stderr=PIPE,
        cwd=cwd,
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode() if stdout else ""
    error = stderr.decode() if stderr else ""
    return output + error, process.returncode if process.returncode is not None else 1


async def run_command(ctx: RunContext[RunDeps], command: str, cwd: str | None = None) -> ToolResult:
    """Execute a shell command inside the allowed workspace."""
    try:
        base = resolve_path(cwd or ".", ctx.deps) if cwd else None
        output, returncode = await _run_shell_command(command, str(base) if base else None)
        success = returncode == 0
        if success:
            return ToolResult(success=True, content=output)
        return ToolResult(success=False, content=output, error=output)
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))
