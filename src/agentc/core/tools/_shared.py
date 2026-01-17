"""Shared utilities for Agent C tools.

This module provides common infrastructure used across all tool categories,
including path validation, security boundaries, and shared type imports.
"""

from pathlib import Path

from pydantic_ai import ModelRetry, RunContext

from ..types import RunDeps, ToolResult


def resolve_path(path_str: str, deps: RunDeps, *, must_exist: bool = True) -> Path:
    """Resolve and validate a path within allowed root directories.

    This function serves as the primary security boundary for all file-based tools,
    ensuring that operations are sandboxed to configured root directories.

    Args:
        path_str: The path string to resolve (supports ~/ expansion).
        deps: Runtime dependencies containing allowed root_dirs.
        must_exist: If True, raises ModelRetry if the path doesn't exist.

    Returns:
        A fully resolved Path object guaranteed to be within one of the root_dirs.

    Raises:
        ModelRetry: If the path is outside all root_dirs, or if must_exist=True
            and the path doesn't exist. This signals to the LLM that it should
            retry with a corrected path.

    Security guarantees:
        - All paths are resolved via Path.resolve() to handle symlinks and '..' traversal
        - Paths must be descendants of at least one configured root directory
        - No access is permitted outside the sandboxed root_dirs boundaries

    Examples:
        >>> resolve_path("src/main.py", deps)
        PosixPath('/workspace/src/main.py')

        >>> resolve_path("../../etc/passwd", deps)
        ModelRetry: Path is outside allowed directories: ../../etc/passwd

        >>> resolve_path("nonexistent.txt", deps, must_exist=False)
        PosixPath('/workspace/nonexistent.txt')
    """
    candidate = Path(path_str).expanduser().resolve(strict=False)

    for root in deps.root_dirs:
        if candidate.is_relative_to(root.resolve()):
            if must_exist and not candidate.exists():
                raise ModelRetry(f"Path does not exist: {path_str}")
            return candidate

    raise ModelRetry(f"Path is outside allowed directories: {path_str}")


__all__ = ["resolve_path", "Path", "ModelRetry", "RunContext", "RunDeps", "ToolResult"]
