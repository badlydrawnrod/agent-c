"""
CLI entry point for the Textual UI.

Instantiates the `TextualAgentApp` with a created `Agent` and runs the
Textual application.
"""

from ..core.factory import create_agent
from ..core.loop import AgentSession
from ..core.skill_loader import SkillLoader
from ..core.types import RunDeps
from .textual_app import TextualAgentApp


def main() -> None:
    """CLI entry point for the Textual UI application."""
    from pathlib import Path

    loader = SkillLoader()
    skill_dirs = loader.get_default_skill_dirs()

    deps = RunDeps(root_paths=[Path.cwd()] + skill_dirs)
    session = AgentSession(agent=create_agent(skill_dirs=deps.root_paths), deps=deps)
    app = TextualAgentApp(session=session, deps=deps)
    app.run()


if __name__ == "__main__":
    main()
