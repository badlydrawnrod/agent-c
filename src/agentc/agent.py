"""Main entry point and orchestration for Agent C.

This module provides the main entry point and event loop orchestration
for the agent, delegating to core modules for all business logic.
"""

import asyncio
import sys

from agentc.core import (CommandHandler, CommandType, create_agent,
                         create_agent_factory, discover_tools, load_configs,
                         parse_args)
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

    # Create the agent factory for delegation
    agent_factory = create_agent_factory(
        personalities, agent_configs, args.model, args.provider
    )

    ui = ConsoleUI(personalities)
    run_deps = RunDeps(info=ui.show_info, agent_factory=agent_factory)

    tools_info = discover_tools()
    await ui.show_intro(tools_info)

    conversation: list = []

    # Create command handler once for all command parsing
    command_handler = CommandHandler(personalities)

    while True:
        user_input = await ui.get_user_input()
        if user_input is None:
            ui.console.print("\nGoodbye!")
            break

        # Parse command using centralized handler
        result = command_handler.parse(user_input)

        # Handle different command types
        if result.command_type == CommandType.EXIT:
            break

        if result.command_type == CommandType.UNKNOWN:
            error_msg = result.args.get("error", "Unknown error")
            ui.console.print(f"Error: {error_msg}")
            continue

        if result.command_type == CommandType.CLEAR:
            conversation = []
            ui.console.print("Context cleared.")
            continue

        if result.command_type == CommandType.PERSONALITY_SWITCH:
            new_personality = result.args["personality"]
            agent = create_agent(
                new_personality, personalities, agent_configs, None, args.provider
            )
            # Update factory for the new personality context
            agent_factory = create_agent_factory(
                personalities, agent_configs, None, args.provider
            )
            run_deps.agent_factory = agent_factory
            current_personality = new_personality
            conversation = []
            ui.console.print(f"Switched to personality: {new_personality}")
            continue

        # Regular input - run agent interaction
        if result.command_type == CommandType.NORMAL_INPUT:
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
