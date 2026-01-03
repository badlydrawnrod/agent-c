"""Agent C Legacy - A code editing assistant powered by Pydantic AI.

This package provides a modular AI agent system with support for multiple
personalities and LLM providers.

DEPRECATED: Use agentc package instead.
"""

from .agent import main
from .core import (AgentConfig, PersonalityConfig, RunDeps, ToolRegistry,
                   create_agent, load_configs)

__all__ = [
    "main",
    "AgentConfig",
    "PersonalityConfig",
    "RunDeps",
    "ToolRegistry",
    "create_agent",
    "load_configs",
]
