# Agent C — Layered Streaming Pipeline (Bidirectional Async Generator)

UI initiates requests at the top; external systems at the bottom produce events that flow UP through layers; approval decisions flow DOWN via asend().

```mermaid
graph TD
    %% UI (Top - Initiator and Consumer)
    UI["UI Layer - INITIATES request CONSUMES events
TextualAgentApp and Console entry point
Renders stream and handles approval prompts"]
    
    %% Adapter
    Adapter["Inbound Adapter
TextualAgentAdapter and ConsoleAgentAdapter
CONSUMES AgentEvent stream PRODUCES UI messages
Loop await events asend response"]
    
    %% Core Port
    Core["Core Port AgentSessionProtocol
session run returns AgentEventStream
Yields AgentChunk ToolCallInfo ApprovalRequest AgentDone
Consumes ApprovalResponse via asend"]
    
    %% Backend Implementation
    Backend["Backend Session
AgentSession and GhAgentSession
Wraps backend events into AgentEvent stream
Handles approval requests via asend"]
    
    %% External Event Sources (Bottom - Producers)
    External["External Event Sources - PRODUCE events
LLM providers and tool runtime
Generate streaming deltas and completion signals"]
    
    %% Prompt Flow (Request Initiation - flows DOWN)
    UI ==>|"[1] prompt + cancellation_event"| Adapter
    Adapter ==>|"[2] session.run prompt"| Core
    Core ==>|"[3] prompt triggers backend"| Backend
    Backend ==>|"[4] sends to external"| External
    
    %% Event Flow UP (Response - flows UP from external to UI)
    External -->|"[5] raw events"| Backend
    Backend -->|"[6] AgentEvent stream"| Core
    Core -->|"[7] AgentEvent stream"| Adapter
    Adapter -->|"[8] UI messages"| UI
    
    %% Approval Flow DOWN
    UI -.->|"ApprovalResponse via asend"| Adapter
    Adapter -.->|"ApprovalResponse via asend"| Core
    Core -.->|"ApprovalResponse via asend"| Backend
    
    %% Styling
    classDef ui fill:#eff6ff,stroke:#3b82f6,stroke-width:2px
    classDef adapter fill:#fefce8,stroke:#eab308,stroke-width:2px
    classDef core fill:#eef2ff,stroke:#6366f1,stroke-width:3px
    classDef backend fill:#fff7ed,stroke:#f97316,stroke-width:2px
    classDef external fill:#fff,stroke:#94a3b8,stroke-width:2px
    
    class UI ui
    class Adapter adapter
    class Core core
    class Backend backend
    class External external
```

## Key Pattern: "Run a Request" = "Stream Events"

**Request initiation flows DOWN (UI → External)**:
1. User enters prompt in UI (top layer)
2. UI creates adapter with prompt and `cancellation_event`
3. Adapter calls `session.run(prompt, cancellation_event)`
4. Core port invokes backend session
5. Backend sends prompt to external LLM/tool systems (bottom layer)

**Events flow UP in response (External → UI)**:
6. External systems produce streaming events (bottom layer)
7. Backend wraps them as `AgentEvent` stream
8. Core port enforces protocol contract
9. Adapter translates to UI messages
10. UI renders to screen (top layer)

**Approval responses flow DOWN** via `asend()`:
- When backend needs approval (e.g., tool execution), it yields `ApprovalRequest` that flows UP
- UI prompts user for approval decision
- Decision flows DOWN through each layer via `asend()`
- Backend receives `ApprovalResponse` and continues execution

**Cancellation**:
- UI's `cancellation_event` can interrupt the stream at any layer

Each layer repeats the same async generator pattern:
```python
async def process(events: AgentEventStream) -> AgentEventStream:
    response = None
    while True:
        event = await events.asend(response)
        response = None
        # Transform event, possibly obtain approval
        yield transformed_event
```
