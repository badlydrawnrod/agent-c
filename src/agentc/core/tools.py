"""
Tool implementations for Agent C Next.
"""

import asyncio
from datetime import datetime
from pathlib import Path
import shutil

import pathspec

from pydantic_ai import ModelRetry, RunContext

from .config import (
    BACKUP_SUFFIX,
    DEFAULT_IGNORE_PATTERNS,
    MAX_TOOL_OUTPUT_LINES,
    TEMP_SUFFIX,
)
from .types import RunDeps, ToolResult


def _resolve_path(path_str: str, deps: RunDeps, *, must_exist: bool = True) -> Path:
    """Resolve a path safely, ensuring it is within one of the allowed root paths."""
    candidate = Path(path_str).expanduser().resolve(strict=False)

    for root in deps.root_dirs:
        if candidate.is_relative_to(root.resolve()):
            if must_exist and not candidate.exists():
                raise ModelRetry(f"Path does not exist: {path_str}")
            return candidate

    raise ModelRetry(f"Path is outside allowed directories: {path_str}")


def _format_error(tool_name: str, message: str) -> str:
    """Return a consistently formatted error message for tool failures."""
    return f"[{tool_name}] Failed: {message}"


def _cat_n_format(text: str) -> str:
    """Return text with `cat -n` style line numbers, preserving trailing newline."""
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")
    numbered = [f"{i:6}\t{line}" for i, line in enumerate(lines, 1)]
    result = "\n".join(numbered)
    if trailing_newline:
        result += "\n"
    return result


def _write_text_atomic(path: Path, content: str) -> None:
    """Write text atomically via a temp file in the same directory."""
    temp_path = path.parent / f"{path.name}{TEMP_SUFFIX}"
    try:
        temp_path.write_text(content, encoding="utf-8")
        written = temp_path.read_text(encoding="utf-8")
        if written != content:
            raise ValueError("Write verification failed: content mismatch")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _create_backup(path: Path) -> Path:
    """Create a timestamped backup of the file alongside the original."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.parent / f"{path.name}{BACKUP_SUFFIX}.{timestamp}"
    shutil.copy2(path, backup_path)
    return backup_path


def _load_ignore_spec(base: Path) -> pathspec.PathSpec:
    """Load combined ignore patterns from defaults and .gitignore."""
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    gitignore_path = base / ".gitignore"
    if gitignore_path.is_file():
        patterns.extend(gitignore_path.read_text(encoding="utf-8").splitlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def list_files(ctx: RunContext[RunDeps], path: str = ".") -> ToolResult:
    """List entries in a directory inside the current working tree.

    - Path must be inside the current working directory; otherwise ModelRetry is raised.
    - Returns one entry per line, sorted case-insensitively; directories are suffixed with "/".
    """
    try:
        target = _resolve_path(path, ctx.deps)
        if not target.is_dir():
            raise ModelRetry(f"Path must be a directory: {path}")

        items = []
        for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            suffix = "/" if entry.is_dir() else ""
            items.append(f"{entry.name}{suffix}")

        content = "\n".join(items) if items else "Directory is empty."
        return ToolResult(success=True, content=content)
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def glob_paths(ctx: RunContext[RunDeps], pattern: str, path: str = ".") -> ToolResult:
    """Glob for files/directories under a base path, returning relative paths.

    - path must be a directory inside the current working directory; otherwise ModelRetry is raised.
    - Respects default ignore patterns and `.gitignore` if it exists in the base path.
    - pattern follows pathlib.rglob rules (supports "**" for recursion).
    - Returns newline-separated relative paths from the base path; directories end with a trailing slash.
    - Caps results at MAX_TOOL_OUTPUT_LINES; if truncated, a summary line is appended.
    """
    try:
        base = _resolve_path(path, ctx.deps)
        if not base.is_dir():
            raise ModelRetry(f"Path must be a directory: {path}")

        spec = _load_ignore_spec(base)

        matches: list[str] = []
        for entry in base.rglob(pattern):
            rel = entry.relative_to(base).as_posix()
            if entry.is_dir():
                rel += "/"

            # Skip entries that match ignore patterns.
            if spec.match_file(rel):
                continue

            matches.append(rel)

        if not matches:
            return ToolResult(success=True, content="No matches.")

        matches.sort()
        limit = MAX_TOOL_OUTPUT_LINES
        truncated = len(matches) > limit
        shown = matches[:limit]
        output = "\n".join(shown)
        if truncated:
            output += f"\n... {len(matches) - limit} more"
        return ToolResult(success=True, content=output)
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def search_files(ctx: RunContext[RunDeps], query: str, path: str = ".") -> ToolResult:
    """Recursively search for a substring in text files under a base path.

    - path must be a directory inside the current working directory; otherwise ModelRetry is raised.
    - Respects default ignore patterns and `.gitignore` if it exists in the base path.
    - Matches are case-sensitive substring checks on UTF-8 text (binary data is skipped via errors="ignore").
    - Returns relative paths from the base directory with `path:line: text`; results are sorted and capped at MAX_TOOL_OUTPUT_LINES with a summary line if truncated.
    - If no matches are found, returns "No matches.".
    """
    try:
        base = _resolve_path(path, ctx.deps)
        if not base.is_dir():
            raise ModelRetry(f"Path must be a directory: {path}")

        spec = _load_ignore_spec(base)

        matches: list[str] = []
        for file_path in base.rglob("*"):
            rel = file_path.relative_to(base).as_posix()
            if file_path.is_dir():
                rel += "/"

            # Skip files/dirs that match ignore patterns.
            if spec.match_file(rel):
                continue

            if not file_path.is_file():
                continue

            try:
                with file_path.open(encoding="utf-8", errors="ignore") as fh:
                    for line_no, line in enumerate(fh, 1):
                        if query in line:
                            matches.append(f"{rel}:{line_no}: {line.rstrip()}")
            except OSError:
                # Skip unreadable files.
                continue

        if not matches:
            return ToolResult(success=True, content="No matches.")

        matches.sort()
        limit = MAX_TOOL_OUTPUT_LINES
        truncated = len(matches) > limit
        output = "\n".join(matches[:limit])
        if truncated:
            output += f"\n... {len(matches) - limit} more"
        return ToolResult(success=True, content=output)
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def read_file(ctx: RunContext[RunDeps], path: str) -> ToolResult:
    """Read a UTF-8 text file and return cat -n style output.

    - Path must be inside the current working directory and must be a file; directories are rejected.
    - Output is line-numbered like `cat -n` (right-aligned 6-digit number, tab, then content); trailing newline is preserved.
    - Raises ModelRetry for invalid paths, directories, or non-UTF-8 content.
    """
    try:
        target = _resolve_path(path, ctx.deps)
        if target.is_dir():
            raise ModelRetry(f"Path must be a file, not a directory: {path}")

        content = target.read_text(encoding="utf-8")
        return ToolResult(success=True, content=_cat_n_format(content))
    except UnicodeDecodeError:
        raise ModelRetry(f"File must be UTF-8 encoded text: {path}")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def edit_file(ctx: RunContext[RunDeps], path: str, old_str: str, new_str: str) -> ToolResult:
    """Replace a unique occurrence of old_str with new_str in a UTF-8 text file.

    - Path must be inside the current working directory and must be a file; directories are rejected.
    - The file must decode as UTF-8; otherwise ModelRetry is raised.
    - old_str must appear exactly once; otherwise ModelRetry is raised requesting more context.
    - A timestamped backup is created alongside the file before writing; writes are atomic via temp file.
    - Returns a short success or error message; on error, backup name is included when available.
    """
    try:
        target = _resolve_path(path, ctx.deps)
        if target.is_dir():
            raise ModelRetry(f"Path must be a file, not a directory: {path}")

        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ModelRetry(f"File must be UTF-8 encoded text: {path}")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))

    occurrences = content.count(old_str)
    if occurrences == 0:
        raise ModelRetry("old_str not found in file")
    if occurrences > 1:
        raise ModelRetry(
            "old_str appears multiple times; provide more context to match uniquely"
        )

    backup_path = _create_backup(target)

    try:
        new_content = content.replace(old_str, new_str, 1)
        _write_text_atomic(target, new_content)
        return ToolResult(success=True, content="Edit completed successfully")
    except Exception as e:
        return ToolResult(success=False, content="", error=f"{e}. Backup saved to {backup_path.name}")


def create_file(ctx: RunContext[RunDeps], path: str, content: str) -> ToolResult:
    """Create a new file with the given content.

    - Path must be inside currently working directory.
    - Path must NOT exist (use edit_file to modify existing files).
    - Creates parent directories if needed.
    - Writes atomically via a temp file.
    """
    try:
        target = _resolve_path(path, ctx.deps, must_exist=False)
        if target.exists():
            raise ModelRetry(f"File already exists: {path}. Use edit_file to modify it.")

        target.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(target, content)
        return ToolResult(success=True, content="File created successfully")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


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
