"""
CLI entry point for the Textual UI with GitHub Copilot integration.
"""

import asyncio
import shutil
import sys
from pathlib import Path

from copilot import CopilotClient
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    SessionConfig as CopilotSessionConfig,
    SystemMessageReplaceConfig,
)

from .textual_app import TextualAgentApp
from ..core.backends.github_copilot.session_factory import GhCopilotSessionFactory
from ..core.command_types import SessionConfig
from ..core.deps import RunDeps
from ..core.skill_loader import SkillLoader


async def main() -> None:
    """CLI entry point for the Textual UI with GitHub Copilot integration."""

    # Handler for permission requests.
    def on_permission_request(
        permission_request: PermissionRequest, args: dict[str, str]
    ) -> PermissionRequestResult:
        print(f"\nPermission request {permission_request} with args {args}\n")
        return PermissionRequestResult(kind="approved")

    cli_path = shutil.which("copilot")
    if not cli_path:
        raise RuntimeError("Copilot CLI not found in PATH")

    # Determine root directories.
    args = sys.argv[1:]
    root_dirs = [Path(arg).resolve() for arg in args] if args else [Path.cwd()]

    loader = SkillLoader()
    skill_dirs = loader.get_default_skill_dirs()
    deps = RunDeps(root_dirs=root_dirs, skill_dirs=skill_dirs)

    # Create and start client.
    client = CopilotClient({"cli_path": cli_path})
    await client.start()

    # This prompt replaces the system message, but leaves tools and skills intact.
    system_message_config = SystemMessageReplaceConfig(
        mode="replace",
        content=f"""\
# Instructions

You are an expert coding assistant with comprehensive file system access and command execution capabilities. You help users navigate, analyze, edit, and manage their codebase efficiently.

## Communication Guidelines
- **Be succinct but informative**: Provide clear, actionable responses
- **Use markdown**: Format code snippets with appropriate syntax highlighting
- **Ask when uncertain**: If a request is ambiguous, ask clarifying questions before acting
- **Explain errors**: When things go wrong, explain the issue and suggest alternatives
- **Summarize changes**: After modifications, clearly state what was changed and why
- **Warn about risks**: If uncertain about a change's impact, warn the user explicitly

## Output Encoding
By default, use ASCII encoding. Only introduce non-ASCII or Unicode characters if:
- The file already contains them
- There's a domain-specific need (e.g., internationalization, mathematical notation)
Always explain why non-ASCII characters are necessary.

## Success Criteria
- All requested changes are correctly implemented
- Changes align with existing code style and patterns  
- No syntax errors or regressions are introduced
- User's intent is fully addressed

<environment_context>
You are working in the following environment. You do not need to make additional tool calls to verify this.
* Current working directory: {Path.cwd()}
</environment_context>
""",
    )

    # Create a session.
    model = "gpt-5 mini"
    # model = "Claude Haiku 4.5"
    # provider_config = ProviderConfig(
    #     type="openai", wire_api="completions", base_url="http://localhost:11434/v1"
    # )
    # model = "gpt-oss:20b"
    is_streaming = True
    session_config = CopilotSessionConfig(
        model=model,  # type: ignore
        on_permission_request=on_permission_request,
        # provider=provider_config,
        skill_directories=[str(d) for d in skill_dirs],
        streaming=is_streaming,
        system_message=system_message_config,
    )

    session_factory = GhCopilotSessionFactory(client, session_config)
    agent_session = await session_factory.create_session(
        SessionConfig(
            model_name=model,
            skill_dirs=skill_dirs,
            deps=deps,
        )
    )
    app = TextualAgentApp(
        session=agent_session,
        session_factory=session_factory,
        deps=deps,
    )
    await app.run_async()

    # Clean up.
    await session_factory.cleanup()
    await client.stop()


def main_sync():
    """Synchronous wrapper for the async main function."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
