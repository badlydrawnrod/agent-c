"""Filesystem discovery tools for Agent C.

Provides tools for listing, searching, and discovering files within
the workspace, with gitignore support and security sandboxing.
"""

from pathlib import Path

import pathspec

from pydantic_ai import ModelRetry

from ._shared import resolve_path, RunContext, RunDeps, ToolResult
from ..config import DEFAULT_IGNORE_PATTERNS, MAX_TOOL_OUTPUT_LINES


def _load_ignore_spec(base: Path) -> pathspec.PathSpec:
    """Load combined ignore patterns from defaults and .gitignore."""
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    gitignore_path = base / ".gitignore"
    if gitignore_path.is_file():
        patterns.extend(gitignore_path.read_text(encoding="utf-8").splitlines())
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def list_files(ctx: RunContext[RunDeps], path: str = ".") -> ToolResult:
    """List entries in a directory inside the current working tree.

    - Path must be inside the current working directory; otherwise ModelRetry is raised.
    - Returns one entry per line, sorted case-insensitively; directories are suffixed with "/".
    """
    try:
        target = resolve_path(path, ctx.deps)
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
        base = resolve_path(path, ctx.deps)
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
        base = resolve_path(path, ctx.deps)
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


__all__ = ["list_files", "glob_paths", "search_files"]
