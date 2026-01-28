"""Session factory for the Pydantic_AI backend."""

from __future__ import annotations

from ...command_types import SessionConfig
from ...types import AgentSessionProtocol
from .factory import create_agent
from .loop import AgentSession
from .provider_loader import MissingAPIKeyError


class PydanticAISessionFactory:
    """Factory for creating Pydantic_AI agent sessions.

    Implements the `SessionFactoryProtocol` by using `create_agent()` to
    build a pydantic_ai agent, then wrapping it in `AgentSession`.
    """

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        """Create a Pydantic_AI agent session.

        Args:
            config: Backend-agnostic session configuration.

        Returns:
            AgentSession wrapping a configured pydantic_ai Agent.

        Raises:
            MissingAPIKeyError: If model requires API key that's not set.
            ValueError: If model_name is unknown.
        """
        try:
            agent = create_agent(
                model_name=config.model_name,
                skill_dirs=config.skill_dirs,
            )
        except MissingAPIKeyError:
            raise

        history: list | None = [] if config.clear_history else None

        return AgentSession(
            agent=agent,
            history=history,
            deps=config.deps,
        )


__all__ = ["PydanticAISessionFactory"]
