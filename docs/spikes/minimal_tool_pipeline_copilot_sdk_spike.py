# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, cast
from uuid import uuid4

from copilot import CopilotClient, CopilotSession
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    PostToolUseHookInput,
    PostToolUseHookOutput,
    PreToolUseHookInput,
    PreToolUseHookOutput,
    SessionConfig as CopilotSessionConfig,
    SessionHooks,
    SystemMessageReplaceConfig,
)


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


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


class HookApprovalBroker:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[ApprovalRequest, asyncio.Future[bool]]] = (
            asyncio.Queue()
        )

    async def request_approval(self, tool_call: ToolCallInfo) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        await self._queue.put((ApprovalRequest(tool_calls=[tool_call]), future))
        return await future

    async def next_request(self) -> tuple[ApprovalRequest, asyncio.Future[bool]]:
        return await self._queue.get()


class CopilotToolHooks:
    """Adapter that maps Copilot pre/post hooks into a generic ToolPipeline."""

    def __init__(self, pipeline: ToolPipeline, approval_broker: HookApprovalBroker) -> None:
        self._pipeline = pipeline
        self._approval_broker = approval_broker

    async def on_pre_tool_use(
        self,
        hook_input: PreToolUseHookInput,
        args: dict[str, str],
    ) -> PreToolUseHookOutput | None:
        tool_name = hook_input.get("toolName") or "unknown"
        tool_args = hook_input.get("toolArgs")
        mapped_args = tool_args if isinstance(tool_args, Mapping) else {}
        tool_call = ToolCallInfo(
            tool_name=tool_name,
            args=mapped_args,
            tool_call_id=str(uuid4()),
        )

        decision = await self._pipeline.before_tool_use(tool_call)
        if decision.kind == "deny":
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": decision.reason or "Denied by pipeline.",
            }

        if decision.kind == "ask":
            approved = await self._approval_broker.request_approval(tool_call)
            if not approved:
                return {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Denied by approval authority.",
                }

        return {"permissionDecision": "allow"}

    async def on_post_tool_use(
        self,
        hook_input: PostToolUseHookInput,
        args: dict[str, str],
    ) -> PostToolUseHookOutput | None:
        tool_name = hook_input.get("toolName") or "unknown"
        tool_args = hook_input.get("toolArgs")
        mapped_args = tool_args if isinstance(tool_args, Mapping) else {}
        raw_result = hook_input.get("toolResult")
        result = ToolResult(success=True, content=str(raw_result), error=None)

        tool_call = ToolCallInfo(
            tool_name=tool_name,
            args=mapped_args,
            tool_call_id=str(uuid4()),
        )
        piped_result = await self._pipeline.after_tool_use(tool_call, result)
        return {"modifiedResult": piped_result.content}


class GhToolPipelineSession(AgentSessionProtocol):
    def __init__(
        self,
        session: CopilotSession,
        approval_broker: HookApprovalBroker,
        pipeline: ToolPipeline,
    ) -> None:
        self._session = session
        self._approval_broker = approval_broker
        self._pipeline = pipeline
        self._event_queue: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._history: list[Any] = []
        self._run_active = False
        self._tool_calls_by_id: dict[str, ToolCallInfo] = {}

        def _on_event(event: SessionEvent) -> None:
            self._event_queue.put_nowait(event)

        self._session.on(_on_event)

    @property
    def history(self) -> Sequence[Any]:
        return tuple(self._history)

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        return self._run_impl(prompt=prompt, cancellation_event=cancellation_event)

    async def _run_impl(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None,
    ) -> AgentEventStream:
        if self._run_active:
            raise RuntimeError("Only one active run is allowed per session.")

        self._run_active = True
        self._history.append({"role": "user", "content": prompt})

        event_task: asyncio.Task[SessionEvent] | None = None
        approval_task: asyncio.Task[tuple[ApprovalRequest, asyncio.Future[bool]]] | None = (
            None
        )

        try:
            await self._session.send({"prompt": prompt})

            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    return

                if event_task is None:
                    event_task = asyncio.create_task(self._event_queue.get())
                if approval_task is None:
                    approval_task = asyncio.create_task(self._approval_broker.next_request())

                done, _ = await asyncio.wait(
                    {event_task, approval_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if approval_task in done:
                    request, future = approval_task.result()
                    approval_task = None

                    response = cast(ApprovalResponse | None, (yield request))
                    if response is None:
                        future.set_result(False)
                        return
                    if response.request_id != request.request_id:
                        raise ValueError(
                            "ApprovalResponse.request_id does not match request."
                        )

                    future.set_result(response.approved)
                    continue

                if event_task in done:
                    event = event_task.result()
                    event_task = None

                    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                        delta = getattr(event.data, "delta_content", "") or ""
                        if delta:
                            yield AgentChunk(content=delta, is_thought=False)
                        continue

                    if event.type == SessionEventType.ASSISTANT_REASONING_DELTA:
                        delta = getattr(event.data, "delta_content", "") or ""
                        if delta:
                            yield AgentChunk(content=delta, is_thought=True)
                        continue

                    if event.type == SessionEventType.TOOL_EXECUTION_START:
                        tool_name = getattr(event.data, "tool_name", None) or "unknown"
                        if tool_name != "report_intent":
                            tool_call = ToolCallInfo(
                                tool_name=tool_name,
                                args=_to_mapping(getattr(event.data, "arguments", {})),
                                tool_call_id=(
                                    getattr(event.data, "tool_call_id", None)
                                    or str(uuid4())
                                ),
                            )
                            self._tool_calls_by_id[tool_call.tool_call_id] = tool_call
                            yield tool_call
                        continue

                    if event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
                        tool_call_id = getattr(event.data, "tool_call_id", None) or str(uuid4())
                        success = bool(getattr(event.data, "success", False))
                        content = str(getattr(event.data, "result", "") or "")
                        error_value = getattr(event.data, "error", None)
                        error_text = str(error_value) if error_value else None

                        tool_call = self._tool_calls_by_id.get(
                            tool_call_id,
                            ToolCallInfo(
                                tool_name="unknown",
                                args={},
                                tool_call_id=tool_call_id,
                            ),
                        )
                        result = ToolResult(
                            success=success,
                            content=content,
                            error=error_text,
                        )
                        piped_result = await self._pipeline.after_tool_use(tool_call, result)
                        self._tool_calls_by_id.pop(tool_call_id, None)
                        yield ToolCallResultInfo(
                            tool_call_id=tool_call_id,
                            result=piped_result,
                        )
                        continue

                    if event.type == SessionEventType.SESSION_IDLE:
                        self._history.append({"role": "assistant", "content": "<session idle>"})
                        yield AgentDone()
                        return
        finally:
            self._run_active = False
            if event_task is not None:
                event_task.cancel()
            if approval_task is not None:
                approval_task.cancel()


async def _always_approve_permission_request(
    permission_request: PermissionRequest,
    args: dict[str, str],
) -> PermissionRequestResult:
    return PermissionRequestResult(kind="approved")


class CopilotToolPipelineFactory(SessionFactoryProtocol):
    def __init__(self, client: CopilotClient, root_dir: Path, pipeline: ToolPipeline) -> None:
        self._client = client
        self._root_dir = root_dir
        self._pipeline = pipeline

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        approval_broker = HookApprovalBroker()
        hooks_adapter = CopilotToolHooks(self._pipeline, approval_broker)
        hooks: SessionHooks = {
            "on_pre_tool_use": hooks_adapter.on_pre_tool_use,
            "on_post_tool_use": hooks_adapter.on_post_tool_use,
        }

        session_config = CopilotSessionConfig(
            model=config.model_name or "gpt-5 mini",
            streaming=True,
            on_permission_request=_always_approve_permission_request,
            hooks=hooks,
            skill_directories=[str(self._root_dir / ".github" / "skills")],
            system_message=SystemMessageReplaceConfig(
                mode="replace",
                content=(
                    "You are a coding spike agent with a backend-agnostic tool pipeline. "
                    "To answer project name questions, run a shell command like "
                    "`echo agent-c` and report the result."
                ),
            ),
        )
        sdk_session = await self._client.create_session(session_config)
        return GhToolPipelineSession(
            sdk_session,
            approval_broker=approval_broker,
            pipeline=self._pipeline,
        )


def ensure_copilot_cli_available() -> str:
    cli_path = shutil.which("copilot")
    if not cli_path:
        raise RuntimeError(
            "GitHub Copilot CLI was not found in PATH. Install it and sign in first."
        )
    return cli_path


async def demo_auto_approval() -> None:
    cli_path = ensure_copilot_cli_available()
    client = CopilotClient({"cli_path": cli_path})
    await client.start()

    pipeline = ToolPipeline(
        stages=[
            BlockedToolStage(blocked_tools={"dangerous_tool"}),
            RequireApprovalStage(),
            ResultPrefixStage(),
        ]
    )

    try:
        factory = CopilotToolPipelineFactory(
            client=client,
            root_dir=Path.cwd(),
            pipeline=pipeline,
        )
        session = await factory.create_session(SessionConfig())
        stream = session.run(
            "What is the project name? Use a tool if needed and then answer."
        )
        approval_authority: ApprovalAuthority = AutoApproveAuthority()

        async for event in iter_events_with_approval_authority(
            stream,
            approval_authority,
        ):
            print(event)
    finally:
        await client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(demo_auto_approval())
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
    except StopAsyncIteration:
        pass
