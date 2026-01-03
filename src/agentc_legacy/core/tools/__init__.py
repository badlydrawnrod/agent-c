"""Tool definitions and registry for Agent C.

This package provides a centralized way to manage tools, separating tool
definitions from registry management for better modularity and extensibility.
"""

from .registry import ToolRegistry, discover_tools

__all__ = ["ToolRegistry", "discover_tools"]
