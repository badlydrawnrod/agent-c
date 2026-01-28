"""Console UI entry point using the ConsoleAgentAdapter.

This module demonstrates the console adapter pattern, translating agent
events into console output via callbacks.
"""

import asyncio

from ..adapters.console import ConsoleAgentAdapter
from ..adapters.console_messages import (
    ConsoleApprovalRequestEvent,
    ConsoleCancelledEvent,
    ConsoleDoneEvent,
    ConsoleErrorEvent,
    ConsoleEvent,
    ConsoleTextEvent,
    ConsoleThinkingEvent,
    ConsoleToolCallEvent,
    ConsoleToolResultEvent,
)
from ..core.backends.pydantic_ai.factory import create_agent
from ..core.backends.pydantic_ai.loop import AgentSession
from ..core.skill_loader import SkillLoader
from ..core.deps import RunDeps
from ..core.types import ApprovalResponse


def handle_event(event: ConsoleEvent) -> None:
    """Handle console events by printing to stdout.

    Args:
        event: The console event to handle.
    """
    match event:
        case ConsoleThinkingEvent(text=text):
            print(f"\n[THINKING]: {text}", end="", flush=True)

        case ConsoleTextEvent(text=text):
            print(text, end="", flush=True)

        case ConsoleToolCallEvent(tool_name=name, args=args):
            print(f"\n[TOOL CALL]: {name}({args})", flush=True)

        case ConsoleToolResultEvent(result=result):
            status = "✓" if result.success else "✗"
            print(f"[TOOL RESULT {status}]: {result.content[:100]}...", flush=True)

        case ConsoleDoneEvent():
            print("\n" + "-" * 40)
            print("DONE")

        case ConsoleErrorEvent(error=error):
            print(f"\nERROR: {error}")

        case ConsoleCancelledEvent():
            print("\nCANCELLED")


async def handle_approval(event: ConsoleApprovalRequestEvent) -> ApprovalResponse:
    """Handle approval requests.

    In a real console app, this would use input() to get user confirmation.
    For demonstration, we auto-approve.

    Args:
        event: The approval request event containing tool calls.

    Returns:
        ApprovalResponse indicating whether the tools are approved.
    """
    print("\n" + "!" * 40)
    print("APPROVAL REQUIRED:")
    for call in event.tool_calls:
        print(f"  - {call.tool_name}({call.args})")

    # In a real console app, we'd use input().
    # For demonstration, we auto-approve to show the flow.
    print("Auto-approving for demo...")
    print("!" * 40 + "\n")
    return ApprovalResponse(approved=True)


async def run_console_ui() -> None:
    """Run the console UI using the ConsoleAgentAdapter."""
    from pathlib import Path

    loader = SkillLoader()
    skill_dirs = loader.get_default_skill_dirs()

    # Setup agent using the factory
    deps = RunDeps(root_dirs=[Path.cwd()], skill_dirs=skill_dirs)
    agent = create_agent(skill_dirs=deps.skill_dirs)
    session = AgentSession(agent=agent, deps=deps)

    prompt = "List the files in the current directory and then read README.md"

    print(f"Prompt: {prompt}\n")
    print("-" * 40)

    adapter = ConsoleAgentAdapter(
        session=session,
        prompt=prompt,
        on_event=handle_event,
        on_approval=handle_approval,
    )

    await adapter.run()


def main():
    asyncio.run(run_console_ui())


if __name__ == "__main__":
    main()
