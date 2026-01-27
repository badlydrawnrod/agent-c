# Agent C Development Guide

> **Note**: This guide consolidates rules from package-level documentation (2026-01-17). All architectural and coding rules apply to both human developers and AI coding assistants.

**You are an automated code assistant working on Agent C in a Python 3.13+ repository. Follow these rules exactly when producing code changes. You must preserve the repository's layered, strongly-typed architecture.**

## Environment

- **Python**: 3.13+ required (no legacy Python support needed)
- **Package Manager**: `uv` (standalone installer)

## Quick Start Commands

- **Install deps**: `uv sync`
  - (Windows PowerShell) Create & activate venv then install:
    ```powershell
    python -m venv .venv; .\venv\Scripts\Activate.ps1; uv sync
    ```
- **Run Agent C (Textual UI)**: `uv run agent-c`
- **Run Console UI**: `uv run run-console`
- **Test all**: `uv run pytest`
- **Test agentc only**: `uv run pytest tests/core/ tests/middleware/ tests/adapters/`
- **Type check**: `uv run mypy`
- **Lint**: `uv run ruff check`
- **Format**: `uv run ruff format`

## Windows PowerShell Quickstart

```powershell
uv sync
uv run agent-c  # Launch the Textual UI
```

## Architecture Overview

> For visual architecture diagrams, see the [Architecture section in README.md](README.md#architecture).

The project uses an event-driven, layered architecture with clear separation of concerns:

**Layer Stack**: types (core) → loop → middleware → adapter → UI

### Main Implementation (`src/agentc/`)

Event-driven, layered architecture with:

- **`core/`**: Agnostic agentic logic (types, event loop, agent factory, tools). The `tools/` package provides filesystem operations (with combined ignore patterns), file editing with atomic writes and backups, and command execution. `skill_loader.py` discovers `SKILL.md` files from bundled skills (installed to user data directory) and project directories.
  - `types.py`: Event-stream union (`AgentEvent`), `AgentSessionProtocol`, tool result dataclasses, and re-exports of patching types.
  - `config_types.py`: `BackendConfig` and `ModelConfig` for provider/model presets.
  - `command_types.py`: `CommandType`, `CommandResult`, and `CommandEffect` for command parsing/execution.
  - `deps.py`: `RunDeps` context for dependency-injected agent runs.
  - `config.py`: Centralized system constants (output caps, suffixes, default skill dirs, `DEFAULT_MODEL`, `DEFAULT_PROVIDER_DIRS`). Must be UI-agnostic.
  - `loop.py`: `AgentSession` implementing the bidirectional async generator loop and mapping pydantic_ai events to `AgentEvent`.
  - `factory.py`: `create_agent` factory assembling the `pydantic_ai.Agent` using the model preset configured in `providers.toml` (default preset: `local-oss` on the `ollama` backend), plus the shared toolset and skills table.
  - `commands.py`: Command parsing (`CommandParser`) and effect-based execution (`execute_command`).
    - `CommandParser` performs pure parsing without validation
    - Commands produce pure `CommandEffect` data containing `SessionConfig`
    - Session factories validate model names and apply configuration to create new sessions
  - `tool_parsing.py`: Robust JSON/dict argument handling for tool calls.
  - `tools/`: Tool package organized by category (see Available Tools section)
  - `skill_loader.py`: Discovers `SKILL.md` skills from project directories (`.github/skills`, `.claude/skills`), user directory (`~/.agentc/skills`), and bundled skills (installed to platform-specific user data directory). Earlier directories take precedence.
  - `provider_loader.py`: Discovers, loads, and merges `providers.toml` files from repo/user/bundled locations (priority: repo > user > bundled). Dynamically imports provider/model classes and builds instances with API keys, base URLs, and model params.

- **`middleware/`**: Cross-cutting concerns (e.g., debouncing)
  - `debouncing.py`: `DebouncingMiddleware` for text/thinking delta aggregation (default threshold: 40 characters, configurable).

- **`adapters/`**: Bridges core event stream to specific frameworks. Owns translation logic and UI-specific message types.
  - `textual.py`: `TextualAgentAdapter` translating `AgentEvent` to Textual messages.
  - `console.py`: `ConsoleAgentAdapter` translating `AgentEvent` to console callbacks.
  - `textual_messages.py`: Textual-specific `Message` types (e.g., `AgentText`, `AgentApprovalRequest`).
  - `console_messages.py`: Console event dataclasses.

- **`ui/`**: User interface implementations (Textual TUI, Console)
  - `textual_app.py`: The main Textual `App` implementation.
    - Receives model names list via dependency injection from composition root
    - Each backend's entry point discovers models using backend-specific mechanisms
    - UI layer remains completely backend-agnostic
  - `widgets.py`: Reusable UI components (status bar, approval forms, etc.).
  - `widgets.py`: Reusable UI components (status bar, approval forms, etc.).
  - `run_textual.py`: Launcher for the Textual UI (entry point: `agent-c`).
  - `run_console.py`: Launcher for the Console UI demo (auto-approval sample prompt, entry point: `run-console`).

- **`skills/`**: Bundled skills (e.g., fibonacci-number) packaged with the application

### Event Flow

1. **`AgentSession.run()`** streams pydantic_ai events using the current history and optional deferred tool approvals.
2. **Core layer** maps pydantic_ai parts into `AgentEvent` items, including tool call results so UIs can display execution outcomes.
3. **`DebouncingMiddleware`** aggregates small text/thinking deltas (buffered until threshold reached), while passing tool calls, tool results, approvals, and completion events through immediately.
4. **Adapters** consume the debounced stream, convert events to UI messages/callback events, and perform the approval handshake by sending an `ApprovalResponse` back into the async generator via `asend`.

### Command Execution

User commands follow an effect-based pattern that separates parsing, execution logic, and UI concerns:

1. **`CommandParser.parse(user_input)`** → `CommandResult` (parsed command with type and args)
2. **`execute_command(result)`** → `CommandEffect | None` (pure data: new session, notification, reset flag)
3. **UI applies the effect**: updates session, displays notification, resets state

Supported commands: `/clear`, `/reset`, `/exit`, `/quit`, `/bye`, `/model <name>`, `/help`

Framework-specific commands (`/exit`, unknown commands) return `None` and are handled directly by the UI layer.

### Session Factory Pattern

Commands produce `SessionConfig` (pure data), which session factories translate into backend-specific sessions:

- **`SessionFactoryProtocol`** (`types.py`): Interface for session creation
- **`PydanticAISessionFactory`** (`backends/pydantic_ai/`): Uses `create_agent()` + `AgentSession`
- **`GhCopilotSessionFactory`** (`backends/github_copilot/`): Uses `CopilotClient.create_session()`

Entry points inject concrete factories into the UI layer, which uses the Protocol abstraction.

### Skills System

`SkillLoader` scans bundled skills (installed to user data directory) and project directories (`.github/skills` and `.claude/skills` by default) for `SKILL.md` descriptors. `create_agent` injects a table of discovered skills into the system prompt, with guidance to `cd` into the skill base directory before running documented commands.

## Available Tools

Agent C provides the following tools in the `core/tools/` package:

### Filesystem Tools (`tools/filesystem.py`)

- **list_files**: List directory contents with gitignore support
- **glob_paths**: Find files matching glob patterns recursively
  - Respects default ignore patterns and `.gitignore` if it exists in the base path
  - Returns newline-separated relative paths; directories end with trailing slash
  - Caps results at `MAX_TOOL_OUTPUT_LINES` (200); if truncated, a summary line is appended
- **search_files**: Search for text in files with line-level matches
  - Case-sensitive substring checks on UTF-8 text (binary data is skipped)
  - Returns relative paths with `path:line: text` format
  - Respects combined ignore patterns and caps output at `MAX_TOOL_OUTPUT_LINES`

### Editing Tools (`tools/editing.py`)

- **read_file**: Read file with `cat -n` style line numbers
  - Output is line-numbered (right-aligned 6-digit number, tab, then content)
  - Trailing newline is preserved
- **create_file**: Create new files with atomic writes (**requires approval**)
  - Creates parent directories if needed
  - Writes atomically via a temp file
- **edit_file**: Replace a unique string occurrence in a file (**requires approval**)
  - Enforces single-match requirement (raises `ModelRetry` if multiple matches)
  - Creates timestamped backups (`.bak`) before writing
  - Writes atomically via temp files
- **apply_hunks**: Apply structured patch hunks to one or more files atomically (**requires approval**)
  - Uses anchor-based matching (lines before/after the edit)
  - Supports insert (empty `remove`), delete (empty `add`), and replace operations
  - Transactional: all hunks must match or no files are modified
  - Creates timestamped backups before modification
  - Returns structured JSON summary of applied changes

### Execution Tools (`tools/execution.py`)

- **run_command**: Execute shell commands asynchronously (**requires approval**)
  - Uses asyncio.create_subprocess_shell with stdin piped
  - Returns captured output (stdout then stderr) trimmed

### Security and Constraints

All tools respect `.gitignore` patterns and default ignore patterns. File operations use atomic writes via temp files. The `resolve_path` function in `tools/_shared.py` serves as the primary security boundary, ensuring all file operations are sandboxed to configured root directories.

Default ignore patterns: `.git/`, `__pycache__/`, `*.pyc`, `.venv/`, `node_modules/`, `.DS_Store`.

## Code Style & Architecture Rules

When working on `agentc`, follow these rules strictly:

### Layering & Dependencies
- **Layer stack**: types (core) / loop / middleware / adapter / UI
- State the layer(s) you change **before** modifying code
- No cross-layer imports from `core` to `ui`
- If data flows across layers, add a typed dataclass to the appropriate core module (`types.py` for events, `command_types.py` for commands, `config_types.py` for provider/model configs, `deps.py` for dependency context)

### Event-Driven Pattern
- The run loop is a bidirectional async generator
- Preserve explicit `ApprovalRequest` → `ApprovalResponse` send/receive via `asend`
- All events defined in `core/types.py`

### Typing & Style
- **Language**: Python 3.13+, use modern Python features freely
- **Type hints**: Full type annotations required (MyPy strict mode)
- All new or modified public functions must have full type annotations and docstrings
- Use `Protocol` for interfaces, `TypeAlias` for complex types, `@dataclass` for event/value objects
- **Imports**: Standard library → third-party → local
- **Paths**: Use `pathlib.Path`, never string paths
- **Errors**: Custom exceptions with descriptive messages

### Tools & Formatting
- **Linting**: Ruff for linting and formatting
- **Console output**: Rich library for terminal formatting
- **Async**: Use `async`/`await` pattern for I/O operations

### Testing (Mandatory)
Maintain and update the test suite in `tests/`. Must cover:
- `core.loop`: approval handshake, history, and tool call yielding
- `core.factory`: agent creation with model presets
- `core.commands`: command parsing and effect-based execution
- `core.tool_parsing`: robust JSON argument handling
- `core.tools`: 
  - `test_tools_filesystem.py`: list_files, glob_paths, search_files
  - `test_tools_editing.py`: read_file, create_file, edit_file, apply_hunks
  - `test_tools_execution.py`: run_command
  - `test_tool_result.py`: tool result mapping
  - `test_ignore_logic.py`: gitignore support integration
- `core.skill_loader`: skill discovery and skills table rendering
- `core.provider_loader`: provider/model loading and merging
- `middleware.debouncing`: flush logic and delta aggregation
- `adapters.textual`: mapping to `adapters.messages`
- `adapters.console`: console event mapping and approval flow

## Development Workflow

1. **Activate the venv** and run frequent checks:
   ```powershell
   .\venv\Scripts\Activate.ps1
   uv run ruff check; uv run mypy; uv run pytest tests/core/ tests/middleware/ tests/adapters/
   ```

2. **Run a single test** for quick feedback:
   ```powershell
   uv run pytest tests/core/test_loop.py::test_agent_session_history
   ```

3. **Before submitting changes**, verify:
   - [ ] `uv run ruff check` passes (no linting issues)
   - [ ] `uv run mypy` passes (no type errors)
   - [ ] `uv run pytest` passes (all tests green)
   - [ ] Updated tests for any new functionality
   - [ ] Updated docstrings for public APIs

## Configuration & Secrets

- The `providers.toml` file in `src/agentc/` holds backend definitions and model presets
- Set provider credentials with environment variables or update local config files
- Example: `export ANTHROPIC_API_KEY=your_key` (Linux/macOS) or `$env:ANTHROPIC_API_KEY = 'your_key'` (PowerShell)

### Custom Backends and Models

Agent C discovers configuration in priority order:

1. **Repo-local**: `.agentc/providers.toml` (highest priority)
2. **User-global**: `~/.agentc/providers.toml`
3. **Bundled**: `src/agentc/providers.toml` (lowest priority)

Entries from earlier locations override those with the same name later.

#### providers.toml Structure

```toml
[backends.ollama]
provider_cls = "pydantic_ai.providers.ollama.OllamaProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
api_key_env = "MY_API_KEY"
base_url = "http://localhost:11434/v1"

[models.local]
backend = "ollama"
model_name = "deepseek-r1:32b"
params = {temperature = 0.2}
```

#### Implementation Details (`core/provider_loader.py`)

- **`get_default_provider_dirs()`**: Returns discovery paths in priority order
- **`load_providers(dirs)`**: Discovers and merges backend/model presets; earlier directories override later ones
- **`build_model(model_config, backend_config)`**: Dynamically imports provider/model classes, applies params, passes `api_key`/`base_url` overrides
- **Error handling**: Raises `FileNotFoundError` if bundled providers missing; `ValueError` on import failures

## Code Review Checklist

When contributing to `agentc`:
1. **Verify layering**: State which layers you modified
2. **Check types**: All public functions fully annotated
3. **Validate tests**: New tests cover changes, all existing tests pass
4. **Ensure async patterns**: Proper use of `async`/`await` and `asend` for handshakes
5. **Review imports**: No circular dependencies, respect layer boundaries
6. **Run all checks**: `ruff check`, `mypy`, and `pytest`

## Verification & Outputs

When making changes, include in your response:

1. **`files_changed`**: Exact file paths changed
2. **Full file contents or unified diffs** for each changed file
3. **Test file path(s) and test contents**
4. **One-line commit message** and brief summary explaining how layering was preserved
5. **PR checklist status**: Run `uv run ruff check`, `uv run mypy`, and `uv run pytest tests/core/ tests/middleware/ tests/adapters/`

**Deliver only the requested items.** Do not add unrelated refactors or features.

## Build and Distribution

- **Build system**: `uv_build`
- **Entry points**:
  - `agentc.ui.run_textual:main` (agent-c command - default Textual UI)
  - `agentc.ui.run_console:main` (run-console command)
  - `agentc.ui.run_textual:main` (run-textual command)
