"""
CLI entry point for the Textual UI.

Instantiates the `TextualAgentApp` with a created `Agent` and runs the
Textual application.
"""

from ..core.factory import create_agent
from ..core.loop import AgentSession
from ..core.types import RunDeps
from .textual_app import TextualAgentApp


def main() -> None:
    """CLI entry point for the Textual UI application."""
    from pathlib import Path

    deps = RunDeps(root_paths=[Path.cwd()])
    session = AgentSession(agent=create_agent(), deps=deps)
    app = TextualAgentApp(session=session, deps=deps)
    app.run()


if __name__ == "__main__":
    main()
