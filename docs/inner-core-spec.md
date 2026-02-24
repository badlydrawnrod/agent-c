# Agent C Inner Core Specification (Normative)

Status: Active  
Owner: Core Architecture  
Last updated: 2026-02-24

## 1. Purpose

This document defines the **minimum viable agentic loop** for Agent C such that the core can be implemented once and extended later without modifying original core contracts.

This specification is **normative**. Any backend, middleware, adapter, or UI integration claiming compatibility with Agent C inner core MUST satisfy the requirements in this document.

## 2. OCP Contract

The inner core MUST remain:

- **Closed for modification**: Existing core protocols and invariants are immutable once released.
- **Open for extension**: New behavior is added through additive implementations, registrations, or subclassing of existing base abstractions.

### 2.1 Change Policy

The following changes are allowed without breaking OCP:

- Add a new event subtype already covered by an existing base union member.
- Add a new implementation of an existing Protocol.
- Add a new middleware, adapter, or backend implementation that consumes existing contracts.
- Add optional configuration that does not change required protocol signatures.

The following changes violate this specification:

- Change existing Protocol method signatures.
- Change `AgentEventStream` send/receive types incompatibly.
- Introduce backend-specific event types into core stream contracts.
- Require consumers to mutate or reinterpret existing event semantics.

## 3. Layer Boundary

The inner core owns only:

1. Event stream contracts
2. Interaction contracts
3. Session lifecycle contracts
4. Minimal extension protocols required by the six irreducible requirements

The inner core MUST NOT depend on UI, adapter, middleware rendering details, or backend-specific SDK types.

### 3.1 Responsibility Matrix

To preserve OCP and avoid ownership ambiguity, responsibilities are split as follows:

| Component | Owns | Does not own |
|---|---|---|
| Core loop contract | Event/interaction/session protocol shapes and invariants | UI rendering, human workflow details, provider SDK specifics |
| Session implementation | Runtime invariant enforcement, request correlation checks, event ordering guarantees | Policy authoring, UI transport decisions |
| Session factory/composition root | Dependency wiring (tool registry bindings, context mechanism implementation, approval authority binding) | Per-turn loop semantics |
| Adapter/runtime broker | Transport between loop and external authorities via `asend(...)` | Approval policy decisions |
| Approval authority | Approve/deny/escalate decisions | Stream type definitions or loop invariants |

## 4. Six Irreducible Requirements

An implementation is compliant only if it supports all six requirements:

1. Typed event stream
2. Tool gate
3. Post-tool observation
4. Tool registry
5. History/context protocol
6. Session lifecycle protocol

## 5. Normative Core Types

### 5.1 Typed Event Stream

The event stream contract MUST be represented by a typed async generator equivalent to:

```python
type AgentEventStream = AsyncGenerator[AgentEvent, InteractionResponse | None]
```

Where `AgentEvent` MUST include at least:

- `AgentChunk`
- `ToolCallInfo`
- `ToolCallResultInfo`
- `InteractionRequest`
- `AgentDone`

Optional event categories (for example status notifications) MAY be included if they are core-defined and backend-agnostic.

### 5.2 Tool Gate

Tool execution that requires authorization MUST pass through an explicit gate with bidirectional handshake semantics:

- Loop yields an interaction request to an external approval authority.
- Approval authority responds via `asend(...)` with the paired response type.
- `None` response MUST be treated as disconnected consumer and abort current run safely.

Transport of approval requests/responses is owned by adapter/runtime broker components outside the core loop.

Gate implementations MAY be policy-driven, user-driven, or hybrid, but MUST preserve explicit decision semantics.

### 5.2.1 Approval Authority Model

Approval decisions MUST be owned by a component outside the core loop.

- The approval authority MAY be a fully automated policy engine (for example rules, allowlists, risk scoring).
- The approval authority MAY delegate to a human reviewer through UI or workflow tooling.
- The approval authority MAY use mixed strategy (automatic default plus human escalation).

The core loop remains agnostic to who or what made the decision. It only enforces the typed handshake and applies the returned decision.

### 5.3 Post-Tool Observation

After each tool execution attempt, the loop MUST emit a corresponding post-tool observation event (`ToolCallResultInfo` equivalent) to the stream.

Observation hooks MAY read this event. Mutation of canonical tool result semantics is optional and outside minimum compliance.

### 5.4 Tool Registry

The system MUST support tool extension without changing core loop code.

Minimum requirement:

- A backend can register/add/remove tools through construction-time configuration or registry composition.

Required registry lifecycle capabilities:

- **Register**: add a tool binding before session run.
- **Disable/Remove**: make a registered tool unavailable without changing loop code.
- **Resolve**: map an incoming tool call name to an executable binding or a typed "not found" failure.

Ownership: tool registry composition is wired by session factory/composition root; loop contracts remain registry-agnostic.

Core MUST NOT hardcode a single immutable tool list in core contracts.

### 5.5 History/Context Protocol

A session MUST maintain turn history internally across runs and expose a read-only inspection surface.

Minimum requirement:

- History continuity across successful turns.
- A stable mechanism boundary to apply context shaping before model invocation.

The mechanism boundary MAY be a no-op implementation. Compliance requires the boundary to exist, not that non-trivial transforms are always enabled.

Ownership: core defines the boundary contract; session implementation/factory supplies the concrete mechanism.

### 5.6 Session Lifecycle Protocol

Core MUST define backend-agnostic lifecycle boundaries:

- Session creation through a factory protocol using pure configuration input.
- Session execution through a run protocol returning `AgentEventStream`.
- Session completion signal via final `AgentDone` event on normal completion.

## 6. Interaction Contract

All bidirectional interactions MUST be modeled through stable base types:

```python
@dataclass
class InteractionRequest:
    request_id: str

@dataclass
class InteractionResponse:
    request_id: str
```

Specific interactions (approval, user input, future additions) MUST extend these bases rather than modifying stream signatures.

### 6.1 Request Identity and Correlation

Interaction identity MUST satisfy:

- `request_id` is unique within an active run.
- A response MUST reference a previously emitted request with matching type expectations.
- Unknown or mismatched responses MUST fail fast (exception or typed protocol error) and terminate the active run.

Enforcement of these checks is owned by the session implementation.

### 6.2 Interaction Extensibility Rule

Adding a new interaction type MUST require only:

1. New request/response subtype definitions
2. Consumer handling logic for the new subtype

It MUST NOT require changing `AgentEventStream` type shape.

## 7. Session Invariants

Each session implementation MUST satisfy:

- **Single-active-run invariant**: At most one active `run()` per session.
- **Ordering invariant**: Events for a turn are emitted in causal order.
- **Completion invariant**: Normal completion emits `AgentDone` exactly once.
- **Cancellation invariant**: Cancellation terminates run without emitting completion event.
- **Error invariant**: Exceptions propagate; stream does not fabricate completion.

### 7.1 Invariant Enforcement

If `run()` is called while another run is active for the same session, implementation MUST fail fast and reject the second invocation.

Rejection SHOULD be raised as a typed runtime error at session boundary entry.

### 7.2 Minimum Ordering Guarantees

For a single tool call attempt in a turn, emitted events MUST satisfy:

1. Tool intent is emitted before any gate decision outcome is applied.
2. If a gate requires interaction, request emission occurs before awaiting `asend(...)`.
3. Post-tool observation (`ToolCallResultInfo` equivalent) is emitted after execution attempt completes.
4. `AgentDone` is emitted only after all events for that turn are emitted.

## 8. Extension Protocols (Optional but Recommended)

These extension contracts are outside minimum compliance but recommended for long-term OCP stability.

### 8.1 Tool Policy Protocol

A policy protocol MAY decide `allow`, `deny`, or `ask` before tool execution.

### 8.2 Context Transform Protocol

A context transform pipeline MAY mutate model-facing context before each invocation.

This section is optional extension guidance. The normative requirement for a stable context mechanism boundary is defined in §5.5.

### 8.3 Post-Tool Observer Protocol

Observers MAY consume tool execution outcomes for telemetry, auditing, and adaptive policies.

### 8.4 Multi-Agent Orchestration Protocol

Systems MAY add outer-loop orchestration (sub-agents, role-based workers) as an external extension that composes sessions, not by changing session contracts.

## 9. Compliance Matrix

A backend implementation MUST document compliance for each requirement:

- R1 Typed event stream
- R2 Tool gate
- R3 Post-tool observation
- R4 Tool registry
- R5 History/context protocol
- R6 Session lifecycle protocol

Non-compliance in any required dimension disqualifies inner-core compatibility.

Accountability: backend implementers MUST provide this compliance declaration; code review and CI policy SHOULD verify it.

## 10. Mapping to Current Agent C Symbols

Current Agent C implementations SHOULD map this spec through these core symbols:

- `AgentEvent`, `AgentEventStream`, `AgentSessionProtocol`, `SessionFactoryProtocol` in `src/agentc/core/types.py`
- `SessionConfig` in `src/agentc/core/command_types.py`
- Backend loop implementations in `src/agentc/core/backends/*/loop.py`

This section is informative for migration and does not redefine normative contracts.

## 11. Backward Compatibility

To preserve OCP:

- Existing compliant implementations MUST continue to compile and run when optional extensions are added.
- New capabilities MUST be introduced as additive protocols, implementations, or configuration.
- Breaking changes require a versioned successor spec rather than in-place mutation of this contract.

## 12. Authority and Related Documents

This file is the authoritative specification for Agent C inner core contracts.

Related documents:

- `docs/spec.md` (implementation-oriented backend guidance)
- `.github/prompts/plan-innerCoreSpec.prompt.md` (AI planning aid, non-authoritative)