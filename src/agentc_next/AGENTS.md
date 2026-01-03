You are an automated code assistant working on Agent C Next in a Python 3.13+ repo. Follow these rules exactly when producing code changes.

You must preserve the repo's layered, strongly-typed architecture.

### Package Structure (`src/agentc_next/`)
- **`core/`**: Agnostic logic.
  - `types.py`: Central `AgentEvent` union (chunks, tool calls, tool results, approvals, done), `AgentSessionProtocol`, and shared dataclasses.
  - `config.py`: Centralized system constants (output caps, suffixes, default skill dirs). Must be UI-agnostic.
  - `loop.py`: `AgentSession` implementing the bidirectional async generator loop and mapping pydantic_ai events to `AgentEvent`.
  - `factory.py`: `create_agent` factory assembling the `pydantic_ai.Agent` with Ollama (`gpt-oss:20b`), toolset, and skills table.
  - `tool_parsing.py`: Robust JSON/dict argument handling for tool calls.
  - `tools.py`: Concrete tool implementations (`list_files`, `glob_paths`, `search_files`, `read_file`, `edit_file`, `run_command`).
  - `skill_loader.py`: Discovers `SKILL.md` skills under configured directories and renders a skills table for the system prompt.
- **`middleware/`**: Cross-cutting concerns.
  - `debouncing.py`: `DebouncingMiddleware` for text/thinking delta aggregation (default threshold 40 chars).
- **`adapters/`**: Bridging core logic to specific frameworks.
  - `textual.py`: `TextualAgentAdapter` translating `AgentEvent` to Textual messages.
  - `console.py`: `ConsoleAgentAdapter` translating `AgentEvent` to console callbacks.
  - `textual_messages.py`: Textual-specific `Message` types (e.g., `AgentText`, `AgentApprovalRequest`).
  - `console_messages.py`: Console event dataclasses.
- **`ui/`**: User interface entry points and applications. `textual_app.py` and `widgets.py` define the Textual interface.
  - `textual_app.py`: The main Textual `App` implementation.
  - `widgets.py`: Reusable UI components (status bar, approval forms, etc.).
  - `run_textual.py`: Launcher for the Textual UI.
  - `run_console.py`: Launcher for the Console UI demo (auto-approval sample prompt).

### Current implementation snapshot
- Event flow: `AgentSession.run()` streams pydantic_ai parts, maps them to `AgentEvent`, and supports tool call results alongside tool call announcements.
- Debouncing: `DebouncingMiddleware` buffers short text/thinking deltas but lets tool calls, tool results, approvals, and completion events pass through immediately.
- Tools: All file ops are confined to the working tree, `read_file` emits `cat -n` formatting, `edit_file` enforces a single match and writes atomically with `.bak` backups, and `run_command` plus `edit_file` require approval. `glob_paths` and `search_files` respect combined ignore patterns (defaults like `.git/` plus `.gitignore`).
- Skills: `SkillLoader` scans `.github/skills` and `.claude/skills` by default and injects a skills table plus usage guidance into the system prompt.
- Model defaults: `create_agent` uses `OpenAIChatModel` with `OllamaProvider` (`gpt-oss:20b`, `http://localhost:11434/v1`).

### Rules (strict)
- **Layers**: types (core) / loop / middleware / adapter / UI. State the layer(s) you change **before** modifying code.
- **Cross-layer types**: If data flows across layers, add a typed dataclass to `src/agentc_next/core/types.py`. No cross-layer imports from `core` to `ui`.
- **Handshake**: The `AgentSession.run` loop is a bidirectional async generator yielding `AgentEvent` and receiving `ApprovalResponse` via `asend`. Preserve this explicit handshake.
- **Typing & style**: All new or modified public functions must have full type annotations and docstrings. Use `Protocol` for interfaces, `TypeAlias` for complex types, and `@dataclass` for event/value objects.
- **Tests (Mandatory)**: Maintain and update the test suite in `tests/agentc_next/`. Covering:
  - `core.loop`: `test_loop.py` (handshake, history, tool call yielding).
  - `core.factory`: `test_factory.py` (agent creation).
  - `core.tool_parsing`: `test_tool_parsing.py` (JSON argument handling).
  - `core.tools`: `test_tools.py` and `test_tool_result.py` (file operations, glob/search, safety constraints, tool result mapping).
  - `core.skill_loader`: `test_skill_loader.py` (skill discovery and skills table rendering).
  - `middleware.debouncing`: `test_debouncing.py` (flush logic and delta aggregation).
  - `adapters.textual`: `test_textual.py` (mapping `AgentEvent` to `adapters.messages`).
  - `adapters.console`: `test_console.py` (console event mapping and approval flow).

### Verification & Outputs
In your reply include:
1) `files_changed`: exact file paths changed.
2) Full file contents or unified diffs for each changed file.
3) Test file path(s) and test contents.
4) One-line commit message and a brief summary explaining how layering was preserved.
5) PR checklist status: run `uv run ruff check`, `uv run mypy`, and `uv run pytest tests/agentc_next/`.

Deliver only the requested items. Do not add unrelated refactors or features.
