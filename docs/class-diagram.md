# Agent C — Class Diagram (UML)

Protocols owned by Core, implemented by Backends, used by Adapters

```mermaid
classDiagram
    %% Core Protocols (Interface Definitions)
    class AgentSessionProtocol {
        <<protocol>>
        +run(prompt, cancellation_event) AgentEventStream
        +history list[ModelMessage]
        +reset_history()
    }
    
    class AgentEventStream {
        <<type>>
        AsyncGenerator[AgentEvent, ApprovalResponse | None]
    }
    
    class AgentEvent {
        <<union>>
        AgentChunk | ToolCallInfo | ToolCallResultInfo | ApprovalRequest | AgentDone
    }
    
    class SessionFactoryProtocol {
        <<protocol>>
        +create_session(config) AgentSessionProtocol
    }
    
    %% Backend Implementations
    class AgentSession {
        -_agent Agent
        -_history list[ModelMessage]
        +run(prompt, event) AgentEventStream
        +reset_history()
    }
    
    class GhAgentSession {
        -_session CopilotSession
        -_history list[Message]
        +run(prompt, event) AgentEventStream
        +reset_history()
    }
    
    class PydanticAISessionFactory {
        +create_session(config) AgentSessionProtocol
    }
    
    class GhCopilotSessionFactory {
        +create_session(config) AgentSessionProtocol
    }
    
    %% Adapter Layer
    class TextualAgentAdapter {
        -_session AgentSessionProtocol
        -_prompt str
        +run() AsyncIterator[Message]
        -_handle_approval()
    }
    
    class ConsoleAgentAdapter {
        -_session AgentSessionProtocol
        -_prompt str
        +run()
    }
    
    %% UI Layer
    class TextualAgentApp {
        -_factory SessionFactoryProtocol
        +background_task(prompt)
    }
    
    %% Relationships - Realization (implements)
    AgentSession ..|> AgentSessionProtocol : realizes
    GhAgentSession ..|> AgentSessionProtocol : realizes
    PydanticAISessionFactory ..|> SessionFactoryProtocol : realizes
    GhCopilotSessionFactory ..|> SessionFactoryProtocol : realizes
    
    %% Relationships - Dependencies (uses)
    AgentSessionProtocol ..> AgentEventStream : returns
    AgentEventStream ..> AgentEvent : yields
    TextualAgentAdapter ..> AgentSessionProtocol : uses
    ConsoleAgentAdapter ..> AgentSessionProtocol : uses
    TextualAgentApp ..> SessionFactoryProtocol : uses
    TextualAgentApp ..> TextualAgentAdapter : creates
    
    %% Styling
    style AgentSessionProtocol fill:#eef2ff,stroke:#6366f1,stroke-width:3px
    style AgentEventStream fill:#eef2ff,stroke:#6366f1,stroke-width:2px
    style AgentEvent fill:#eef2ff,stroke:#6366f1,stroke-width:2px
    style SessionFactoryProtocol fill:#eef2ff,stroke:#6366f1,stroke-width:2px
    
    style AgentSession fill:#fff7ed,stroke:#f97316,stroke-width:2px
    style GhAgentSession fill:#fff7ed,stroke:#f97316,stroke-width:2px
    style PydanticAISessionFactory fill:#fff7ed,stroke:#f97316,stroke-width:2px
    style GhCopilotSessionFactory fill:#fff7ed,stroke:#f97316,stroke-width:2px
    
    style TextualAgentAdapter fill:#fefce8,stroke:#eab308,stroke-width:2px
    style ConsoleAgentAdapter fill:#fefce8,stroke:#eab308,stroke-width:2px
    
    style TextualAgentApp fill:#eff6ff,stroke:#3b82f6,stroke-width:2px
```

## Key Relationships

**Realization** (dotted line with hollow arrow `...|>`):
- Backend classes IMPLEMENT the protocols defined by Core
- `AgentSession` and `GhAgentSession` realize `AgentSessionProtocol`
- Factory classes realize `SessionFactoryProtocol`

**Dependency** (dotted line with arrow `..>`):
- Adapters and UI DEPEND ON protocols (use them via interfaces)
- `TextualAgentAdapter` uses `AgentSessionProtocol` (doesn't care which implementation)
- `TextualAgentApp` uses `SessionFactoryProtocol` to create sessions

**Core Principle**:
- Core layer OWNS protocols (`AgentSessionProtocol`, `AgentEventStream`, `AgentEvent`)
- Backends REALIZE protocols (provide concrete implementations)
- Adapters/UI DEPEND on protocols (consume via abstract interfaces)
- Dependencies point toward abstractions, not implementations
