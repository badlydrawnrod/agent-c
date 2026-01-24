"""Filesystem discovery tools for the Pydantic_AI backend."""

from pathlib import Path

import pathspec

from pydantic_ai import ModelRetry

from ._shared import resolve_path, RunContext, RunDeps, ToolResult
from ....config import DEFAULT_IGNORE_PATTERNS, MAX_TOOL_OUTPUT_LINES


def _load_ignore_spec(base: Path) -> pathspec.PathSpec:
    """Load combined ignore patterns from defaults and .gitignore."""
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    gitignore_path = base / ".gitignore"
    if gitignore_path.is_file():
        patterns.extend(gitignore_path.read_text(encoding="utf-8").splitlines())
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def list_files(ctx: RunContext[RunDeps], path: str = ".") -> ToolResult:
    """List entries in a directory inside the current working tree."""
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
    """Find files matching glob pattern recursively within the working tree."""
    try:
        base = resolve_path(path, ctx.deps)
        if not base.is_dir():
            raise ModelRetry(f"Path must be a directory: {path}")

        spec = _load_ignore_spec(base)
        matches = []
        all_matches = []
        for p in base.rglob(pattern):
            rel = p.relative_to(base)
            rel_str = rel.as_posix()
            rel_for_match = rel_str + "/" if p.is_dir() else rel_str
            if spec.match_file(rel_for_match):
                continue
            entry = rel_str + ("/" if p.is_dir() else "")
            all_matches.append(entry)

        all_matches.sort()

        if len(all_matches) > MAX_TOOL_OUTPUT_LINES:
            matches = all_matches[:MAX_TOOL_OUTPUT_LINES]
            remaining = len(all_matches) - MAX_TOOL_OUTPUT_LINES
            matches.append(f"... {remaining} more")
        else:
            matches = all_matches

        content = "\n".join(matches) if matches else "No matches."
        return ToolResult(success=True, content=content)
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def search_files(ctx: RunContext[RunDeps], query: str, path: str = ".") -> ToolResult:
    """Search for text in files within the working tree."""
    try:
        base = resolve_path(path, ctx.deps)
        if not base.is_dir():
            raise ModelRetry(f"Path must be a directory: {path}")

        spec = _load_ignore_spec(base)
        matches: list[str] = []
        all_matches: list[str] = []
        for file_path in base.rglob("*"):
            rel = file_path.relative_to(base)
            rel_str = rel.as_posix()
            rel_for_match = rel_str + "/" if file_path.is_dir() else rel_str
            if spec.match_file(rel_for_match):
                continue

            if file_path.is_dir():
                continue

            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for lineno, line in enumerate(text.splitlines(), 1):
                if query in line:
                    all_matches.append(f"{rel_str}:{lineno}: {line}")

        all_matches.sort()

        if len(all_matches) > MAX_TOOL_OUTPUT_LINES:
            matches = all_matches[:MAX_TOOL_OUTPUT_LINES]
            remaining = len(all_matches) - MAX_TOOL_OUTPUT_LINES
            matches.append(f"... {remaining} more")
        else:
            matches = all_matches

        content = "\n".join(matches) if matches else "No matches."
        return ToolResult(success=True, content=content)
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))
