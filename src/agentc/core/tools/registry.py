"""Tool registry for Agent C."""

from pydantic_ai import Tool

from .agent_tools import delegate_to_agent
from .backup_tools import list_backups, restore_backup
from .file_tools import (create_file, edit_file, list_files, read_file,
                         search_files)


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


def discover_tools() -> str:
    """Discover and format information about available tools.

    This is a convenience function that creates a registry instance
    and returns formatted tool information.

    Returns:
        Formatted string describing all available tools.
    """
    registry = ToolRegistry()
    return registry.discover()
