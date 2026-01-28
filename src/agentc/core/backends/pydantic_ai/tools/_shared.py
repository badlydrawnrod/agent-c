"""Shared utilities for Pydantic_AI tools."""

from pathlib import Path

from pydantic_ai import ModelRetry, RunContext

from ....deps import RunDeps
from ....types import ToolResult


def resolve_path(path_str: str, deps: RunDeps, *, must_exist: bool = True) -> Path:
    """Resolve and validate a path within allowed root directories."""
    candidate = Path(path_str).expanduser().resolve(strict=False)

    for root in deps.root_dirs:
        if candidate.is_relative_to(root.resolve()):
            if must_exist and not candidate.exists():
                raise ModelRetry(f"Path does not exist: {path_str}")
            return candidate

    raise ModelRetry(f"Path is outside allowed directories: {path_str}")


__all__ = ["resolve_path", "Path", "ModelRetry", "RunContext", "RunDeps", "ToolResult"]
