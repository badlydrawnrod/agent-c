"""Core module containing modular components of Agent C.

This module provides the public API for the agent-c core functionality,
including type definitions, configuration management, file operations,
tool registry, and agent factory.
"""

from .agent_factory import create_agent, create_agent_factory
from .cli import parse_args
from .commands import CommandHandler, CommandResult, CommandType
from .config import load_configs
from .tools import ToolRegistry, discover_tools
from .types import AgentConfig, PersonalityConfig, RunDeps

__all__ = [
    "AgentConfig",
    "PersonalityConfig",
    "RunDeps",
    "CommandHandler",
    "CommandResult",
    "CommandType",
    "load_configs",
    "ToolRegistry",
    "create_agent",
    "create_agent_factory",
    "discover_tools",
    "parse_args",
]
