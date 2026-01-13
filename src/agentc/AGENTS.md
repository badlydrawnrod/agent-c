You are an automated code assistant working on Agent C in a Python 3.13+ repo. Follow these rules exactly when producing code changes.

You must preserve the repo's layered, strongly-typed architecture.

### Package Structure (`src/agentc/`)
- **`core/`**: Agnostic logic.
  - `types.py`: Central `AgentEvent` union (chunks, tool calls, tool results, approvals, done), `AgentSessionProtocol`, and shared dataclasses. Also defines `CommandEffect` for effect-based command execution, plus `BackendConfig` and `ModelConfig` for backend/model presets.
  - `config.py`: Centralized system constants (output caps, suffixes, default skill dirs, `DEFAULT_MODEL`, `DEFAULT_PROVIDER_DIRS`). Must be UI-agnostic.
  - `loop.py`: `AgentSession` implementing the bidirectional async generator loop and mapping pydantic_ai events to `AgentEvent`.
  - `factory.py`: `create_agent` factory assembling the `pydantic_ai.Agent` using the model preset configured in `providers.toml` (repo default preset is `ollama-gpt-oss-120b` on the `ollama` backend), plus the shared toolset and skills table.
  - `commands.py`: Command parsing (`CommandParser`) and effect-based execution (`execute_command`). Commands produce pure `CommandEffect` data; UIs apply effects.
  - `tool_parsing.py`: Robust JSON/dict argument handling for tool calls.
  - `tools.py`: Concrete tool implementations (`list_files`, `glob_paths`, `search_files`, `read_file`, `edit_file`, `create_file`, `run_command`).
  - `skill_loader.py`: Discovers `SKILL.md` skills from project directories (`.github/skills`, `.claude/skills`), user directory (`~/.agentc/skills`), and bundled skills (installed to platform-specific user data directory). Earlier directories take precedence.
  - `provider_loader.py`: Discovers, loads, and merges `providers.toml` files from repo/user/bundled locations (priority: repo > user > bundled). Dynamically imports provider/model classes and builds instances with API keys, base URLs, and model params.
    - `get_default_provider_dirs()`: Returns discovery paths in priority order (`.agentc/`, `~/.agentc/`, bundled)
    - `load_providers(dirs)`: Merges backend and model preset configs with precedence (earlier overrides later)
    - `build_model(model_config, backend_config)`: Instantiates provider and model, passes merged params plus api key/base URL overrides
- **`middleware/`**: Cross-cutting concerns.
  - `debouncing.py`: `DebouncingMiddleware` for text/thinking delta aggregation (default threshold 40 chars).
- **`adapters/`**: Bridging core logic to specific frameworks.
  - `textual.py`: `TextualAgentAdapter` translating `AgentEvent` to Textual messages.
  - `console.py`: `ConsoleAgentAdapter` translating `AgentEvent` to console callbacks.
  - `textual_messages.py`: Textual-specific `Message` types (e.g., `AgentText`, `AgentApprovalRequest`).
  - `console_messages.py`: Console event dataclasses.
- **`ui/`**: User interface entry points and applications.
  - `textual_app.py`: The main Textual `App` implementation.
  - `widgets.py`: Reusable UI components (status bar, approval forms, etc.).
  - `run_textual.py`: Launcher for the Textual UI.
  - `run_console.py`: Launcher for the Console UI demo (auto-approval sample prompt).
- **`skills/`**: Bundled skills packaged with the application, copied to user data directory on first run.

### Current implementation snapshot
- Event flow: `AgentSession.run()` streams pydantic_ai parts, maps them to `AgentEvent`, and supports tool call results alongside tool call announcements.
- Debouncing: `DebouncingMiddleware` buffers short text/thinking deltas but lets tool calls, tool results, approvals, and completion events pass through immediately.
- Command execution: Effect-based pattern separates command logic from UI. `CommandParser.parse()` returns `CommandResult`; `execute_command()` produces `CommandEffect` (pure data); UI layer applies effects. Commands like `/clear` and `/model <name>` are handled generically; framework-specific commands (`/exit`, unknown commands) are handled directly by the UI.
- Tools: All file ops are confined to the working tree, `read_file` emits `cat -n` formatting, `edit_file` enforces a single match and writes atomically with `.bak` backups, and `run_command` plus `edit_file` plus `create_file` require approval. `glob_paths` and `search_files` respect combined ignore patterns (defaults like `.git/` plus `.gitignore`).
- Skills: `SkillLoader` discovers skills from project directories (`.github/skills`, `.claude/skills`), user directory (`~/.agentc/skills`), and bundled skills (installed to user data directory). Returns all discovered skills (no precedence filtering) and injects a skills table plus usage guidance into the system prompt.
- Model defaults: backends and models are loaded from `src/agentc/providers.toml` via `provider_loader.load_providers()` and `provider_loader.build_model()`; the repo default model preset is `ollama-gpt-oss-120b (see `core/config.py`), which maps to an Ollama-backed model string in `providers.toml` (for example `gpt-oss:120b-cloud` at `http://localhost:11434/v1`).

### Rules (strict)
- **Layers**: types (core) / loop / middleware / adapter / UI. State the layer(s) you change **before** modifying code.
- **Cross-layer types**: If data flows across layers, add a typed dataclass to `src/agentc_next/core/types.py`. No cross-layer imports from `core` to `ui`.
- **Handshake**: The `AgentSession.run` loop is a bidirectional async generator yielding `AgentEvent` and receiving `ApprovalResponse` via `asend`. Preserve this explicit handshake.
- **Typing & style**: All new or modified public functions must have full type annotations and docstrings. Use `Protocol` for interfaces, `TypeAlias` for complex types, and `@dataclass` for event/value objects.
- **Tests (Mandatory)**: Maintain and update the test suite in `tests/agentc/`. Covering:
  - `core.loop`: `test_loop.py` (handshake, history, tool call yielding).
  - `core.factory`: `test_factory.py` (agent creation).
  - `core.commands`: `test_commands.py` (command parsing and effect-based execution).
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
5) PR checklist status: run `uv run ruff check`, `uv run mypy`, and `uv run pytest tests/core/ tests/middleware/ tests/adapters/`.

Deliver only the requested items. Do not add unrelated refactors or features.
