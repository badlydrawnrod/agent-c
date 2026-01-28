"""
CLI entry point for the Textual UI.

Instantiates the `TextualAgentApp` with a created `Agent` and runs the
Textual application.
"""

from ..core.backends.pydantic_ai.factory import create_agent
from ..core.backends.pydantic_ai.loop import AgentSession
from ..core.backends.pydantic_ai.provider_loader import load_providers
from ..core.backends.pydantic_ai.session_factory import PydanticAISessionFactory
from ..core.skill_loader import SkillLoader
from ..core.deps import RunDeps
from ..ui.textual_app import TextualAgentApp


def main() -> None:
    """CLI entry point for the Textual UI application."""
    from pathlib import Path

    loader = SkillLoader()
    skill_dirs = loader.get_default_skill_dirs()

    # Load available models from providers.toml
    _, models = load_providers()
    model_names = sorted(models.keys())

    deps = RunDeps(root_dirs=[Path.cwd()], skill_dirs=skill_dirs)
    session_factory = PydanticAISessionFactory()
    session = AgentSession(agent=create_agent(skill_dirs=deps.skill_dirs), deps=deps)
    app = TextualAgentApp(
        session=session,
        session_factory=session_factory,
        model_names=model_names,
        deps=deps,
    )
    app.run()


if __name__ == "__main__":
    main()
