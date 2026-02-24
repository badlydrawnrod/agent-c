# Agent C — Inner Core Specification

> [!IMPORTANT]
> This prompt file is a planning aid and is non-authoritative.
> The normative inner-core contract is defined in `docs/inner-core-spec.md`.

The inner core is Agent C's foundational layer — the minimal set of abstractions that every backend, middleware, adapter, and UI depends on. It defines *what* an agentic session is, *how* events flow, and *where* extensibility points live. Everything outside this boundary (UI rendering, command parsing, TUI widgets, provider configuration) is a separate concern.

> **Design philosophy**: The inner core should be small enough that a new backend can implement it in a single file, yet powerful enough that the full coding-agent experience can be built on top without reaching inside the loop.

---

## 1. Scope

The inner core owns exactly four things:

1. **Event types** — the typed vocabulary of the event stream
2. **Session protocol** — the bidirectional async generator contract
3. **Context pipeline** — pre-call transformation of what the LLM sees
4. **Tool lifecycle hooks** — observation and interception of tool execution

Everything else — middleware, adapters, UI, command parsing, provider discovery, skill loading, patching engine — is *outside* the inner core and depends on it.

### What is NOT in the inner core

| Concern | Where it lives |
|---|---|
| Debouncing / batching | Middleware layer |
| Textual or console rendering | UI / Adapter layer |
| Slash commands (`/model`, `/clear`) | Command layer |
| `providers.toml` discovery | Backend configuration |
| Skill / `AGENTS.md` loading | Session factory or entrypoint |
| File patching engine | Tool implementation |
| `RunDeps` construction | Entrypoint / composition root |

---

## 2. Event Types

All events are plain dataclasses with no framework dependencies. A backend must yield exactly these types — no backend-specific types may leak upstream.

### 2.1 Content Events

```python
@dataclass
class AgentChunk:
    """Streamed content from the LLM."""
    content: str
    is_thought: bool = False
```

```python
@dataclass
class ToolCallInfo:
    """The LLM is invoking a tool. Args are read-only (display/logging only)."""
    tool_name: str
    args: Mapping[str, Any]
    tool_call_id: str
```

```python
@dataclass
class ToolCallResultInfo:
    """A tool finished executing."""
    tool_call_id: str
    result: ToolResult

@dataclass
class ToolResult:
    success: bool
    content: str
    error: str | None = None
```

### 2.2 Notification

```python
class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

@dataclass
class Notification:
    """Unidirectional status message. No response expected."""
    message: str
    severity: Severity = Severity.INFO
```

Backends yield `Notification` for progress updates, transient errors, compaction status, or any informational message that isn't LLM content. It passes through middleware untouched.

### 2.3 Interaction Protocol

All bidirectional flows share a common base so that middleware and the stream type never need to change when new interaction types are added.

```python
@dataclass
class InteractionRequest:
    """Base for all loop→consumer questions."""
    request_id: str = field(default_factory=lambda: str(uuid4()))

@dataclass
class InteractionResponse:
    """Base for all consumer→loop answers."""
    request_id: str
```

**Approval**:
```python
@dataclass
class ApprovalRequest(InteractionRequest):
    tool_calls: list[ToolCallInfo]

@dataclass
class ApprovalResponse(InteractionResponse):
    approved: bool
    reason: str | None = None
```

**User input**:
```python
@dataclass
class UserInputRequest(InteractionRequest):
    question: str
    options: list[UserInputOption]
    allow_freeform: bool = False
    placeholder: str | None = None

@dataclass
class UserInputResponse(InteractionResponse):
    response: str
```

### 2.4 Completion Signal

```python
@dataclass
class AgentDone:
    """Turn complete. The session owns the history — this is a pure signal."""
    pass
```

`AgentDone` carries no payload. History is accessible via the session's `history` property, not through the event stream.

### 2.5 The Event Union

```python
type AgentEvent = (
    AgentChunk
    | ToolCallInfo
    | ToolCallResultInfo
    | Notification
    | InteractionRequest
    | AgentDone
)

type AgentEventStream = AsyncGenerator[
    AgentEvent,
    InteractionResponse | None
]
```

The union includes `InteractionRequest` (not its subtypes), so adding new interaction types never changes the union or the stream type signature.

---

## 3. Session Protocol

### 3.1 AgentSessionProtocol

```python
class AgentSessionProtocol(Protocol):
    @property
    def history(self) -> Any:
        """Backend-specific conversation history (read-only)."""
        ...

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream: ...
```

**Contract**:

- `run()` returns a bidirectional async generator.
- Yields `AgentDone` as its final event on normal completion, then terminates.
- On cancellation: `return` immediately, no `AgentDone`.
- On error: exception propagates, no `AgentDone`.
- Maintains conversation history internally across `run()` calls.
- Only one `run()` may be active per session at a time (concurrency guard).

### 3.2 SessionFactoryProtocol

```python
class SessionFactoryProtocol(Protocol):
    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol: ...
```

The factory is the boundary between backend-specific construction (model loading, API key validation, provider setup) and the backend-agnostic world. The UI layer depends only on this protocol.

### 3.3 SessionConfig

```python
@dataclass
class SessionConfig:
    model_name: str | None = None
    clear_history: bool = False
    skill_dirs: list[Path] | None = None
    deps: RunDeps | None = None
```

Pure data describing *what* session to create, without knowing *how*. The factory translates this into backend-specific construction.

---

## 4. Context Pipeline

The context pipeline runs **before each LLM call**, transforming the conversation context that the LLM will see. This is distinct from middleware (which operates on events *after* the LLM speaks).

### 4.1 Purpose

- **Compaction**: Summarize old messages when approaching the context window limit.
- **Context injection**: Insert dynamic information (file contents, search results, timestamps) before a turn.
- **Message filtering**: Remove UI-only messages, collapse redundant tool results, strip metadata.
- **Cross-provider normalization**: Transform thinking blocks or provider-specific constructs when switching models.

### 4.2 ContextTransform Protocol

```python
class ContextTransform(Protocol):
    async def transform(
        self,
        messages: list[Any],
        model_context: ModelContext,
    ) -> list[Any]:
        """Transform the message list before it is sent to the LLM.

        Args:
            messages: The current conversation history (backend-specific format).
            model_context: Metadata about the target model (context window, etc.).

        Returns:
            The transformed message list.
        """
        ...

@dataclass
class ModelContext:
    """Metadata about the model, available to context transforms."""
    model_name: str
    context_window: int | None = None
    max_output_tokens: int | None = None
```

### 4.3 Integration Point

The session calls registered transforms in order, immediately before each LLM invocation:

```
prompt arrives → history + prompt assembled → [transform₁ → transform₂ → ...] → LLM call
```

A session accepts transforms at construction time. The factory or entrypoint is responsible for wiring them. The loop itself does not know what the transforms do — it only calls them in sequence.

### 4.4 Compaction as a ContextTransform

Automatic compaction is a `ContextTransform` implementation, not a built-in feature of the loop:

```python
class CompactionTransform:
    """Summarize old messages when approaching the context window limit."""

    def __init__(self, reserve_tokens: int = 16384, keep_recent_tokens: int = 20000):
        self._reserve = reserve_tokens
        self._keep_recent = keep_recent_tokens

    async def transform(self, messages, model_context):
        if not self._should_compact(messages, model_context):
            return messages
        cut_point = self._find_cut_point(messages)
        summary = await self._summarize(messages[:cut_point], model_context)
        return [summary] + messages[cut_point:]
```

This keeps the loop simple while enabling sophisticated context management. A notification (`Notification(message="Compacting conversation...", severity=Severity.INFO)`) can be yielded by the loop if the transform signals that compaction occurred.

---

## 5. Tool Lifecycle Hooks

The current approval flow (`ApprovalRequest`/`ApprovalResponse`) is a special case of a more general pattern: observing and intercepting tool execution. The inner core defines a minimal hook protocol that subsumes approval and opens the door for logging, cost tracking, and custom policies.

### 5.1 ToolHook Protocol

```python
class ToolAction(Enum):
    """What the hook decided."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"        # Delegate to the interaction protocol (yield ApprovalRequest)

@dataclass
class ToolDecision:
    """Result of a before_tool_call hook."""
    action: ToolAction = ToolAction.ALLOW
    reason: str | None = None

class ToolHook(Protocol):
    async def before_tool_call(self, tool_call: ToolCallInfo) -> ToolDecision:
        """Called before a tool executes. Return a decision.

        - ALLOW: proceed with execution.
        - DENY: skip execution, feed denial reason to the LLM.
        - ASK: yield an ApprovalRequest to the consumer and await the response.
        """
        ...

    async def after_tool_call(
        self, tool_call: ToolCallInfo, result: ToolCallResultInfo
    ) -> None:
        """Called after a tool completes. Observation only — cannot modify the result."""
        ...
```

### 5.2 Built-in Policy: RequiresApprovalHook

The current approval behavior is expressed as a `ToolHook`:

```python
class RequiresApprovalHook:
    """Returns ASK for tools marked as requiring approval, ALLOW for others."""

    def __init__(self, approval_tools: set[str]):
        self._approval_tools = approval_tools

    async def before_tool_call(self, tool_call: ToolCallInfo) -> ToolDecision:
        if tool_call.tool_name in self._approval_tools:
            return ToolDecision(action=ToolAction.ASK)
        return ToolDecision(action=ToolAction.ALLOW)

    async def after_tool_call(self, tool_call, result):
        pass  # No observation needed
```

### 5.3 Integration

Hooks are registered on the session at construction time. The loop calls them in order:

1. For each tool call the LLM wants to execute:
   - Call `hook.before_tool_call(tool_call)` for each registered hook (first `DENY` or `ASK` wins).
   - If `ASK`: yield `ApprovalRequest`, await `ApprovalResponse` via `asend`.
   - If `DENY`: feed denial to LLM, skip execution.
   - If `ALLOW`: execute the tool.
2. After execution, call `hook.after_tool_call(tool_call, result)` for all hooks.

This means the approval handshake is no longer hard-wired into the loop — it's triggered by hook policy. The loop only needs to know how to yield an `InteractionRequest` and receive an `InteractionResponse`.

---

## 6. Session Persistence

The inner core defines a persistence protocol that backends *may* implement. In-memory sessions remain valid — persistence is opt-in.

### 6.1 SessionStore Protocol

```python
@dataclass
class SessionEntry:
    """A single entry in a session's history graph."""
    id: str
    parent_id: str | None
    timestamp: float
    entry_type: str          # "message", "compaction", "model_change", etc.
    data: dict[str, Any]     # Backend-specific payload

class SessionStore(Protocol):
    async def append(self, session_id: str, entry: SessionEntry) -> None:
        """Append an entry to a session."""
        ...

    async def load(self, session_id: str) -> list[SessionEntry]:
        """Load all entries for a session, ordered by the path from root to leaf."""
        ...

    async def list_sessions(self) -> list[str]:
        """List all available session IDs."""
        ...

    async def branch(self, session_id: str, from_entry_id: str) -> str:
        """Create a new branch from an existing entry. Returns the new session ID."""
        ...
```

### 6.2 Design Notes

- Entries form a tree via `id`/`parent_id`. This enables conversation branching — navigating back to a prior point and forking — without duplicating data.
- The `data` field is intentionally `dict[str, Any]` because history format is backend-specific. The store is a dumb append-only log; it does not interpret the data.
- A JSONL file implementation is the expected default: one file per session, one JSON object per line.
- The session reads from the store on construction and appends entries as the conversation progresses. The store is injected via `SessionConfig` or `RunDeps`.

---

## 7. RunDeps

Runtime dependencies injected into the session and made available to tools and hooks:

```python
@dataclass
class RunDeps:
    root_dirs: list[Path]                            # Filesystem security boundary
    skill_dirs: list[Path]                           # Skill discovery paths
    user_input_handler: UserInputHandler | None       # Broker for mid-turn user input
    context_transforms: list[ContextTransform]        # Pre-call context pipeline (§4)
    tool_hooks: list[ToolHook]                        # Tool lifecycle hooks (§5)
    session_store: SessionStore | None                # Persistence (§6), None = in-memory
```

`RunDeps` is constructed by the entrypoint / composition root and threaded through the session factory into the session. The inner core defines the shape; the outer layers decide what to put in it.

---

## 8. Error Handling

Errors are **not modelled as events**. The loop lets exceptions propagate naturally:

| Error source | Behavior |
|---|---|
| LLM call fails | Exception propagates through the generator |
| Tool execution fails | Caught internally, yielded as `ToolCallResultInfo(success=False)` |
| Context transform fails | Exception propagates (transforms are critical-path) |
| Hook fails | Exception propagates (hooks are part of the execution contract) |
| Store write fails | Yielded as `Notification(severity=ERROR)`, execution continues |

**Invariant**: If the loop exits abnormally, it must **not** yield `AgentDone`. The absence of `AgentDone` signals incomplete turn.

---

## 9. Cancellation

`cancellation_event` is an `asyncio.Event`. Check it:

- Top of the outer loop (before LLM call)
- Top of the inner loop (before `asyncio.wait`)
- After context transforms, before the LLM call
- After receiving an event, before yielding

On cancellation: `return` immediately, no `AgentDone`. Clean up tasks in `finally`.

---

## 10. Backpressure

The async generator protocol provides natural backpressure: the loop suspends at each `yield` until the consumer calls `asend()` or `__anext__()`. Backend implementations must preserve this — no background buffering of LLM events.

---

## 11. Summary: The Inner Core Surface

| Abstraction | Role | Module |
|---|---|---|
| `AgentEvent` union | Vocabulary of the event stream | `core/types.py` |
| `AgentEventStream` | Bidirectional async generator type | `core/types.py` |
| `AgentSessionProtocol` | Session contract (run + history) | `core/types.py` |
| `SessionFactoryProtocol` | Backend-agnostic session creation | `core/types.py` |
| `InteractionRequest` / `InteractionResponse` | Extensible bidirectional handshake | `core/types.py` |
| `ContextTransform` | Pre-call context pipeline | `core/context.py` |
| `ToolHook` / `ToolDecision` | Tool lifecycle observation and interception | `core/hooks.py` |
| `SessionStore` / `SessionEntry` | Opt-in persistence with branching | `core/persistence.py` |
| `RunDeps` | Dependency injection container | `core/deps.py` |
| `Notification` | Unidirectional status events | `core/types.py` |

Everything else is outer-layer concern.
