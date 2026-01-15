# Agent C Development Guide

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

The project uses an event-driven, layered architecture:

### Main Implementation (`src/agentc/`)
Event-driven, layered architecture with:
- **`core/`**: Agnostic agentic logic (types, event loop, agent factory, tools). `tools.py` uses combined ignore patterns for file discovery. `skill_loader.py` discovers `SKILL.md` files from bundled skills (installed to user data directory) and project directories.
- **`middleware/`**: Cross-cutting concerns (e.g., debouncing)
- **`adapters/`**: Bridges core event stream to specific frameworks. Owns translation logic and UI-specific message types.
- **`ui/`**: User interface implementations (Textual TUI, Console)
- **`skills/`**: Bundled skills (e.g., fibonacci-number) packaged with the application

## Available Tools

Agent C provides the following tools in `core/tools.py`:

- **list_files**: List directory contents with gitignore support
- **glob_paths**: Find files matching glob patterns recursively
- **search_files**: Search for text in files with line-level matches
- **read_file**: Read file with cat -n style line numbers
- **create_file**: Create new files with atomic writes
- **edit_file**: Replace a unique string occurrence in a file
- **apply_hunks**: Apply structured patch hunks to one or more files atomically
  - Uses anchor-based matching (lines before/after the edit)
  - Supports insert (empty `remove`), delete (empty `add`), and replace operations
  - Transactional: all hunks must match or no files are modified
  - Creates timestamped backups before modification
  - Returns structured JSON summary of applied changes
- **run_command**: Execute shell commands asynchronously

All tools respect `.gitignore` patterns and default ignore patterns. File operations use atomic writes via temp files.

## Code Style & Architecture Rules

When working on `agentc`, follow these rules strictly:

### Layering & Dependencies
- **Layer stack**: types (core) / loop / middleware / adapter / UI
- State the layer(s) you change **before** modifying code
- No cross-layer imports from `core` to `ui`
- If data flows across layers, add a typed dataclass to `src/agentc/core/types.py`

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
- `middleware.debouncing`: flush logic and delta aggregation
- `adapters.textual`: mapping to `adapters.messages`
- `core.tool_parsing`: robust JSON argument handling
- `core.apply_hunks`: hunk matching, insertion, deletion, transactional behavior across files

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

## Build and Distribution

- **Build system**: `uv_build`
- **Entry points**:
  - `agentc.ui.run_textual:main` (agent-c command - default Textual UI)
  - `agentc.ui.run_console:main` (run-console command)
  - `agentc.ui.run_textual:main` (run-textual command)
