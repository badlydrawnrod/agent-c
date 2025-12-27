You are an automated code assistant working on Agent C Next in a Python 3.13+ repo. Follow these rules exactly when producing code changes.

You must preserve the repo's layered, strongly-typed architecture.

### Package Structure (`src/agentc_next/`)
- **`core/`**: Agnostic logic.
  - `types.py`: Central `AgentEvent` union, `AgentSessionProtocol`, and shared dataclasses.
  - `loop.py`: `AgentSession` implementing the bidirectional async generator loop.
  - `factory.py`: `create_agent` factory for assembling the `pydantic_ai.Agent`.
  - `tool_parsing.py`: Robust JSON/dict argument handling for tool calls.
  - `tools.py`: Concrete tool implementations (e.g., `edit_file`).
- **`middleware/`**: Cross-cutting concerns.
  - `debouncing.py`: `DebouncingMiddleware` for text delta aggregation.
- **`adapters/`**: Bridging core logic to specific frameworks.
  - `textual.py`: `TextualAgentAdapter` translating `AgentEvent` to Textual messages.
  - `textual_messages.py`: Textual-specific `Message` types (e.g., `AgentText`, `AgentApprovalRequest`).
- **`ui/`**: User interface entry points and applications.
  - `textual_app.py`: The main Textual `App` implementation.
  - `run_textual.py`: Launcher for the Textual UI.
  - `run_console.py`: Launcher for the Console UI.

### Rules (strict)
- **Layers**: types (core) / loop / middleware / adapter / UI. State the layer(s) you change **before** modifying code.
- **Cross-layer types**: If data flows across layers, add a typed dataclass to `src/agentc_next/core/types.py`. No cross-layer imports from `core` to `ui`.
- **Handshake**: The `AgentSession.run` loop is a bidirectional async generator yielding `AgentEvent` and receiving `ApprovalResponse` via `asend`. Preserve this explicit handshake.
- **Typing & style**: All new or modified public functions must have full type annotations and docstrings. Use `Protocol` for interfaces, `TypeAlias` for complex types, and `@dataclass` for event/value objects.
- **Tests (Mandatory)**: Maintain and update the test suite in `tests/agentc_next/`. Covering:
  - `core.loop`: `test_loop.py` (handshake, history, tool call yielding).
  - `core.factory`: `test_factory.py` (agent creation).
  - `core.tool_parsing`: `test_tool_parsing.py` (JSON argument handling).
  - `middleware.debouncing`: `test_debouncing.py` (flush logic and delta aggregation).
  - `adapters.textual`: `test_textual.py` (mapping `AgentEvent` to `adapters.messages`).

### Verification & Outputs
In your reply include:
1) `files_changed`: exact file paths changed.
2) Full file contents or unified diffs for each changed file.
3) Test file path(s) and test contents.
4) One-line commit message and a brief summary explaining how layering was preserved.
5) PR checklist status: run `uv run ruff check`, `uv run mypy`, and `uv run pytest tests/agentc_next/`.

Deliver only the requested items. Do not add unrelated refactors or features.
