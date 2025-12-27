# AgentC Next Generation

This directory contains the next generation of AgentC: a decoupled architecture for a tool-augmented agent with multiple UI implementations.

## Overview

AgentC Next separates the core agentic loop from the UI layer using an event-driven approach. It leverages `pydantic_ai` for the agent implementation but wraps it in an agnostic event stream that can be consumed by different adapters (Textual, Console, etc.).

### Quick Architectural Summary

**One Word:** Pipelined

**One Sentence:** `agentc_next` is an event-driven pipeline architecture where a core agentic loop yields framework-agnostic events that flow through optional middleware and are adapted into framework-specific UI messages.

**Full Description:** `agentc_next` is a layered, event-driven architecture that decouples the core agentic logic from UI implementations through an async generator-based event pipeline. At its foundation, an `AgentSession` wraps a `pydantic_ai` agent and yields framework-agnostic events (`AgentChunk`, `ToolCallInfo`, `ApprovalRequest`, `AgentDone`) that represent the agent's thinking, outputs, and decisions. These events flow through an optional middleware layer (like `DebouncingMiddleware`) that can buffer or transform the stream while preserving the async send/receive protocol for approval handshakes. Finally, framework-specific adapters (like `TextualAgentAdapter`) consume this event stream and translate core events into framework-specific messages (Textual `Message` subclasses) that the UI layer consumes. This design completely decouples agent logic from presentation, enabling multiple UI implementations while keeping the core stateless and reusable.

## Architecture Diagrams

### Dependency Graph

The project is structured to minimize tight coupling, with dependencies flowing towards the core logic.

```mermaid
graph TD
    UI[ui] --> Adapters[adapters]
    UI --> Core[core]
    Adapters --> Middleware[middleware]
    Adapters --> Core
    Middleware --> Core
    Core --> PydanticAI[pydantic_ai]
```

### Class Diagram

Key classes and their relationships:

```mermaid
classDiagram
    class AgentSessionProtocol {
        <<interface>>
        +run(prompt, deps, cancellation_event) AsyncGenerator
    }

    class AgentSession {
        -agent: NextAgent
        -history: list
        +run(prompt, deps, cancellation_event)
        -_map_event_to_chunk(event)
    }

    class TextualAgentAdapter {
        -app: App
        -session: AgentSessionProtocol
        +run()
        -_handle_approval_request(request)
    }

    class DebouncingMiddleware {
        +process(events) AsyncGenerator
    }

    class AgentEvent {
        <<union>>
        AgentChunk
        ToolCallInfo
        ApprovalRequest
        AgentDone
    }

    AgentSession ..|> AgentSessionProtocol
    TextualAgentAdapter --> AgentSessionProtocol
    TextualAgentAdapter --> DebouncingMiddleware
    AgentSession ..> AgentEvent : yields
```

### Typical Conversation Sequence

This diagram shows the flow of a user prompt through the layers, including a tool approval cycle.

```mermaid
sequenceDiagram
    participant User
    participant App as TextualApp
    participant Adapter as TextualAgentAdapter
    participant Mid as DebouncingMiddleware
    participant Session as AgentSession
    participant AI as PydanticAI

    User->>App: Submits Prompt
    App->>Adapter: await run()
    Adapter->>Session: run(prompt)
    Session->>AI: run_stream_events()
    
    loop Streaming Events
        AI->>Session: PartDeltaEvent
        Session->>Mid: yield AgentChunk
        Mid-->>Mid: Buffering...
        Note over Mid: Threshold Reached
        Mid->>Adapter: yield AgentChunk (Buffered)
        Adapter->>App: post_message(AgentText/Thinking)
        App->>User: Update UI
    end

    AI->>Session: AgentRunResultEvent (Approval Required)
    Session->>Mid: yield ApprovalRequest
    Mid->>Adapter: yield ApprovalRequest
    Adapter->>App: post_message(AgentApprovalRequest)
    App->>User: Show Dialog
    User->>App: Approve Tool Call
    App->>Adapter: resolve(approved=True)
    Adapter->>Mid: send ApprovalResponse
    Mid->>Session: send ApprovalResponse
    Session->>AI: Resume with results

    AI->>Session: AgentRunResultEvent (Final)
    Session->>Adapter: yield AgentDone
    Adapter->>App: post_message(AgentDone)
    App->>User: Show Final Response
```

## Key Components

- **`core/`**: Contains the `AgentSession` and the agnostic event types. It encapsulates the interaction with `pydantic_ai`.
- **`adapters/`**: Bridges the core event stream to specific UI frameworks. The `TextualAgentAdapter` converts `AgentEvent` objects into Textual `Message` objects.
- **`middleware/`**: Intermediaries that can transform the event stream. The `DebouncingMiddleware` aggregates small text deltas to prevent UI flickering.
- **`ui/`**: Concrete UI implementations. `run_textual.py` launches the full interactive terminal application.

## Getting Started

You can run the different UI variants using the following commands:

```powershell
# Run the Textual UI
python -m agentc_next.ui.run_textual

# Run the Console UI
python -m agentc_next.ui.run_console
```
