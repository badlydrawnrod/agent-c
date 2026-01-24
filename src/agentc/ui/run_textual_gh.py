"""
CLI entry point for the Textual UI with GitHub Copilot integration.
"""

import asyncio
from pathlib import Path
import shutil
from typing import Dict

from .textual_app import TextualAgentApp

from copilot import CopilotClient
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    ProviderConfig,
    SessionConfig,
    SystemMessageReplaceConfig,
)
from copilot.generated.session_events import SessionEvent, SessionEventType

from ..core.backends.github_copilot.loop import GhAgentSession


async def main():
    # Handler for permission requests.
    def on_permission_request(
        permission_request: PermissionRequest, args: Dict[str, str]
    ) -> PermissionRequestResult:
        print(f"\nPermission request {permission_request} with args {args}\n")
        return PermissionRequestResult(kind="approved")

    cli_path = shutil.which("copilot")
    if not cli_path:
        raise RuntimeError("Copilot CLI not found in PATH")

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
    session_config = SessionConfig(
        model=model,  # type: ignore
        on_permission_request=on_permission_request,
        # provider=provider_config,
        skill_directories=[".github/skills"],
        streaming=is_streaming,
        system_message=system_message_config,
    )
    session = await client.create_session(session_config)
    agent_session = GhAgentSession(session)
    app = TextualAgentApp(agent_session)
    await app.run_async()

    # Clean up.
    await session.destroy()
    await client.stop()


def main_sync():
    """Synchronous wrapper for the async main function."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
