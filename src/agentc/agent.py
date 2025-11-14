"""Main entry point and orchestration for Agent C.

This module provides the main entry point and event loop orchestration
for the agent, delegating to core modules for all business logic.
"""

import asyncio
import sys

from agentc.core import create_agent, discover_tools, load_configs, parse_args
from agentc.core.types import RunDeps
from agentc.ui import ConsoleUI


async def _async_main() -> None:
    """Async main entry point of the application."""
    agent_configs, personalities = load_configs()

    args = parse_args(personalities, agent_configs)
    current_personality = args.personality

    try:
        agent = create_agent(
            current_personality, personalities, agent_configs, args.model, args.provider
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    ui = ConsoleUI(personalities)
    run_deps = RunDeps(info=ui.show_info)

    tools_info = discover_tools()
    await ui.show_intro(tools_info)

    conversation: list = []

    while True:
        user_input = await ui.get_user_input()
        if user_input is None:
            ui.console.print("\nGoodbye!")
            break

        new_personality, should_exit = await ui.handle_command(user_input)
        if should_exit:
            break
        if new_personality:
            agent = create_agent(
                new_personality, personalities, agent_configs, None, args.provider
            )
            current_personality = new_personality
            conversation = []
            continue
        if user_input.strip().lower() in ("/clear", "/reset"):
            conversation = []
            continue

        try:
            conversation = await ui.run_agent_interaction(
                agent, user_input, conversation, run_deps
            )
        except Exception as e:
            ui.console.print(f"Error: {e}")


def main() -> None:
    """Synchronous entry point for the application."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
