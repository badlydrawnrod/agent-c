# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias, cast
from uuid import uuid4

from copilot import CopilotClient, CopilotSession
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.types import (
    PermissionRequest,
    PermissionRequestResult,
    SessionConfig as CopilotSessionConfig,
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


def _extract_tool_call_from_permission(
    permission_request: PermissionRequest,
    args: Mapping[str, str],
) -> ToolCallInfo:
    tool_name = (
        args.get("tool_name")
        or args.get("toolName")
        or str(permission_request)
        or "unknown"
    )
    tool_call_id = args.get("tool_call_id") or args.get("toolCallId") or str(uuid4())
    return ToolCallInfo(tool_name=tool_name, args=args, tool_call_id=tool_call_id)


class GhApprovalBroker:
    """Bridge Copilot permission callbacks into stream ApprovalRequest events."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[
            tuple[ApprovalRequest, asyncio.Future[PermissionRequestResult]]
        ] = asyncio.Queue()

    async def handle_permission_request(
        self,
        permission_request: PermissionRequest,
        args: dict[str, str],
    ) -> PermissionRequestResult:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[PermissionRequestResult] = loop.create_future()

        tool_call = _extract_tool_call_from_permission(permission_request, args)
        request = ApprovalRequest(tool_calls=[tool_call])

        await self._queue.put((request, future))
        return await future

    async def next_request(
        self,
    ) -> tuple[ApprovalRequest, asyncio.Future[PermissionRequestResult]]:
        return await self._queue.get()


class GhSpikeSession(AgentSessionProtocol):
    """Minimal core loop over GitHub Copilot SDK event and approval channels."""

    def __init__(
        self,
        session: CopilotSession,
        approval_broker: GhApprovalBroker,
    ) -> None:
        self._session = session
        self._approval_broker = approval_broker
        self._event_queue: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._history: list[Any] = []
        self._run_active = False

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
        approval_task: asyncio.Task[
            tuple[ApprovalRequest, asyncio.Future[PermissionRequestResult]]
        ] | None = None

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
                    {event_task, approval_task}, return_when=asyncio.FIRST_COMPLETED
                )

                if approval_task in done:
                    request, future = approval_task.result()
                    approval_task = None

                    response = cast(ApprovalResponse | None, (yield request))
                    if response is None:
                        future.set_result(PermissionRequestResult(kind="denied"))  # type: ignore
                        return
                    if response.request_id != request.request_id:
                        raise ValueError(
                            "ApprovalResponse.request_id does not match request."
                        )

                    if response.approved:
                        future.set_result(PermissionRequestResult(kind="approved"))  # type: ignore
                    else:
                        future.set_result(PermissionRequestResult(kind="denied"))  # type: ignore
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
                            yield ToolCallInfo(
                                tool_name=tool_name,
                                args=_to_mapping(getattr(event.data, "arguments", {})),
                                tool_call_id=(
                                    getattr(event.data, "tool_call_id", None)
                                    or str(uuid4())
                                ),
                            )
                        continue

                    if event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
                        success = bool(getattr(event.data, "success", False))
                        content = str(getattr(event.data, "result", "") or "")
                        error_value = getattr(event.data, "error", None)
                        error_text = str(error_value) if error_value else None
                        yield ToolCallResultInfo(
                            tool_call_id=(
                                getattr(event.data, "tool_call_id", None) or str(uuid4())
                            ),
                            result=ToolResult(
                                success=success,
                                content=content,
                                error=error_text,
                            ),
                        )
                        continue

                    if event.type == SessionEventType.SESSION_IDLE:
                        self._history.append(
                            {"role": "assistant", "content": "<session idle>"}
                        )
                        yield AgentDone()
                        return
        finally:
            self._run_active = False
            if event_task is not None:
                event_task.cancel()
            if approval_task is not None:
                approval_task.cancel()


class CopilotSpikeFactory(SessionFactoryProtocol):
    """Session factory that wires Copilot SDK + approval broker into core loop."""

    def __init__(self, client: CopilotClient, root_dir: Path) -> None:
        self._client = client
        self._root_dir = root_dir

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        broker = GhApprovalBroker()
        session_config = CopilotSessionConfig(
            model=config.model_name or "gpt-5 mini",
            streaming=True,
            on_permission_request=broker.handle_permission_request,
            skill_directories=[str(self._root_dir / ".github" / "skills")],
            system_message=SystemMessageReplaceConfig(
                mode="replace",
                content=(
                    "You are a coding spike agent. To answer project name questions, "
                    "run a shell command like `echo agent-c` and report the result."
                ),
            ),
        )
        sdk_session = await self._client.create_session(session_config)
        return GhSpikeSession(sdk_session, approval_broker=broker)


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

    try:
        factory = CopilotSpikeFactory(client=client, root_dir=Path.cwd())
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
