from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, TypeAlias
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


ToolDecisionKind: TypeAlias = Literal["allow", "ask", "deny"]


@dataclass(slots=True)
class ToolDecision:
    kind: ToolDecisionKind
    reason: str | None = None


@dataclass(slots=True)
class ToolPipelineInteractionRequest(InteractionRequest):
    stage: str = "approval"
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolPipelineInteractionResponse(InteractionResponse):
    decision: ToolDecisionKind
    reason: str | None = None
    remember_for_session: bool = False


class InteractionResponder(Protocol):
    async def decide(
        self,
        request: ToolPipelineInteractionRequest,
    ) -> ToolPipelineInteractionResponse:
        ...


class AutoAllowAndRememberInteractionResponder:
    async def decide(
        self,
        request: ToolPipelineInteractionRequest,
    ) -> ToolPipelineInteractionResponse:
        return ToolPipelineInteractionResponse(
            request_id=request.request_id,
            decision="allow",
            reason=None,
            remember_for_session=True,
        )


AgentEvent: TypeAlias = (
    AgentChunk
    | ToolCallInfo
    | ToolCallResultInfo
    | InteractionRequest
    | ToolPipelineInteractionRequest
    | AgentDone
)
AgentEventStream: TypeAlias = AsyncGenerator[AgentEvent, InteractionResponse | None]


async def iter_events_with_interaction_responder(
    stream: AgentEventStream,
    interaction_responder: InteractionResponder,
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

        if isinstance(event, ToolPipelineInteractionRequest):
            pending_response = await interaction_responder.decide(event)
            continue

        yield event


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

    def build_interaction_request(
        self,
        tool_call: ToolCallInfo,
        context: Mapping[str, Any] | None = None,
    ) -> ToolPipelineInteractionRequest:
        request_context = context or {}
        for stage in self._stages:
            builder = getattr(stage, "build_interaction_request", None)
            if callable(builder):
                request = builder(tool_call, request_context)
                if isinstance(request, ToolPipelineInteractionRequest):
                    return request

        return ToolPipelineInteractionRequest(
            stage="approval",
            tool_calls=[tool_call],
            context=request_context,
        )

    def resolve_interaction_response(
        self,
        tool_call: ToolCallInfo,
        response: ToolPipelineInteractionResponse,
    ) -> ToolDecision:
        for stage in self._stages:
            resolver = getattr(stage, "resolve_interaction_response", None)
            if callable(resolver):
                decision = resolver(tool_call, response)
                if isinstance(decision, ToolDecision):
                    return decision

        return ToolDecision(kind=response.decision, reason=response.reason)


@dataclass(slots=True)
class SessionGrantStore:
    granted_keys: set[str] = field(default_factory=set)

    def has_grant(self, grant_key: str) -> bool:
        return grant_key in self.granted_keys

    def add_grant(self, grant_key: str) -> None:
        self.granted_keys.add(grant_key)


def default_grant_key_builder(tool_call: ToolCallInfo) -> str:
    return tool_call.tool_name


class InteractiveApprovalStage:
    def __init__(
        self,
        grant_store: SessionGrantStore | None = None,
        grant_key_builder: Callable[[ToolCallInfo], str] = default_grant_key_builder,
        auto_allow_tools: set[str] | None = None,
    ) -> None:
        self._grant_store = grant_store or SessionGrantStore()
        self._grant_key_builder = grant_key_builder
        self._auto_allow_tools = auto_allow_tools or set()

    async def before_tool_use(self, tool_call: ToolCallInfo) -> ToolDecision | None:
        if tool_call.tool_name in self._auto_allow_tools:
            return ToolDecision(kind="allow")

        grant_key = self._grant_key_builder(tool_call)
        if self._grant_store.has_grant(grant_key):
            return ToolDecision(kind="allow")
        return ToolDecision(kind="ask")

    async def after_tool_use(
        self,
        tool_call: ToolCallInfo,
        result: ToolResult,
    ) -> ToolResult | None:
        return None

    def build_interaction_request(
        self,
        tool_call: ToolCallInfo,
        context: Mapping[str, Any],
    ) -> ToolPipelineInteractionRequest:
        return ToolPipelineInteractionRequest(
            stage="approval",
            tool_calls=[tool_call],
            context=context,
        )

    def resolve_interaction_response(
        self,
        tool_call: ToolCallInfo,
        response: ToolPipelineInteractionResponse,
    ) -> ToolDecision:
        if response.decision == "allow" and response.remember_for_session:
            self._grant_store.add_grant(self._grant_key_builder(tool_call))
        return ToolDecision(kind=response.decision, reason=response.reason)


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


ToolHandler: TypeAlias = Callable[[Mapping[str, Any], Any], ToolResult]


@dataclass(slots=True)
class RegisteredTool:
    name: str
    description: str
    handler: ToolHandler
    parameters: Mapping[str, Any] = field(default_factory=dict)
    requires_approval: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.name] = tool

    def disable(self, tool_name: str) -> None:
        self._tools.pop(tool_name, None)

    def resolve(self, tool_name: str) -> RegisteredTool | None:
        return self._tools.get(tool_name)

    @property
    def tools(self) -> tuple[RegisteredTool, ...]:
        return tuple(self._tools.values())


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
