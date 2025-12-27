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
- **Run legacy agent**: `uv run agent-c --personality coder`
- **Run Textual UI (agentc_next)**: `uv run run-textual`
- **Run Console UI (agentc_next)**: `uv run run-console`
- **Test all**: `uv run pytest`
- **Test agentc_next only**: `uv run pytest tests/agentc_next/`
- **Type check**: `uv run mypy`
- **Lint**: `uv run ruff check`
- **Format**: `uv run ruff format`

## Windows PowerShell Quickstart

```powershell
python -m venv .venv; .\venv\Scripts\Activate.ps1; uv sync
uv run run-textual  # Launch the Textual UI
```

## Architecture Overview

The project contains two main implementations:

### Legacy Implementation (`src/agentc/`)
Traditional monolithic agent with file operations, multiple personalities, and CLI interface.

### Next-Generation Implementation (`src/agentc_next/`)
Event-driven, layered architecture with:
- **`core/`**: Agnostic agentic logic (types, event loop, agent factory, tools). No UI or framework dependencies.
- **`middleware/`**: Cross-cutting concerns (e.g., debouncing)
- **`adapters/`**: Bridges core event stream to specific frameworks. Owns translation logic and UI-specific message types.
- **`ui/`**: User interface implementations (Textual TUI, Console)

## Code Style & Architecture Rules (agentc_next)

When working on `agentc_next`, follow these rules strictly:

### Layering & Dependencies
- **Layer stack**: types (core) / loop / middleware / adapter / UI
- State the layer(s) you change **before** modifying code
- No cross-layer imports from `core` to `ui`
- If data flows across layers, add a typed dataclass to `src/agentc_next/core/types.py`

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
Maintain and update the test suite in `tests/agentc_next/`. Must cover:
- `core.loop`: approval handshake, history, and tool call yielding
- `middleware.debouncing`: flush logic and delta aggregation
- `adapters.textual`: mapping to `adapters.messages`
- `core.tool_parsing`: robust JSON argument handling

## Development Workflow

1. **Activate the venv** and run frequent checks:
   ```powershell
   .\venv\Scripts\Activate.ps1
   uv run ruff check; uv run mypy; uv run pytest tests/agentc_next/
   ```

2. **Run a single test** for quick feedback:
   ```powershell
   uv run pytest tests/agentc_next/core/test_loop.py::test_agent_session_history
   ```

3. **Before submitting changes**, verify:
   - [ ] `uv run ruff check` passes (no linting issues)
   - [ ] `uv run mypy` passes (no type errors)
   - [ ] `uv run pytest tests/agentc_next/` passes (all tests green)
   - [ ] Updated tests for any new functionality
   - [ ] Updated docstrings for public APIs

## Configuration & Secrets

- The `config.toml` files in `src/agentc/` and `src/agentc_next/` hold configuration overrides
- Set provider credentials with environment variables or update local config files
- Example: `export ANTHROPIC_API_KEY=your_key` (Linux/macOS) or `$env:ANTHROPIC_API_KEY = 'your_key'` (PowerShell)

## Code Review Checklist

When contributing to `agentc_next`:
1. **Verify layering**: State which layers you modified
2. **Check types**: All public functions fully annotated
3. **Validate tests**: New tests cover changes, all existing tests pass
4. **Ensure async patterns**: Proper use of `async`/`await` and `asend` for handshakes
5. **Review imports**: No circular dependencies, respect layer boundaries
6. **Run all checks**: `ruff check`, `mypy`, and `pytest tests/agentc_next/`

## Build and Distribution

- **Build system**: `uv_build`
- **Entry points**:
  - `agentc.agent:main` (legacy agent-c command)
  - `agentc_next.ui.run_textual:main` (run-textual)
  - `agentc_next.ui.run_console:main` (run-console)
