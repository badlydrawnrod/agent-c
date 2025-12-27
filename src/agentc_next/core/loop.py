"""
Agent runtime utilities for Agent C Next.

Provides simple file-oriented tools, an `Agent` factory, event types used
by the UI, and an async streaming run loop that yields pydantic_ai
events (text/thinking parts, tool approval requests) and handles the
tool-approval flow.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from pydantic_ai import (
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    ToolDenied,
)
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)

from .tool_parsing import parse_tool_args
from .types import (
    AgentChunk,
    AgentDone,
    AgentEvent,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    RunDeps,
    NextAgent,
    ToolCallInfo,
)


class AgentSession(AgentSessionProtocol):
    """
    Encapsulates the state of an agentic session.

    This class keeps the history and agent implementation details opaque to the UI.
    """

    def __init__(
        self,
        agent: NextAgent,
        history: list[Any] | None = None,
    ):
        self._agent = agent
        self._history = history or []

    @property
    def history(self) -> list[Any]:
        return self._history

    @property
    def agent(self) -> NextAgent:
        return self._agent

    def update_history(self, history: list[Any]) -> None:
        self._history = history

    def _map_event_to_chunk(self, event: Any) -> AgentChunk | None:
        """Map a Pydantic AI event to an agnostic AgentChunk."""
        if isinstance(event, PartStartEvent):
            part = event.part
            if isinstance(part, TextPart) and part.content:
                return AgentChunk(content=part.content, is_thought=False)
            if isinstance(part, ThinkingPart) and part.content:
                return AgentChunk(content=part.content, is_thought=True)

        if isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, TextPartDelta):
                return AgentChunk(content=delta.content_delta, is_thought=False)
            if isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                return AgentChunk(content=delta.content_delta, is_thought=True)

        return None

    def _is_cancelled(self, cancellation_event: asyncio.Event | None) -> bool:
        """Check if cancellation has been requested."""
        if isinstance(cancellation_event, asyncio.Event):
            return cancellation_event.is_set()
        return bool(cancellation_event)

    def _create_approval_request(
        self, event: AgentRunResultEvent[Any]
    ) -> ApprovalRequest:
        """Create an ApprovalRequest from an AgentRunResultEvent."""
        if not isinstance(event.result.output, DeferredToolRequests):
            raise ValueError("Event output is not DeferredToolRequests")

        tool_calls = [
            ToolCallInfo(
                tool_name=call.tool_name,
                args=parse_tool_args(call.args),
                tool_call_id=call.tool_call_id,
            )
            for call in event.result.output.approvals
        ]
        return ApprovalRequest(tool_calls=tool_calls)

    def _create_approval_results(
        self, event: AgentRunResultEvent[Any], approval_response: ApprovalResponse
    ) -> DeferredToolResults:
        """Create DeferredToolResults based on the approval response."""
        if not isinstance(event.result.output, DeferredToolRequests):
            raise ValueError("Event output is not DeferredToolRequests")

        approval_results = DeferredToolResults()
        for call in event.result.output.approvals:
            approval_results.approvals[call.tool_call_id] = (
                approval_response.approved
                if approval_response.approved
                else ToolDenied(
                    approval_response.reason
                    or "The tool call was denied by the user. Acknowledge the denial and do NOT retry."
                )
            )
        return approval_results

    async def run(
        self,
        prompt: str,
        deps: RunDeps,
        cancellation_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[AgentEvent, ApprovalResponse | None]:
        """
        Run the agentic session with the given prompt and dependencies.

        Async generator that runs the agent and yields event types from types.py.
        """
        approval_results: DeferredToolResults | None = None
        current_prompt: str | None = prompt

        while True:
            if self._is_cancelled(cancellation_event):
                return

            async for event in self._agent.run_stream_events(
                current_prompt,
                message_history=self._history,
                deferred_tool_results=approval_results,
                deps=deps,
            ):
                if self._is_cancelled(cancellation_event):
                    return

                if chunk := self._map_event_to_chunk(event):
                    yield chunk

                elif isinstance(event, PartStartEvent) and isinstance(
                    event.part, ToolCallPart
                ):
                    yield ToolCallInfo(
                        tool_name=event.part.tool_name,
                        args=parse_tool_args(event.part.args),
                        tool_call_id=event.part.tool_call_id or "unknown",
                    )

                elif isinstance(event, AgentRunResultEvent):
                    if isinstance(event.result.output, DeferredToolRequests):
                        # This is the bi-directional handshake
                        request = self._create_approval_request(event)
                        approval_response: ApprovalResponse | None = yield request

                        if approval_response is None:
                            return

                        approval_results = self._create_approval_results(
                            event, approval_response
                        )
                        self.update_history(event.result.all_messages())
                        current_prompt = None
                        break

                    else:
                        self.update_history(event.result.all_messages())
                        yield AgentDone(history=self._history)
                        return

            else:
                return


__all__ = [
    "AgentSession",
]
