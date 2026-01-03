"""
Agent runtime utilities for Agent C Next.

Provides simple file-oriented tools, an `Agent` factory, event types used
by the UI, and an async streaming run loop that yields pydantic_ai
events (text/thinking parts, tool approval requests) and handles the
tool-approval flow.
"""

import asyncio
from typing import Any

from pydantic_ai import (
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    FunctionToolResultEvent,
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
    ToolReturnPart,
)

from .tool_parsing import parse_tool_args
from .types import (
    AgentChunk,
    AgentDone,
    AgentSessionProtocol,
    ApprovalRequest,
    ApprovalResponse,
    RunDeps,
    NextAgent,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolResult,
    AgentEventStream,
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
        """Return the current message history."""
        return self._history

    @property
    def agent(self) -> NextAgent:
        """Return the underlying agent implementation."""
        return self._agent

    def update_history(self, history: list[Any]) -> None:
        """Update the session history."""
        self._history = history

    def _map_event_to_chunk(self, event: Any) -> AgentChunk | None:
        """Map a Pydantic AI event to an agnostic AgentChunk."""
        match event:
            case PartStartEvent(part=TextPart(content=text)) if text:
                return AgentChunk(content=text, is_thought=False)

            case PartStartEvent(part=ThinkingPart(content=thought)) if thought:
                return AgentChunk(content=thought, is_thought=True)

            case PartDeltaEvent(delta=TextPartDelta(content_delta=text)):
                return AgentChunk(content=text, is_thought=False)

            case PartDeltaEvent(delta=ThinkingPartDelta(content_delta=thought)) if thought:
                return AgentChunk(content=thought, is_thought=True)

        return None

    def _map_tool_call(self, event: Any) -> ToolCallInfo | None:
        """Map a Pydantic AI PartStartEvent to an agnostic ToolCallInfo."""
        match event:
            case PartStartEvent(
                part=ToolCallPart(tool_name=name, args=args, tool_call_id=call_id)
            ):
                return ToolCallInfo(
                    tool_name=name,
                    args=parse_tool_args(args),
                    tool_call_id=call_id or "unknown",
                )
        return None

    def _map_tool_result(self, event: Any) -> ToolCallResultInfo | None:
        """Map a Pydantic AI FunctionToolResultEvent to an agnostic ToolCallResultInfo."""
        match event:
            case FunctionToolResultEvent(
                result=ToolReturnPart(tool_call_id=call_id, content=content)
            ):
                match content:
                    case ToolResult() as tr:
                        return ToolCallResultInfo(tool_call_id=call_id, result=tr)
                    case {"success": success, "content": c} as d:
                        return ToolCallResultInfo(
                            tool_call_id=call_id,
                            result=ToolResult(
                                success=success, content=c, error=d.get("error")
                            ),
                        )
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
    ) -> AgentEventStream:
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

                # 1. Map content chunks (text/thinking)
                if chunk := self._map_event_to_chunk(event):
                    yield chunk
                    continue

                # 2. Map tool calls
                if tool_call := self._map_tool_call(event):
                    yield tool_call
                    continue

                # 3. Map tool results
                if tool_result := self._map_tool_result(event):
                    yield tool_result
                    continue

                # 4. Handle run results (Done or Approval Handshake)
                match event:
                    case AgentRunResultEvent(result=result):
                        if isinstance(result.output, DeferredToolRequests):
                            # Approval Handshake
                            request = self._create_approval_request(event)
                            approval_response: ApprovalResponse | None = yield request

                            if approval_response is None:
                                return

                            approval_results = self._create_approval_results(
                                event, approval_response
                            )
                            # Sync history and break to start next turn
                            self.update_history(result.all_messages())
                            current_prompt = None
                            break
                        else:
                            # Final Result
                            self.update_history(result.all_messages())
                            yield AgentDone(history=self._history)
                            return

            else:
                # Fallback if the stream ends without a result event
                yield AgentDone(history=self._history)
                return


__all__ = [
    "AgentSession",
]
