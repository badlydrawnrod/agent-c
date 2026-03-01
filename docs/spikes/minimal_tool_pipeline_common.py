from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias
from uuid import uuid4


@dataclass(slots=True)
class AgentChunk:
    content: str
    is_thought: bool = False


@dataclass(slots=True)
class ToolCallInfo:
    tool_name: str
    args: Mapping[str, Any]
    tool_call_id: str


@dataclass(slots=True)
class ToolResult:
    success: bool
    content: str
    error: str | None = None


@dataclass(slots=True)
class ToolCallResultInfo:
    tool_call_id: str
    result: ToolResult


@dataclass(slots=True)
class AgentDone:
    pass


@dataclass(slots=True)
class InteractionRequest:
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(slots=True)
class InteractionResponse:
    request_id: str


@dataclass(slots=True)
class ApprovalRequest(InteractionRequest):
    tool_calls: list[ToolCallInfo] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalResponse(InteractionResponse):
    approved: bool
    reason: str | None = None


class ApprovalAuthority(Protocol):
    async def decide(self, request: ApprovalRequest) -> ApprovalResponse:
        ...


class AutoApproveAuthority:
    async def decide(self, request: ApprovalRequest) -> ApprovalResponse:
        return ApprovalResponse(request_id=request.request_id, approved=True)


AgentEvent: TypeAlias = (
    AgentChunk | ToolCallInfo | ToolCallResultInfo | InteractionRequest | AgentDone
)
AgentEventStream: TypeAlias = AsyncGenerator[AgentEvent, InteractionResponse | None]


async def iter_events_with_approval_authority(
    stream: AgentEventStream,
    approval_authority: ApprovalAuthority,
) -> AsyncGenerator[AgentEvent, None]:
    pending_response: InteractionResponse | None = None

    while True:
        try:
            if pending_response is None:
                event = await anext(stream)
            else:
                event = await stream.asend(pending_response)
        except StopAsyncIteration:
            return

        pending_response = None

        if isinstance(event, ApprovalRequest):
            pending_response = await approval_authority.decide(event)
            continue

        yield event


ToolDecisionKind: TypeAlias = Literal["allow", "ask", "deny"]


@dataclass(slots=True)
class ToolDecision:
    kind: ToolDecisionKind
    reason: str | None = None


class ToolPipelineStage(Protocol):
    async def before_tool_use(self, tool_call: ToolCallInfo) -> ToolDecision | None:
        ...

    async def after_tool_use(
        self,
        tool_call: ToolCallInfo,
        result: ToolResult,
    ) -> ToolResult | None:
        ...


class ToolPipeline:
    def __init__(self, stages: Sequence[ToolPipelineStage]) -> None:
        self._stages = list(stages)

    async def before_tool_use(self, tool_call: ToolCallInfo) -> ToolDecision:
        for stage in self._stages:
            decision = await stage.before_tool_use(tool_call)
            if decision is None:
                continue
            if decision.kind != "allow":
                return decision
        return ToolDecision(kind="allow")

    async def after_tool_use(
        self,
        tool_call: ToolCallInfo,
        result: ToolResult,
    ) -> ToolResult:
        current = result
        for stage in self._stages:
            replacement = await stage.after_tool_use(tool_call, current)
            if replacement is not None:
                current = replacement
        return current


class RequireApprovalStage:
    async def before_tool_use(self, tool_call: ToolCallInfo) -> ToolDecision | None:
        if tool_call.tool_name == "report_intent":
            return ToolDecision(kind="allow")
        return ToolDecision(kind="ask")

    async def after_tool_use(
        self,
        tool_call: ToolCallInfo,
        result: ToolResult,
    ) -> ToolResult | None:
        return None


class BlockedToolStage:
    def __init__(self, blocked_tools: set[str]) -> None:
        self._blocked_tools = blocked_tools

    async def before_tool_use(self, tool_call: ToolCallInfo) -> ToolDecision | None:
        if tool_call.tool_name in self._blocked_tools:
            return ToolDecision(kind="deny", reason=f"Blocked tool: {tool_call.tool_name}")
        return None

    async def after_tool_use(
        self,
        tool_call: ToolCallInfo,
        result: ToolResult,
    ) -> ToolResult | None:
        return None


class ResultPrefixStage:
    async def before_tool_use(self, tool_call: ToolCallInfo) -> ToolDecision | None:
        return None

    async def after_tool_use(
        self,
        tool_call: ToolCallInfo,
        result: ToolResult,
    ) -> ToolResult | None:
        return ToolResult(
            success=result.success,
            content=f"[pipeline:{tool_call.tool_name}] {result.content}",
            error=result.error,
        )


@dataclass(slots=True)
class SessionConfig:
    model_name: str | None = None


class AgentSessionProtocol(Protocol):
    @property
    def history(self) -> Sequence[Any]:
        ...

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        ...


class SessionFactoryProtocol(Protocol):
    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        ...
