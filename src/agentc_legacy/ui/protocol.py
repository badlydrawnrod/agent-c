"""UI protocol definitions for Agent C.

This module defines the interface that UI implementations must satisfy.
Alternative UIs (web, API, etc.) should implement all methods in UIProtocol.
"""

from typing import Any, Protocol

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import ModelMessage


class UIProtocol(Protocol):
    """Protocol that UI implementations must satisfy.

    This defines the contract for user interaction. Any alternative UI
    implementation (web, API, etc.) should implement all methods in this
    protocol.
    """

    async def show_intro(self, tools_info: str) -> None:
        """Display the introduction message."""
        ...

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        ...

    async def get_user_input(self) -> str | None:
        """Get input from the user. Returns None if user wants to exit."""
        ...

    async def ask_approval(
        self, tool_name: str, tool_call_id: str, params: dict | str | None
    ) -> bool:
        """Ask the user to approve a tool call. Returns True if approved."""
        ...

    async def run_agent_interaction(
        self,
        agent: Agent[Any, str | DeferredToolRequests],
        user_input: str,
        conversation: list[ModelMessage],
        run_deps: Any,
    ) -> list[ModelMessage]:
        """Run the agent interaction loop and return updated conversation."""
        ...
