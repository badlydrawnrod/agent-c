# Agent C — Agentic Loop Specification

> [!IMPORTANT]
> This document is implementation-oriented guidance. The normative inner-core contract is defined in `docs/inner-core-spec.md`.
> If this document conflicts with `docs/inner-core-spec.md`, the inner-core spec takes precedence.

A backend-agnostic specification for implementing Agent C's core agentic loop. Given this spec, an LLM (or developer) should be able to implement a new backend (e.g., OpenAI Responses API, Google Gemini, AWS Bedrock) that integrates into the existing architecture.

---

## 1. Overview

Agent C's agentic loop is a **bidirectional async generator** that:

1. **Streams events** downstream (text chunks, tool calls, tool results, interaction requests, completion signals)
2. **Receives responses** upstream via `asend()` (interaction responses)
3. Runs inside a **session** that maintains conversation history across turns
4. Is created by a **session factory** that the UI knows only through a protocol

The loop is **the only contract** between a backend and the rest of the system. Everything above it (middleware, adapters, UI) is backend-agnostic and reusable.

---

## 2. Event Types

All events are plain dataclasses. A backend must yield exactly these types — no backend-specific types may leak upstream.

### 2.1 [AgentChunk](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#54-60)
Streamed content from the LLM.

```python
@dataclass
class AgentChunk:
    content: str
    is_thought: bool = False  # True for thinking/reasoning tokens
```

**Yield** as soon as content is available — the middleware handles batching.

### 2.2 [ToolCallInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#62-69)
The LLM is invoking a tool. [args](file:///c:/Projects/python/agent-c/src/agentc/core/tool_parsing.py#7-24) is a read-only mapping — consumers use it for display/logging only.

```python
@dataclass
class ToolCallInfo:
    tool_name: str
    args: Mapping[str, Any]   # Immutable view (see Appendix A)
    tool_call_id: str
```

### 2.3 [ToolCallResultInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#122-128)
A tool finished executing.

```python
@dataclass
class ToolCallResultInfo:
    tool_call_id: str     # Matches a prior ToolCallInfo
    result: ToolResult

@dataclass
class ToolResult:
    success: bool
    content: str
    error: str | None = None
```

### 2.4 `Notification`
A unidirectional status message from the backend. Not LLM content, not a tool result — informational only.

```python
class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

@dataclass
class Notification:
    message: str
    severity: Severity = Severity.INFO
```

**When to yield**: Progress updates ("Searching 1,432 files..."), transient errors ("Rate limited, retrying in 5s..."), backend status ("Compacting conversation history..."), or any other information the user should see but that isn't part of the LLM's response.

> [!NOTE]
> `Notification` is unidirectional — no response is expected. It passes straight through middleware and is displayed by the adapter.

### 2.5 [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135)
Pure completion signal. The session retains history internally — consumers never need to carry or relay it.

```python
@dataclass
class AgentDone:
    """Turn complete. The session owns the history."""
    pass
```

> [!NOTE]
> If history inspection is needed (e.g., serialization, export), the session exposes it via a [history](file:///c:/Projects/python/agent-c/src/agentc/core/backends/pydantic_ai/loop.py#85-89) property. This keeps [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) free of opaque `Any` types and prevents history from leaking into the event stream contract.

---

## 3. The Interaction Protocol

All bidirectional flows (approval, user input, and any future interaction types) share a common base.

### 3.1 Base Types

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

### 3.2 Approval Interaction

```python
@dataclass
class ApprovalRequest(InteractionRequest):
    tool_calls: list[ToolCallInfo]  # Tools pending approval

@dataclass
class ApprovalResponse(InteractionResponse):
    approved: bool
    reason: str | None = None  # Denial reason shown to LLM
```

### 3.3 User Input Interaction

```python
@dataclass
class UserInputRequest(InteractionRequest):
    question: str
    options: list[UserInputOption]
    allow_freeform: bool = False
    placeholder: str | None = None

@dataclass
class UserInputOption:
    label: str
    description: str | None = None

@dataclass
class UserInputResponse(InteractionResponse):
    response: str
```

### 3.4 The Event Union and Stream Type

```python
type AgentEvent = (
    AgentChunk | ToolCallInfo | ToolCallResultInfo
    | Notification
    | InteractionRequest  # ← covers all current and future subtypes
    | AgentDone
)

type AgentEventStream = AsyncGenerator[
    AgentEvent,
    InteractionResponse | None  # ← permanently stable
]
```

> [!IMPORTANT]
> Adding a new interaction type (e.g., file picker, confirmation dialog) requires only:
> 1. Subclass `InteractionRequest` and `InteractionResponse`
> 2. Register a handler in the adapter
>
> The event union, stream type, and middleware remain unchanged.

---

## 4. The Session Protocol

### 4.1 [AgentSessionProtocol](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#151-161)

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
- [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161) returns a bidirectional async generator
- First call is always `asend(None)` or `__anext__()`
- Yields [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) as its final event, then terminates
- On cancellation: `return` immediately, no [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135)
- Maintains conversation history internally across calls
- [history](file:///c:/Projects/python/agent-c/src/agentc/core/backends/pydantic_ai/loop.py#85-89) property: available for inspection/serialization but never required by consumers during normal operation
- **Single-active-run**: only one [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161) may be active at a time per session (see [§11 Concurrency Guard](#11-concurrency-guard))

### 4.2 [SessionFactoryProtocol](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#163-184)

```python
class SessionFactoryProtocol(Protocol):
    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol: ...

@dataclass
class SessionConfig:
    model_name: str | None = None
    clear_history: bool = False
    skill_dirs: list[Path] | None = None
    deps: RunDeps | None = None
```

Called by the UI when switching models or clearing history.

---

## 5. Interaction State Machine

All interactions follow the same yield/asend cycle. The loop-level behavior after receiving a response differs by interaction type.

```
             ┌──────────────────────────────────┐
             │         Streaming Phase           │
             │  yield AgentChunk/ToolCallInfo/   │
             │        ToolCallResultInfo         │
             └──────────┬───────────────────────┘
                        │
            ┌───────────▼───────────┐
            │  InteractionRequest?  │──── no ───▶ continue streaming
            └───────────┬───────────┘
                        │ yes
                        ▼
              yield InteractionRequest
                        │
                        ▼
              asend(InteractionResponse)
                        │
        ┌───────────────┼───────────────┐
        │ None          │               │
        ▼               ▼               ▼
     return      ApprovalResponse   UserInputResponse
   (abort)       → restart loop     → resolve future
                 with results       → tool unblocks
```

### 5.1 Approval Flow (loop-initiated)

1. LLM produces deferred tool calls → loop bundles into [ApprovalRequest](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#71-76), `yield`s it
2. Consumer `asend`s [ApprovalResponse](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#78-84)
3. If `None` received instead → `return` (consumer disconnected)
4. **Approved**: execute deferred tools, feed results to LLM, restart outer loop
5. **Denied**: feed denial reason to LLM as a tool error, restart outer loop
6. Update history before restarting

### 5.2 User Input Flow (tool-initiated, concurrent)

1. A tool calls `deps.user_input_handler.request_user_input(request)` — this blocks the tool
2. The broker enqueues the request on an `asyncio.Queue`
3. The loop's concurrent select picks it up and `yield`s the [UserInputRequest](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#94-103)
4. Consumer `asend`s [UserInputResponse](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#105-111)
5. If `None` received → resolve future with empty response, `return`
6. Broker resolves the tool's `Future`, unblocking it

### 5.3 Adding a New Interaction Type

To add a new interaction (e.g., `FilePickerRequest`/`FilePickerResponse`):

1. **Define types**: Subclass `InteractionRequest` and `InteractionResponse`
2. **Choose source**: Loop-initiated (like approval) or tool-initiated (like user input)
3. **Backend loop**: Yield the request at the appropriate point, handle the response
4. **Adapter**: Register a handler mapping the new request type to UI behavior
5. **No changes needed** in: event union, stream type, [DebouncingMiddleware](file:///c:/Projects/python/agent-c/src/agentc/middleware/debouncing.py#44-95), `AgentEventStream`

---

## 6. Approval Trigger Strategies

Which tools require approval is a **policy** decision (a property of the tool, not the backend). How to defer execution is a **mechanism** that depends on what the backend's framework supports.

### 6.1 Policy: Tool Approval Metadata

Tools declare whether they require approval. The backend must honour this flag regardless of mechanism:

```python
class ToolMetadata:
    name: str
    requires_approval: bool = False
```

### 6.2 Mechanism: Three Strategies

| Strategy | When to use | Example |
|---|---|---|
| **Framework-native deferral** | Framework supports marking tools as needing approval and produces deferred results | Pydantic AI [Tool(func, requires_approval=True)](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#113-120) → `DeferredToolRequests` |
| **Bridge to native permissions** | Framework has its own permission system; wire it into the `InteractionRequest` stream via the broker | Copilot SDK [on_permission_request](file:///c:/Projects/python/agent-c/src/agentc/entrypoints/run_textual_gh.py#29-34) → yield [ApprovalRequest](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#71-76) via broker |
| **Manual interception** | Framework has no approval support; backend intercepts before execution | Before calling a flagged tool, yield [ApprovalRequest](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#71-76), await [ApprovalResponse](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#78-84), then execute or return denial |

> [!TIP]
> **Framework-native deferral** is simplest when available — let the framework collect deferred calls and map them to [ApprovalRequest](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#71-76). **Manual interception** is the universal fallback and works with any API (OpenAI, Gemini, etc.).

### 6.3 Manual Interception Pattern

For backends where the framework has no approval concept:

```python
# After LLM produces tool calls:
for tool_call in tool_calls:
    if tool_requires_approval(tool_call):
        deferred.append(tool_call)
    else:
        result = await execute_tool(tool_call)
        yield ToolCallResultInfo(tool_call.tool_call_id, result)

if deferred:
    request = ApprovalRequest(tool_calls=deferred)
    response = yield request
    if response is None: return
    if response.approved:
        for tool_call in deferred:
            result = await execute_tool(tool_call)
            yield ToolCallResultInfo(tool_call.tool_call_id, result)
    else:
        for tool_call in deferred:
            yield ToolCallResultInfo(tool_call.tool_call_id,
                ToolResult(success=False, content="", error=response.reason))
    # Feed results into LLM, restart outer loop
```

---

## 7. The [UserInputHandler](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#186-199) Protocol

Tools request user input through this protocol, which the session's broker implements:

```python
class UserInputHandler(Protocol):
    async def request_user_input(
        self, request: UserInputRequest
    ) -> UserInputResponse: ...
```

The broker implementation bridges tool calls to the event stream:

```python
class UserInputBroker:
    """Bridges tool-initiated input requests to the event stream."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[
            tuple[UserInputRequest, asyncio.Future[UserInputResponse]]
        ] = asyncio.Queue()

    async def request_user_input(
        self, request: UserInputRequest
    ) -> UserInputResponse:
        """Called by tools. Blocks until the consumer provides a response."""
        future: asyncio.Future[UserInputResponse] = asyncio.get_event_loop().create_future()
        await self._queue.put((request, future))
        return await future

    async def next_request(
        self,
    ) -> tuple[UserInputRequest, asyncio.Future[UserInputResponse]]:
        """Called by the loop's select. Returns the next pending request."""
        return await self._queue.get()
```

The session wires it up in [__init__](file:///c:/Projects/python/agent-c/src/agentc/core/backends/github_copilot/loop.py#35-39):

```python
self._broker = UserInputBroker()
deps.user_input_handler = self._broker
```

---

## 8. Concurrent Select Loop

The inner event loop races LLM events against broker requests using `asyncio.wait`:

```python
event_task = asyncio.create_task(next_llm_event())
request_task = asyncio.create_task(broker.next_request())

done, _ = await asyncio.wait(
    {event_task, request_task},
    return_when=asyncio.FIRST_COMPLETED,
)

if request_task in done:
    interaction_request, future = request_task.result()
    response = yield interaction_request
    if response is None:
        future.set_result(default_response(interaction_request))
        return
    future.set_result(response)
    request_task = None

if event_task in done:
    event = event_task.result()
    # ... map and yield ...
    event_task = None
```

**Invariants**:
- Only one interaction is in-flight at a time
- Pending tasks must be cancelled in a `finally` block
- If `asend` returns `None`, terminate gracefully

---

## 9. Implementation Pattern

Complete pseudocode for a backend's [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161) method:

```python
async def run(self, prompt, cancellation_event=None) -> AgentEventStream:
    approval_results = None
    current_prompt = prompt

    while True:  # Outer loop: one iteration per approval round-trip
        if self._is_cancelled(cancellation_event):
            return

        stream = self._call_llm(current_prompt, self._history, approval_results)
        event_task = None
        request_task = None

        try:
            while True:  # Inner loop: process events + broker requests
                if self._is_cancelled(cancellation_event):
                    return

                if event_task is None:
                    event_task = asyncio.create_task(stream.__anext__())
                if request_task is None:
                    request_task = asyncio.create_task(self._broker.next_request())

                done, _ = await asyncio.wait(
                    {event_task, request_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Handle broker interaction requests
                if request_task in done:
                    request, future = request_task.result()
                    request_task = None
                    response = yield request
                    if response is None:
                        future.set_result(default_response(request))
                        return
                    future.set_result(response)
                    continue

                # Handle LLM events
                if event_task in done:
                    try:
                        event = event_task.result()
                    except StopAsyncIteration:
                        break
                    event_task = None

                    if chunk := self._map_chunk(event):
                        yield chunk; continue
                    if tool_call := self._map_tool_call(event):
                        yield tool_call; continue
                    if tool_result := self._map_tool_result(event):
                        yield tool_result; continue

                    if is_approval_needed(event):
                        request = self._build_approval_request(event)
                        response = yield request
                        if response is None: return
                        approval_results = self._build_results(event, response)
                        self._update_history(event)
                        current_prompt = None
                        break  # → restart outer loop

                    if is_final(event):
                        self._update_history(event)
                        yield AgentDone()
                        return
        finally:
            if event_task: event_task.cancel()
            if request_task: request_task.cancel()
```

---

## 10. Error Handling

### 10.1 Error Propagation Contract

Errors are **not modelled as events**. The loop lets exceptions propagate naturally through the async generator. Consumers catch them:

```
Backend error → exception propagates through generator
    → middleware sees it in __anext__() / asend()
    → adapter catches with `except Exception`
    → adapter posts error to UI
```

### 10.2 Backend Responsibilities

| Error source | Backend should | Consumer sees |
|---|---|---|
| **LLM call fails** (network, rate limit, auth) | Let exception propagate | `Exception` from `asend()` / `__anext__()` |
| **Tool execution fails** | Catch internally, yield [ToolCallResultInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#122-128) with [ToolResult(success=False, error=...)](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#113-120) | Normal [ToolCallResultInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#122-128) event |
| **Broker future never resolved** | `finally` block cancels pending tasks; future raises `CancelledError` | Generator terminates |

### 10.3 Invariant

> [!CAUTION]
> If the loop exits abnormally (exception, cancellation), it must **not** yield [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135). The absence of [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) signals to consumers that the turn did not complete normally.

---

## 11. Concurrency Guard

Only one [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161) may be active per session at a time. A second call while the first is still yielding is **undefined behavior**.

The recommended guard:

```python
def run(self, prompt, cancellation_event=None) -> AgentEventStream:
    if self._running:
        raise RuntimeError("Session already has an active run()")
    self._running = True
    try:
        # ... generator body ...
    finally:
        self._running = False
```

> [!NOTE]
> The UI enforces this externally (it cancels the previous run before starting a new one), but the session should defend against misuse.

---

## 12. Backpressure

The async generator protocol **naturally provides backpressure**: the loop suspends at each `yield` until the consumer calls `asend()` or `__anext__()`. This means:

- The LLM will not race ahead of the UI
- No unbounded event queue is needed between loop and consumer
- The loop only produces the next event when the consumer is ready

Backend implementations **must preserve this property**. Specifically:
- **Do not** buffer LLM events in an internal queue and drain them — yield them one at a time
- **Do not** spawn a background task that collects events while the generator is suspended
- The concurrent select loop (§8) is acceptable because it races exactly two tasks and suspends immediately on `yield`

---

## 13. Thread Safety for Callback-Based Backends

Some SDKs deliver events from a non-asyncio thread (e.g., gRPC callbacks, WebSocket handlers). These must be bridged safely.

### Pattern: `call_soon_threadsafe` + `asyncio.Queue`

```python
class CallbackBridge:
    """Bridges thread-based SDK callbacks to an asyncio event stream."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[SdkEvent] = asyncio.Queue()

    def on_sdk_event(self, event: SdkEvent) -> None:
        """Called from SDK thread. Must not use await."""
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def next_event(self) -> SdkEvent:
        """Called from asyncio loop. Blocks until an event arrives."""
        return await self._queue.get()
```

Register `on_sdk_event` as the SDK's callback. The loop's inner `asyncio.wait` races `bridge.next_event()` (instead of `stream.__anext__()`) against the broker.

> [!WARNING]
> Never `await` inside a callback invoked from a non-asyncio thread. Always use `call_soon_threadsafe` to enqueue work onto the event loop.

---

## 14. Cancellation

`cancellation_event` is an `asyncio.Event`. Check it:
- Top of outer loop (before LLM call)
- Top of inner loop (before `asyncio.wait`)
- After receiving an event, before yielding

On cancellation: `return` immediately, no [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135). Clean up tasks in `finally`.

---

## 15. History & RunDeps

### History

The session owns its history internally as a backend-specific data structure. It is:
- Updated on approval round-trips and turn completion
- Preserved across successive [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161) calls (multi-turn conversation)
- Accessible via the session's [history](file:///c:/Projects/python/agent-c/src/agentc/core/backends/pydantic_ai/loop.py#85-89) property for inspection or serialization
- **Never carried in events** — [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) is a pure signal

### RunDeps

Runtime dependencies passed to the session and injected into tools:

```python
@dataclass
class RunDeps:
    root_dirs: list[Path]                        # Filesystem security boundary
    skill_dirs: list[Path]                       # Skill discovery (subset of root_dirs)
    user_input_handler: UserInputHandler | None  # Broker for mid-turn interactions
```

The session must set `deps.user_input_handler` to its broker in [__init__](file:///c:/Projects/python/agent-c/src/agentc/core/backends/github_copilot/loop.py#35-39).

---

## 16. Command System

User commands (e.g., `/model`, `/clear`) are parsed into a **typed union** — no dict access.

```python
@dataclass
class ClearCommand:
    """Clear conversation history."""
    pass

@dataclass
class ExitCommand:
    """Exit the application."""
    pass

@dataclass
class HelpCommand:
    """Show available commands."""
    pass

@dataclass
class ModelSwitchCommand:
    """Switch to a different model preset."""
    model: str

@dataclass
class UnknownCommand:
    """Unrecognised slash command."""
    input: str
    error: str

@dataclass
class NormalInput:
    """Regular user message (not a command)."""
    pass

type CommandResult = (
    ClearCommand | ExitCommand | HelpCommand
    | ModelSwitchCommand | UnknownCommand | NormalInput
)
```

Consumers use structural `match`:

```python
match command_parser.parse(user_input):
    case ModelSwitchCommand(model=name):
        effect = switch_model(name)
    case ClearCommand():
        effect = clear_session()
    case ExitCommand():
        app.exit()
    # ...
```

---

## 17. How Consumers Use the Loop

### Middleware (DebouncingMiddleware)

```python
if isinstance(event, AgentChunk):
    # buffer
elif isinstance(event, InteractionRequest):
    flush_all(); response = yield event  # generic — handles all subtypes
elif isinstance(event, AgentDone):
    flush_all(); yield event
else:
    yield event  # ToolCallInfo, ToolCallResultInfo, Notification passthrough
```

### Adapter (dispatch pattern)

```python
interaction_handlers = {
    ApprovalRequest: self._handle_approval,
    UserInputRequest: self._handle_user_input,
    # Future: FilePickerRequest: self._handle_file_picker,
}

if isinstance(event, InteractionRequest):
    handler = interaction_handlers[type(event)]
    response = await handler(event)
    # asend response back upstream
```

---

## 18. New Backend Checklist

### `core/backends/<name>/loop.py` — implements [AgentSessionProtocol](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#151-161)

- [ ] [__init__](file:///c:/Projects/python/agent-c/src/agentc/core/backends/github_copilot/loop.py#35-39): accept backend client, optional history, [RunDeps](file:///c:/Projects/python/agent-c/src/agentc/core/deps.py#12-42)
- [ ] [__init__](file:///c:/Projects/python/agent-c/src/agentc/core/backends/github_copilot/loop.py#35-39): create [UserInputBroker](file:///c:/Projects/python/agent-c/src/agentc/core/backends/pydantic_ai/loop.py#48-68), set `deps.user_input_handler`
- [ ] [__init__](file:///c:/Projects/python/agent-c/src/agentc/core/backends/github_copilot/loop.py#35-39): set `self._running = False` (concurrency guard)
- [ ] [history](file:///c:/Projects/python/agent-c/src/agentc/core/backends/pydantic_ai/loop.py#85-89) property: expose backend-specific history
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): enforce concurrency guard
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): return `AgentEventStream`
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): map backend events → [AgentChunk](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#54-60), [ToolCallInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#62-69), [ToolCallResultInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#122-128)
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): implement approval (choose strategy from §6)
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): implement concurrent select loop (LLM events + broker)
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): yield [AgentDone()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) as final event (no args)
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): check `cancellation_event`, clean up tasks in `finally`
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): let LLM/network errors propagate (§10)
- [ ] [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161): catch tool errors, yield [ToolCallResultInfo(success=False)](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#122-128) (§10)
- [ ] If callback-based SDK: use thread-safe bridge (§13)
- [ ] History maintained across [run()](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#154-161) calls

### `core/backends/<name>/session_factory.py` — implements [SessionFactoryProtocol](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#163-184)

- [ ] [create_session(config)](file:///c:/Projects/python/agent-c/src/agentc/core/backends/pydantic_ai/session_factory.py#19-47): build client/model from `config.model_name`
- [ ] Handle `config.clear_history`
- [ ] Pass `config.deps` to session
- [ ] Raise on invalid config (missing API keys, unknown models)

### Entrypoint

- [ ] Wire session factory + initial session → [TextualAgentApp](file:///c:/Projects/python/agent-c/src/agentc/ui/textual_app.py#44-377)
- [ ] Register as console script in [pyproject.toml](file:///c:/Projects/python/agent-c/pyproject.toml)

---

## Appendix A: [parse_tool_args](file:///c:/Projects/python/agent-c/src/agentc/core/tool_parsing.py#7-24)

Normalize tool arguments to `Mapping[str, Any]`:

```python
def parse_tool_args(args: Any) -> Mapping[str, Any]:
    if isinstance(args, dict): return args
    if args is None: return {}
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict): return parsed
        except json.JSONDecodeError: pass
        return {"value": args}
    return {"value": str(args)}
```

## Appendix B: Event Ordering

```
(AgentChunk | ToolCallInfo | ToolCallResultInfo | Notification)*  ── streaming
(InteractionRequest ── InteractionResponse)*                      ── zero or more interactions
AgentDone                                                         ── exactly once, terminal
```

- [ToolCallInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#62-69) precedes its matching [ToolCallResultInfo](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#122-128)
- `Notification` can appear at **any** point during streaming (unidirectional, no response)
- `InteractionRequest` from the **loop** (approval) appears after LLM completes a response
- `InteractionRequest` from the **broker** (user input) can appear at any point during streaming
- [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) is always last (except on cancellation, where it's omitted)
- On error: no [AgentDone](file:///c:/Projects/python/agent-c/src/agentc/core/types.py#130-135) is yielded — the exception propagates instead
