import asyncio

from ..core.factory import create_agent
from ..core.loop import (
    AgentSession,
)
from ..core.types import (
    AgentChunk,
    AgentDone,
    ApprovalRequest,
    ApprovalResponse,
    RunDeps,
)
from ..middleware.debouncing import DebouncingMiddleware


async def run_console_ui():
    # Setup agent using the factory
    agent = create_agent()

    prompt = "List the files in the current directory and then read README.md"
    deps = RunDeps()

    print(f"Prompt: {prompt}\n")
    print("-" * 40)

    session = AgentSession(agent=agent)
    raw_gen = session.run(prompt, deps)

    middleware = DebouncingMiddleware(threshold=40)
    gen = middleware.process(raw_gen)

    response = None

    try:
        while True:
            event = await gen.asend(response)
            response = None

            if isinstance(event, AgentChunk):
                if event.is_thought:
                    print(f"\n[THINKING]: {event.content}", end="", flush=True)
                else:
                    print(event.content, end="", flush=True)

            elif isinstance(event, ApprovalRequest):
                print("\n" + "!" * 40)
                print("APPROVAL REQUIRED:")
                for call in event.tool_calls:
                    print(f"  - {call.tool_name}({call.args})")

                # In a real console app, we'd use input().
                # For demonstration, we auto-approve to show the flow.
                print("Auto-approving for demo...")
                response = ApprovalResponse(approved=True)
                print("!" * 40 + "\n")

            elif isinstance(event, AgentDone):
                print("\n" + "-" * 40)
                print("DONE")
                break

    except StopAsyncIteration:
        pass
    except Exception as e:
        print(f"\nERROR: {e}")


def main():
    asyncio.run(run_console_ui())


if __name__ == "__main__":
    main()
