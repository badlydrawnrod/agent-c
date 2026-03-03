# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    FunctionToolResultEvent,
    Tool,
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
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.tools import RunContext
from pydantic_core import to_jsonable_python

from session_persistence_adapter import (
    CommonSessionRecord,
    CommonSessionState,
    SessionCheckpoint,
    SessionCheckpointStore,
    SessionInterchangeCodec,
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
    session_file: Path | None = None
    session_key: str = "spike-default"
    parent_checkpoint_id: str | None = None
    checkpoint_id: str | None = None
    checkpoint_label: str | None = None
    initial_history: Sequence[Any] | None = None


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


@dataclass(slots=True)
class SpikeDeps:
    project_name: str = "agent-c"


def project_name_tool(ctx: RunContext[SpikeDeps]) -> ToolResult:
    return ToolResult(success=True, content=ctx.deps.project_name)


@dataclass(slots=True)
class JsonlHistoryEntry:
    session_key: str
    role: str
    content: str
    event_type: str
    checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class JsonlSessionPersistenceAdapter(SessionCheckpointStore, SessionInterchangeCodec):
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: JsonlHistoryEntry) -> None:
        payload = asdict(entry)
        with self._file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self._file_path.exists():
            return []

        rows: list[dict[str, Any]] = []
        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def _write_rows(self, rows: list[dict[str, Any]]) -> None:
        with self._file_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def load(self, session_key: str) -> list[JsonlHistoryEntry]:
        if not self._file_path.exists():
            return []

        entries: list[JsonlHistoryEntry] = []
        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("session_key") != session_key:
                    continue
                entries.append(
                    JsonlHistoryEntry(
                        session_key=row.get("session_key", ""),
                        role=row.get("role", "unknown"),
                        content=row.get("content", ""),
                        event_type=row.get("event_type", "unknown"),
                        checkpoint_id=row.get("checkpoint_id"),
                        metadata=row.get("metadata", {}),
                    )
                )
        return entries

    def _checkpoint_map(self, session_key: str) -> dict[str, SessionCheckpoint]:
        checkpoints: dict[str, SessionCheckpoint] = {}
        for entry in self.load(session_key):
            if entry.event_type != "checkpoint":
                continue
            checkpoint = SessionCheckpoint(
                checkpoint_id=entry.metadata.get("checkpoint_id", ""),
                parent_checkpoint_id=entry.metadata.get("parent_checkpoint_id"),
                label=entry.metadata.get("label"),
                metadata=entry.metadata.get("metadata", {}),
            )
            checkpoints[checkpoint.checkpoint_id] = checkpoint
        return checkpoints

    def create_checkpoint(
        self,
        session_key: str,
        parent_checkpoint_id: str | None = None,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        checkpoint_id = str(uuid4())
        self.append(
            JsonlHistoryEntry(
                session_key=session_key,
                role="system",
                content=label or checkpoint_id,
                event_type="checkpoint",
                checkpoint_id=checkpoint_id,
                metadata={
                    "checkpoint_id": checkpoint_id,
                    "parent_checkpoint_id": parent_checkpoint_id,
                    "label": label,
                    "metadata": metadata or {},
                },
            )
        )
        self.set_active_checkpoint(session_key, checkpoint_id)
        return checkpoint_id

    def set_active_checkpoint(self, session_key: str, checkpoint_id: str | None) -> None:
        self.append(
            JsonlHistoryEntry(
                session_key=session_key,
                role="system",
                content=checkpoint_id or "",
                event_type="active_checkpoint",
                checkpoint_id=checkpoint_id,
                metadata={"checkpoint_id": checkpoint_id},
            )
        )

    def get_active_checkpoint(self, session_key: str) -> str | None:
        active_checkpoint_id: str | None = None
        latest_checkpoint_id: str | None = None
        for entry in self.load(session_key):
            if entry.event_type == "checkpoint":
                latest_checkpoint_id = entry.checkpoint_id
            if entry.event_type == "active_checkpoint":
                active_checkpoint_id = entry.metadata.get("checkpoint_id")
        return active_checkpoint_id or latest_checkpoint_id

    def save_native(
        self,
        session_key: str,
        native_state: list[Any],
        checkpoint_id: str | None = None,
    ) -> str:
        target_checkpoint_id = checkpoint_id or self.get_active_checkpoint(session_key)
        if target_checkpoint_id is None:
            target_checkpoint_id = self.create_checkpoint(session_key=session_key)

        rows = self._read_rows()
        rows = [
            row
            for row in rows
            if not (
                row.get("session_key") == session_key
                and row.get("event_type") == "native_snapshot"
                and row.get("checkpoint_id") == target_checkpoint_id
            )
        ]
        rows.append(
            asdict(
                JsonlHistoryEntry(
                    session_key=session_key,
                    role="system",
                    content="native_snapshot",
                    event_type="native_snapshot",
                    checkpoint_id=target_checkpoint_id,
                    metadata={"native": to_jsonable_python(native_state)},
                )
            )
        )
        self._write_rows(rows)
        return target_checkpoint_id

    def load_native(
        self,
        session_key: str,
        checkpoint_id: str | None = None,
    ) -> list[Any] | None:
        target_checkpoint_id = checkpoint_id or self.get_active_checkpoint(session_key)
        if target_checkpoint_id is None:
            return None

        latest_snapshot: list[Any] | None = None
        for entry in self.load(session_key):
            if entry.event_type != "native_snapshot":
                continue
            if entry.checkpoint_id != target_checkpoint_id:
                continue
            snapshot = entry.metadata.get("native")
            if isinstance(snapshot, list):
                latest_snapshot = snapshot

        return latest_snapshot

    def build_context(
        self,
        session_key: str,
        checkpoint_id: str | None = None,
    ) -> list[Any] | None:
        target_checkpoint_id = checkpoint_id or self.get_active_checkpoint(session_key)
        if target_checkpoint_id is None:
            return None

        checkpoints = self._checkpoint_map(session_key)
        lineage: set[str] = set()
        cursor: str | None = target_checkpoint_id
        while cursor is not None:
            lineage.add(cursor)
            checkpoint = checkpoints.get(cursor)
            if checkpoint is None:
                break
            cursor = checkpoint.parent_checkpoint_id

        context: list[Any] = []
        for entry in self.load(session_key):
            if entry.checkpoint_id not in lineage:
                continue
            if entry.event_type in {"checkpoint", "active_checkpoint", "native_snapshot"}:
                continue
            context.append(asdict(entry))

        return context

    def export_common(self, session_key: str) -> CommonSessionState:
        active_checkpoint_id = self.get_active_checkpoint(session_key)
        records = [
            CommonSessionRecord(
                role=entry.role,
                content=entry.content,
                kind=entry.event_type,
                checkpoint_id=entry.checkpoint_id,
                metadata=entry.metadata,
            )
            for entry in self.load(session_key)
            if entry.event_type not in {"checkpoint", "active_checkpoint"}
        ]
        checkpoints = list(self._checkpoint_map(session_key).values())
        return CommonSessionState(
            session_key=session_key,
            active_checkpoint_id=active_checkpoint_id,
            checkpoints=checkpoints,
            records=records,
        )

    def import_common(
        self,
        common_state: CommonSessionState,
        target_session_key: str | None = None,
    ) -> str:
        effective_session_key = target_session_key or common_state.session_key
        for checkpoint in common_state.checkpoints:
            self.append(
                JsonlHistoryEntry(
                    session_key=effective_session_key,
                    role="system",
                    content=checkpoint.label or checkpoint.checkpoint_id,
                    event_type="checkpoint",
                    checkpoint_id=checkpoint.checkpoint_id,
                    metadata={
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "parent_checkpoint_id": checkpoint.parent_checkpoint_id,
                        "label": checkpoint.label,
                        "metadata": checkpoint.metadata,
                    },
                )
            )
        for record in common_state.records:
            self.append(
                JsonlHistoryEntry(
                    session_key=effective_session_key,
                    role=record.role,
                    content=record.content,
                    event_type=record.kind,
                    checkpoint_id=record.checkpoint_id,
                    metadata=record.metadata,
                )
            )
        if common_state.active_checkpoint_id is not None:
            self.set_active_checkpoint(effective_session_key, common_state.active_checkpoint_id)
        return effective_session_key


def build_pydantic_agent(
    model_name: str,
    ollama_base_url: str,
) -> Agent[SpikeDeps, str | DeferredToolRequests]:
    model = OpenAIChatModel(
        provider=OllamaProvider(base_url=ollama_base_url),
        model_name=model_name,
    )

    tools: list[Tool[SpikeDeps]] = [
        Tool(project_name_tool, takes_ctx=True, requires_approval=True)
    ]

    return Agent(
        model=model,
        deps_type=SpikeDeps,
        output_type=(str, DeferredToolRequests),
        tools=tools,
        system_prompt=(
            "You are a spike backend. Use the project_name_tool to answer questions "
            "about the project name."
        ),
    )


class PydanticAICoreSession(AgentSessionProtocol):
    def __init__(
        self,
        agent: Agent[SpikeDeps, str | DeferredToolRequests],
        deps: SpikeDeps,
        store: SessionCheckpointStore,
        session_key: str,
        checkpoint_id: str,
        history: list[Any] | None = None,
    ) -> None:
        self._agent = agent
        self._deps = deps
        self._store = store
        self._session_key = session_key
        self._checkpoint_id = checkpoint_id
        self._history = history or []
        self._run_active = False
        self._store.set_active_checkpoint(self._session_key, self._checkpoint_id)

    @property
    def history(self) -> Sequence[Any]:
        return tuple(self._history)

    def _persist(
        self,
        role: str,
        content: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(self._store, JsonlSessionPersistenceAdapter):
            raise TypeError("Expected JsonlSessionPersistenceAdapter for event logging")

        self._store.append(
            JsonlHistoryEntry(
                session_key=self._session_key,
                role=role,
                content=content,
                event_type=event_type,
                checkpoint_id=self._checkpoint_id,
                metadata=metadata or {},
            )
        )

    def _map_chunk(self, event: Any) -> AgentChunk | None:
        match event:
            case PartStartEvent(part=TextPart(content=text)) if text:
                return AgentChunk(content=text, is_thought=False)
            case PartStartEvent(part=ThinkingPart(content=thought)) if thought:
                return AgentChunk(content=thought, is_thought=True)
            case PartDeltaEvent(delta=TextPartDelta(content_delta=text)) if text:
                return AgentChunk(content=text, is_thought=False)
            case PartDeltaEvent(
                delta=ThinkingPartDelta(content_delta=thought)
            ) if thought:
                return AgentChunk(content=thought, is_thought=True)
        return None

    def _map_tool_call(self, event: Any) -> ToolCallInfo | None:
        match event:
            case PartStartEvent(
                part=ToolCallPart(tool_name=name, args=args, tool_call_id=call_id)
            ):
                mapped_args = args if isinstance(args, Mapping) else {}
                return ToolCallInfo(
                    tool_name=name,
                    args=mapped_args,
                    tool_call_id=call_id or "unknown",
                )
        return None

    def _map_tool_result(self, event: Any) -> ToolCallResultInfo | None:
        if not isinstance(event, FunctionToolResultEvent):
            return None
        if not isinstance(event.result, ToolReturnPart):
            return None

        content = event.result.content
        if isinstance(content, ToolResult):
            result = content
        else:
            result = ToolResult(success=True, content=str(content), error=None)

        return ToolCallResultInfo(tool_call_id=event.result.tool_call_id, result=result)

    def _build_approval_request(
        self, deferred: DeferredToolRequests
    ) -> ApprovalRequest:
        return ApprovalRequest(
            tool_calls=[
                ToolCallInfo(
                    tool_name=call.tool_name,
                    args=call.args if isinstance(call.args, Mapping) else {},
                    tool_call_id=call.tool_call_id,
                )
                for call in deferred.approvals
            ]
        )

    def _build_deferred_results(
        self,
        deferred: DeferredToolRequests,
        response: ApprovalResponse,
    ) -> DeferredToolResults:
        results = DeferredToolResults()
        for call in deferred.approvals:
            results.approvals[call.tool_call_id] = (
                response.approved
                if response.approved
                else ToolDenied(
                    response.reason
                    or "Denied by approval authority. Do not retry without new approval."
                )
            )
        return results

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
        approval_results: DeferredToolResults | None = None
        current_prompt: str | None = prompt
        assistant_parts: list[str] = []

        self._persist(role="user", content=prompt, event_type="user_prompt")

        try:
            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    return

                should_restart = False
                async for event in self._agent.run_stream_events(
                    current_prompt,
                    message_history=self._history,
                    deferred_tool_results=approval_results,
                    deps=self._deps,
                ):
                    if cancellation_event is not None and cancellation_event.is_set():
                        return

                    chunk = self._map_chunk(event)
                    if chunk is not None:
                        if not chunk.is_thought:
                            assistant_parts.append(chunk.content)
                        yield chunk
                        continue

                    tool_call = self._map_tool_call(event)
                    if tool_call is not None:
                        self._persist(
                            role="tool",
                            content=tool_call.tool_name,
                            event_type="tool_call",
                            metadata={
                                "tool_call_id": tool_call.tool_call_id,
                                "args": dict(tool_call.args),
                            },
                        )
                        yield tool_call
                        continue

                    tool_result = self._map_tool_result(event)
                    if tool_result is not None:
                        self._persist(
                            role="tool",
                            content=tool_result.result.content,
                            event_type="tool_result",
                            metadata={
                                "tool_call_id": tool_result.tool_call_id,
                                "success": tool_result.result.success,
                                "error": tool_result.result.error,
                            },
                        )
                        yield tool_result
                        continue

                    if isinstance(event, AgentRunResultEvent):
                        self._history = list(event.result.all_messages())
                        self._checkpoint_id = self._store.save_native(
                            session_key=self._session_key,
                            native_state=self._history,
                            checkpoint_id=self._checkpoint_id,
                        )

                        if isinstance(event.result.output, DeferredToolRequests):
                            request = self._build_approval_request(event.result.output)
                            response = yield request
                            if response is None:
                                return
                            if not isinstance(response, ApprovalResponse):
                                raise TypeError(
                                    "Expected ApprovalResponse for ApprovalRequest."
                                )
                            if response.request_id != request.request_id:
                                raise ValueError(
                                    "ApprovalResponse.request_id does not match request."
                                )

                            self._persist(
                                role="system",
                                content=(
                                    "approved"
                                    if response.approved
                                    else f"denied: {response.reason or ''}"
                                ),
                                event_type="approval_decision",
                                metadata={"request_id": request.request_id},
                            )

                            approval_results = self._build_deferred_results(
                                event.result.output,
                                response,
                            )
                            current_prompt = None
                            should_restart = True
                            break

                        assistant_text = "".join(assistant_parts).strip()
                        if assistant_text:
                            self._persist(
                                role="assistant",
                                content=assistant_text,
                                event_type="assistant_message",
                            )
                        yield AgentDone()
                        return

                if should_restart:
                    continue

                assistant_text = "".join(assistant_parts).strip()
                if assistant_text:
                    self._persist(
                        role="assistant",
                        content=assistant_text,
                        event_type="assistant_message",
                    )
                yield AgentDone()
                return
        finally:
            self._run_active = False


class PydanticAISpikeFactory(SessionFactoryProtocol):
    def __init__(self, deps: SpikeDeps) -> None:
        self._deps = deps

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        model_name = config.model_name or "gpt-oss:20b"
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        file_path = config.session_file or Path("docs/spikes/session_history.jsonl")
        store: SessionCheckpointStore = JsonlSessionPersistenceAdapter(
            file_path=file_path
        )
        checkpoint_id = config.checkpoint_id or store.get_active_checkpoint(
            config.session_key
        )
        if checkpoint_id is None:
            checkpoint_id = store.create_checkpoint(
                session_key=config.session_key,
                parent_checkpoint_id=config.parent_checkpoint_id,
                label=config.checkpoint_label,
            )
        initial_history = list(config.initial_history) if config.initial_history else None
        if initial_history is None:
            initial_history = store.load_native(
                session_key=config.session_key,
                checkpoint_id=checkpoint_id,
            ) or []
        agent = build_pydantic_agent(model_name, ollama_base_url)
        return PydanticAICoreSession(
            agent=agent,
            deps=self._deps,
            store=store,
            session_key=config.session_key,
            checkpoint_id=checkpoint_id,
            history=initial_history,
        )


def _ollama_health_url(ollama_base_url: str) -> str:
    split = urlsplit(ollama_base_url)
    return f"{split.scheme}://{split.netloc}/api/tags"


def ensure_ollama_is_running(ollama_base_url: str) -> None:
    health_url = _ollama_health_url(ollama_base_url)
    try:
        with urlopen(health_url, timeout=2.0) as response:
            if response.status >= 400:
                raise URLError(f"HTTP {response.status}")
    except Exception as exc:
        raise RuntimeError(
            "Could not reach Ollama. Please start Ollama first (for example: `ollama serve`) "
            f"and ensure model `gpt-oss:20b` is available (`ollama pull gpt-oss:20b`). "
            f"Tried endpoint: {health_url}"
        ) from exc


async def demo_auto_approval() -> None:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ensure_ollama_is_running(ollama_base_url)

    session_file = Path(
        os.getenv("SPIKE_SESSION_FILE", "docs/spikes/session_history.jsonl")
    )
    session_key = os.getenv("SPIKE_SESSION_KEY", "spike-default")
    prompt = os.getenv("SPIKE_PROMPT", "What is the project name?")

    factory = PydanticAISpikeFactory(deps=SpikeDeps(project_name="agent-c"))
    session = await factory.create_session(
        SessionConfig(session_file=session_file, session_key=session_key)
    )
    stream = session.run(prompt)
    approval_authority: ApprovalAuthority = AutoApproveAuthority()

    async for event in iter_events_with_approval_authority(
        stream,
        approval_authority,
    ):
        print(event)


def demo_checkpoint_branching() -> None:
    session_file = Path(
        os.getenv(
            "SPIKE_SESSION_FILE",
            "docs/spikes/session_history.checkpoint_demo.jsonl",
        )
    )
    session_key = os.getenv(
        "SPIKE_SESSION_KEY",
        os.getenv("SPIKE_SESSION_ID", "spike-checkpoint-demo"),
    )

    store = JsonlSessionPersistenceAdapter(file_path=session_file)

    root_checkpoint = store.create_checkpoint(
        session_key=session_key,
        label="root",
    )
    store.append(
        JsonlHistoryEntry(
            session_key=session_key,
            role="assistant",
            content="root-message",
            event_type="assistant_message",
            checkpoint_id=root_checkpoint,
        )
    )

    branch_a = store.create_checkpoint(
        session_key=session_key,
        parent_checkpoint_id=root_checkpoint,
        label="branch-a",
    )
    store.append(
        JsonlHistoryEntry(
            session_key=session_key,
            role="assistant",
            content="branch-a-message",
            event_type="assistant_message",
            checkpoint_id=branch_a,
        )
    )

    branch_b = store.create_checkpoint(
        session_key=session_key,
        parent_checkpoint_id=root_checkpoint,
        label="branch-b",
    )
    store.append(
        JsonlHistoryEntry(
            session_key=session_key,
            role="assistant",
            content="branch-b-message",
            event_type="assistant_message",
            checkpoint_id=branch_b,
        )
    )

    store.set_active_checkpoint(session_key, branch_a)
    active_path_a = [
        row.get("content", "")
        for row in (store.build_context(session_key=session_key) or [])
    ]

    store.set_active_checkpoint(session_key, branch_b)
    active_path_b = [
        row.get("content", "")
        for row in (store.build_context(session_key=session_key) or [])
    ]

    store.save_native(
        session_key=session_key,
        native_state=[{"checkpoint": "branch-a-v1"}],
        checkpoint_id=branch_a,
    )
    store.save_native(
        session_key=session_key,
        native_state=[{"checkpoint": "branch-a-v2"}],
        checkpoint_id=branch_a,
    )
    latest_branch_a_state = store.load_native(
        session_key=session_key,
        checkpoint_id=branch_a,
    )

    print("Checkpoint demo complete")
    print(f"Session file: {session_file}")
    print(f"Session key: {session_key}")
    print(f"Root checkpoint: {root_checkpoint}")
    print(f"Branch A checkpoint: {branch_a}")
    print(f"Branch B checkpoint: {branch_b}")
    print(f"Active path for branch-a: {active_path_a}")
    print(f"Active path for branch-b: {active_path_b}")
    print(f"Latest native snapshot at branch-a: {latest_branch_a_state}")


if __name__ == "__main__":
    demo_mode = os.getenv("SPIKE_DEMO_MODE", "auto-approval")
    try:
        if demo_mode == "checkpoint-branching":
            demo_checkpoint_branching()
        else:
            asyncio.run(demo_auto_approval())
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
    except StopAsyncIteration:
        pass
