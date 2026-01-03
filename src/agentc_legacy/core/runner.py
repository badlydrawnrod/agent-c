from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import (Agent, DeferredToolRequests, DeferredToolResults,
                         ToolDenied)
from pydantic_ai.messages import ModelMessage

from .types import ApprovalRequest, LoopCallbacks, StreamChunk


class AgentRunner:
    """Core interaction loop manager (UI-agnostic).

    This belongs in core so UIs can be implemented independently of the loop.
    """

    def __init__(
        self,
        agent: Agent[Any, str | DeferredToolRequests],
        user_input: str,
        conversation: list[ModelMessage],
        run_deps: Any,
        callbacks: LoopCallbacks | None = None,
    ):
        self.agent = agent
        self.user_input = user_input
        self.conversation = conversation
        self.run_deps = run_deps
        self.callbacks = callbacks

        # Event is set when the runner is allowed to proceed (not paused).
        self._can_proceed = asyncio.Event()
        self._can_proceed.set()

        self.cancel_event = asyncio.Event()
        self.loop_task: asyncio.Task[None] | None = None

        self.run_args: tuple[str, ...] = (user_input,)
        self.run_params: dict[str, Any] = {
            "message_history": conversation,
            "deps": run_deps,
        }
        self.messages = conversation

    async def run(self) -> list[ModelMessage]:
        """Execute the agent interaction loop."""
        try:
            self.loop_task = asyncio.current_task()
            await self._interaction_loop()
        except asyncio.CancelledError:
            pass
        return self.messages

    async def _interaction_loop(self) -> None:
        """Main loop handling the agent interaction and tool approvals."""
        while True:
            output, result = await self._stream_response()
            self.messages = result.all_messages()

            if not isinstance(output, DeferredToolRequests):
                break

            approval_results = await self._collect_tool_approvals(output)
            self._prepare_next_run_params(approval_results)

    async def _stream_response(self) -> tuple[str | DeferredToolRequests, Any]:
        """Stream the agent's response, handling callbacks and cancellation."""
        output: str | DeferredToolRequests = ""
        result: Any = None

        if self.callbacks is not None:
            # Signal that the agent is now thinking; UI decides exact text.
            self.callbacks.on_thinking()

        try:
            if self.cancel_event.is_set():
                raise asyncio.CancelledError()

            has_output = False
            accumulated_text = ""
            accumulated_thinking = ""

            async with self.agent.run_stream(
                *self.run_args, **self.run_params
            ) as result:
                async for message, _ in result.stream_responses(debounce_by=0.1):
                    if self.cancel_event.is_set():
                        raise asyncio.CancelledError()

                    # Handle Thinking
                    current_thinking = message.thinking or ""
                    if len(current_thinking) > len(accumulated_thinking):
                        delta = current_thinking[len(accumulated_thinking) :]
                        accumulated_thinking = current_thinking
                        if self.callbacks:
                            self.callbacks.on_thinking_chunk(delta)

                    # Handle Text
                    current_text = message.text or ""
                    if len(current_text) > len(accumulated_text):
                        delta = current_text[len(accumulated_text) :]
                        accumulated_text = current_text

                        if not has_output:
                            has_output = True

                        if self.callbacks is not None:
                            self.callbacks.on_stream_chunk(StreamChunk(delta))
                            # Provide only the variable portion of the status (eg.
                            # character count). UI will prefix and style this as
                            # appropriate for the environment.
                            self.callbacks.on_status_update(
                                f"({len(accumulated_text)} chars)"
                            )

                    await self._wait_if_paused()

                if self.cancel_event.is_set():
                    raise asyncio.CancelledError()

                if self.callbacks is not None:
                    self.callbacks.on_stream_complete()

                output = await result.get_output()

        except asyncio.CancelledError:
            if self.callbacks is not None:
                self.callbacks.on_cancelled("**Cancelled** - Exiting.")
            raise

        return output, result

    async def _wait_if_paused(self) -> None:
        """Wait if the runner is currently paused."""
        await self._can_proceed.wait()
        if self.cancel_event.is_set():
            raise asyncio.CancelledError()

    async def _collect_tool_approvals(
        self, deferred_output: DeferredToolRequests
    ) -> DeferredToolResults:
        """Collect user approvals for tool requests."""
        approval_results = DeferredToolResults()
        for call in deferred_output.approvals:
            req = ApprovalRequest(call.tool_name, call.tool_call_id, call.args)

            if self.callbacks is not None:
                approved = await self.callbacks.request_approval(req)
            else:
                # No UI; treat as denied
                approved = False

            approval_results.approvals[call.tool_call_id] = (
                True if approved else ToolDenied("Tool denied by user")
            )
        return approval_results

    def _prepare_next_run_params(self, approval_results: DeferredToolResults) -> None:
        """Prepare the parameters for the next agent run iteration."""
        self.run_args = ()
        self.run_params = {
            "message_history": self.messages,
            "deferred_tool_results": approval_results,
            "deps": self.run_deps,
        }

    def pause(self) -> None:
        """Pause the execution of the runner."""
        self._can_proceed.clear()

    def resume(self) -> None:
        """Resume the execution of the runner."""
        self._can_proceed.set()

    def cancel(self) -> None:
        """Cancel the execution of the runner."""
        self.cancel_event.set()
        # Ensure we don't get stuck waiting if paused
        self._can_proceed.set()
        if self.loop_task is not None:
            self.loop_task.cancel()

    @property
    def is_paused(self) -> bool:
        """Check if the runner is currently paused."""
        return not self._can_proceed.is_set()
