"""Command execution tools for Agent C.

Provides tools for running shell commands asynchronously with
proper stdout/stderr capture and error handling.
"""

import asyncio

from ._shared import RunContext, RunDeps, ToolResult


async def run_command(ctx: RunContext[RunDeps], command: str) -> ToolResult:
    """Run a shell command asynchronously and return combined stdout+stderr.

    - Uses asyncio.create_subprocess_shell with stdin piped to avoid stealing the UI terminal.
    - Returns captured output (stdout then stderr) trimmed; if empty, returns a default success message.
    - On failure, returns an error string.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,  # Or DEVNULL if you prefer.
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = (stdout.decode() + stderr.decode()).strip()
        content = output or "Command executed successfully with no output."
        return ToolResult(success=process.returncode == 0, content=content)
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


__all__ = ["run_command"]
