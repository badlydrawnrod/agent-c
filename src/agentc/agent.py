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

    async def handle_input(user_input: str) -> None:
        nonlocal conversation, agent, current_personality, agent_factory, run_deps

        # Parse command using centralized handler
        result = command_handler.parse(user_input)

        # Handle different command types
        if result.command_type == CommandType.EXIT:
            if ui.app:
                ui.app.exit()
            return

        if result.command_type == CommandType.UNKNOWN:
            error_msg = result.args.get("error", "Unknown error")
            ui.show_info(f"Error: {error_msg}")
            return

        if result.command_type == CommandType.CLEAR:
            conversation = []
            ui.show_info("Context cleared.")
            return

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
            ui.show_info(f"Switched to personality: {new_personality}")
            return

        # Regular input - run agent interaction
        if result.command_type == CommandType.NORMAL_INPUT:
            try:
                # Display the user prompt in the UI
                from agentc.ui.console import _to_container, _user_prompt_area
                from prompt_toolkit.widgets import Frame
                
                area = _user_prompt_area(user_input)
                frame = Frame(area, title="You")
                ui.hsplit.children.append(_to_container(frame))
                
                # Now run the agent
                from agentc.core.runner import AgentRunner
                runner = AgentRunner(
                    agent,
                    user_input,
                    conversation,
                    run_deps,
                    callbacks=ui,
                )
                
                conversation[:] = await runner.run()
                
            except Exception as e:
                ui.show_info(f"Error: {e}")

    await ui.run(handle_input)


def main() -> None:
    """Synchronous entry point for the application."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
