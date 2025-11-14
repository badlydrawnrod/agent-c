"""Core module containing modular components of Agent C.

This module provides the public API for the agent-c core functionality,
including type definitions, configuration management, file operations,
tool registry, and agent factory.
"""

from .agent_factory import (
    create_agent,
    discover_tools,
    parse_args,
)
from .config import load_configs
from .tools import ToolRegistry
from .types import AgentConfig, PersonalityConfig, RunDeps

__all__ = [
    "AgentConfig",
    "PersonalityConfig",
    "RunDeps",
    "load_configs",
    "ToolRegistry",
    "create_agent",
    "discover_tools",
    "parse_args",
]
