"""Tool definitions and registry for Agent C.

This module defines all available tools for the agent and provides a
ToolRegistry class for extensibility. Tools can be registered, queried,
and discovered dynamically.
"""

import shutil
from typing import Any

from pydantic_ai import ModelRetry, RunContext, Tool

from .config import load_configs
from .file_ops import (
    cleanup_old_backups,
    create_backup,
    safe_resolve,
    safe_resolve_create,
    write_and_verify,
)
from .types import RunDeps


# ---- TOOL IMPLEMENTATIONS ----


def read_file(ctx: RunContext[RunDeps], path: str) -> str:
    """Read the contents of a file."""
    ctx.deps.info(f"Reading file: {path}")
    resolved_path = safe_resolve(path)
    if not resolved_path.is_file():
        raise ModelRetry("Path must be a file")
    return resolved_path.read_text(encoding="utf-8")


def list_files(ctx: RunContext[RunDeps], path: str) -> str:
    """List files in the specified directory."""
    ctx.deps.info(f"Listing files in: {path}")
    resolved_path = safe_resolve(path)
    if not resolved_path.is_dir():
        raise ModelRetry("Path must be a directory")
    return "\n".join(sorted(p.name for p in resolved_path.iterdir()))


def edit_file(ctx: RunContext[RunDeps], path: str, old_str: str, new_str: str) -> str:
    """Edit a file by replacing old_str with new_str."""
    ctx.deps.info(f"Editing file: {path}")
    resolved_path = safe_resolve(path)
    if not resolved_path.is_file():
        raise ModelRetry("Path must be a file")

    # Read original.
    content = resolved_path.read_text(encoding="utf-8")
    occurrence_count = content.count(old_str)
    if occurrence_count == 0:
        raise ModelRetry("old_str not found in file")
    if occurrence_count > 1:
        raise ModelRetry(
            f"old_str appears {occurrence_count} times; provide more context to match uniquely"
        )

    # Create backup BEFORE modification.
    backup_path = create_backup(resolved_path)
    ctx.deps.info(f"Backup created: {backup_path.name}")

    try:
        # Calculate new content.
        new_content = content.replace(old_str, new_str)

        # Write and verify atomically.
        write_and_verify(resolved_path, new_content)

        # Clean up old backups (keep last 5).
        cleanup_old_backups(resolved_path)

        return "Edit completed successfully"
    except Exception as e:
        ctx.deps.info(f"Edit failed, backup available at {backup_path.name}")
        raise ModelRetry(f"Failed to edit file: {e}")


def create_file(ctx: RunContext[RunDeps], path: str, content: str) -> str:
    """Create a new file with the given content, creating parent directories if needed."""
    ctx.deps.info(f"Creating file: {path}")
    resolved_path = safe_resolve_create(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    # Create backup if file already exists.
    if resolved_path.exists():
        backup_path = create_backup(resolved_path)
        ctx.deps.info(f"Existing file backed up: {backup_path.name}")

    try:
        # Write and verify atomically.
        write_and_verify(resolved_path, content)
        return "File created successfully"
    except Exception as e:
        ctx.deps.info("File creation failed")
        raise ModelRetry(f"Failed to create file: {e}")


def search_files(ctx: RunContext[Any], path: str, query: str) -> str:
    """Recursively search for a query string in files within a given path."""
    resolved_path = safe_resolve(path)
    if not resolved_path.is_dir():
        raise ModelRetry("Path must be a directory")
    results = []
    for file_path in resolved_path.rglob("*"):
        if file_path.is_file():
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if query in line:
                        results.append(f"{file_path}:{line_num}: {line.strip()}")
    return "\n".join(results)


async def delegate_to_agent(
    ctx: RunContext[RunDeps], personality: str, task: str
) -> str:
    """Delegate a task to another agent personality."""
    from .agent_factory import create_agent

    agent_configs, personalities = load_configs()
    if personality not in personalities:
        raise ValueError(f"Unknown personality: {personality}")
    ctx.deps.info(f"Delegating to {personality}...")
    agent = create_agent(personality, personalities, agent_configs)
    result = await agent.run(task, deps=ctx.deps)

    # Handle deferred tool requests.
    from pydantic_ai import DeferredToolRequests

    while isinstance(result.output, DeferredToolRequests):
        ctx.deps.info("Delegation requires tool approvals")
        return "Delegation failed: tool approvals required"

    ctx.deps.info(f"Delegation result: {result.output}")
    if isinstance(result.output, str):
        return result.output
    return "Delegation failed: deferred tool requests not handled"


def list_backups(ctx: RunContext[RunDeps], path: str) -> str:
    """List available backups for a file."""
    ctx.deps.info(f"Listing backups for: {path}")
    resolved_path = safe_resolve(path)
    backups = sorted(resolved_path.parent.glob(f"{resolved_path.name}.backup.*"))
    if not backups:
        return "No backups found"
    return "\n".join(b.name for b in backups)


def restore_backup(ctx: RunContext[RunDeps], path: str, backup_name: str) -> str:
    """Restore a file from a backup."""
    ctx.deps.info(f"Restoring {path} from {backup_name}")
    resolved_path = safe_resolve(path)
    backup_path = resolved_path.parent / backup_name
    if not backup_path.exists():
        raise ModelRetry("Backup not found")
    shutil.copy2(backup_path, resolved_path)
    return f"Restored {path} from {backup_name}"


# ---- TOOL REGISTRY ----


class ToolRegistry:
    """Registry for managing and discovering available tools.

    This class provides a centralized way to register, retrieve, and discover
    tools without coupling them to the main agent.py module.
    """

    def __init__(self):
        """Initialize the tool registry with default tools."""
        self._tools: list[Tool] = [
            Tool(read_file, takes_ctx=True, strict=True),
            Tool(list_files, takes_ctx=True, strict=True),
            Tool(edit_file, takes_ctx=True, strict=True, requires_approval=True),
            Tool(create_file, takes_ctx=True, strict=True, requires_approval=True),
            Tool(search_files, takes_ctx=True, strict=True),
            Tool(delegate_to_agent, takes_ctx=True, strict=True),
            Tool(list_backups, takes_ctx=True, strict=True),
            Tool(restore_backup, takes_ctx=True, strict=True, requires_approval=True),
        ]

    def register(self, tool: Tool) -> None:
        """Register a new tool.

        Args:
            tool: Tool to register.
        """
        self._tools.append(tool)

    def get_all(self) -> list[Tool]:
        """Get all registered tools.

        Returns:
            List of all registered tools.
        """
        return self._tools

    def discover(self) -> str:
        """Discover and format information about available tools.

        Returns:
            Formatted string describing all available tools.
        """
        return "\n".join(f"- {tool.name}: {tool.description}" for tool in self._tools)
