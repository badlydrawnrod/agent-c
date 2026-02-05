"""Session factory for the GitHub Copilot SDK backend."""

from __future__ import annotations

from typing import Any

from copilot import CopilotClient
from copilot.types import SessionConfig as CopilotSessionConfig

from ...command_types import SessionConfig
from ...types import AgentSessionProtocol
from .loop import GhAgentSession, GhUserInputBroker


class GhCopilotSessionFactory:
    """Factory for creating GitHub Copilot SDK sessions.

    Implements the `SessionFactoryProtocol` by wrapping CopilotClient
    session creation. Manages SDK-level session lifecycle (destroying
    old sessions before creating new ones).
    """

    def __init__(
        self,
        client: CopilotClient,
        base_config: CopilotSessionConfig,
    ) -> None:
        """Initialize with a running CopilotClient and base configuration.

        Args:
            client: Running CopilotClient instance (managed by entry point).
            base_config: Base SDK configuration (model, permissions, system
                message, etc). Model and skill_dirs can be overridden per
                session via SessionConfig.
        """
        self._client = client
        self._base_config = base_config
        self._current_copilot_session: Any = None

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        """Create a GitHub Copilot SDK session.

        Destroys any existing session before creating a new one, since the
        SDK manages session state internally.

        Args:
            config: Backend-agnostic session configuration.

        Returns:
            GhAgentSession wrapping a CopilotSession.
        """
        if self._current_copilot_session is not None:
            try:
                await self._current_copilot_session.destroy()
            except Exception:
                pass
            finally:
                self._current_copilot_session = None

        broker = GhUserInputBroker()

        sdk_config = CopilotSessionConfig(
            model=config.model_name or self._base_config["model"],  # type: ignore
            skill_directories=(
                [str(d) for d in config.skill_dirs]
                if config.skill_dirs
                else self._base_config["skill_directories"]  # type: ignore
            ),
            streaming=self._base_config["streaming"],  # type: ignore
            system_message=self._base_config["system_message"],  # type: ignore
            on_permission_request=self._base_config["on_permission_request"],  # type: ignore
            on_user_input_request=broker.handle_sdk_request,  # type: ignore
        )

        self._current_copilot_session = await self._client.create_session(sdk_config)
        return GhAgentSession(
            self._current_copilot_session, user_input_broker=broker
        )

    async def cleanup(self) -> None:
        """Clean up the current session (called on app shutdown)."""
        if self._current_copilot_session is not None:
            try:
                await self._current_copilot_session.destroy()
            except Exception:
                pass
            finally:
                self._current_copilot_session = None


__all__ = ["GhCopilotSessionFactory"]
