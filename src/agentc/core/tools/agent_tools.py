"""Agent delegation tools for Agent C."""

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

from ..types import RunDeps


async def delegate_to_agent(
    ctx: RunContext[RunDeps], personality: str, task: str
) -> str:
    """Delegate a task to another agent personality."""
    if ctx.deps.agent_factory is None:
        raise ModelRetry("Delegation is not available")

    ctx.deps.info(f"Delegating to {personality}...")
    agent = ctx.deps.agent_factory(personality)
    result = await agent.run(task, deps=ctx.deps)

    # Handle deferred tool requests.
    while isinstance(result.output, DeferredToolRequests):
        ctx.deps.info("Delegation requires tool approvals")
        return "Delegation failed: tool approvals required"

    ctx.deps.info(f"Delegation result: {result.output}")
    if isinstance(result.output, str):
        return result.output
    return "Delegation failed: deferred tool requests not handled"
