"""GitHub Copilot backend implementation for Agent C."""

from .loop import GhAgentSession
from .session_factory import GhCopilotSessionFactory

__all__ = ["GhAgentSession", "GhCopilotSessionFactory"]
