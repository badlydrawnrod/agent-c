"""
CLI entry point for the Textual UI.

Instantiates the `TextualAgentApp` with a created `Agent` and runs the
Textual application.
"""

from ..core.factory import create_agent
from ..core.loop import AgentSession
from .textual_app import TextualAgentApp


def main() -> None:
    """CLI entry point for the Textual UI application."""
    session = AgentSession(agent=create_agent())
    app = TextualAgentApp(session=session)
    app.run()


if __name__ == "__main__":
    main()
