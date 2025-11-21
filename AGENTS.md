# Agent C Development Guide

## Environment

- **Python**: 3.13+ required (no legacy Python support needed)
- **Package Manager**: `uv` (standalone installer)

## Commands

- **Install deps**: `uv sync`
  - (Windows PowerShell) Create & activate venv then install:
    ```powershell
    python -m venv .venv; .\.venv\Scripts\Activate.ps1; uv sync
    ```
- **Run agent**: `uv run agent-c --personality coder`
- **Run agent with provider override**: `uv run agent-c --personality coder --provider anthropic`
- **Run agent with model override**: `uv run agent-c --personality coder --model gpt-4`
- **Test all**: `uv run pytest`
- **Test single**: `uv run pytest path/to/test.py::test_function`
- **Type check**: `uv run mypy`
- **Lint**: `uv run ruff check`
- **Format**: `uv run ruff format`
- **Run without install**: `uvx --from . agent-c --personality coder`

## Quickstart (Windows PowerShell)

- Create a Python venv and activate it, then install dependencies:
  ```powershell
  python -m venv .venv; .\.venv\Scripts\Activate.ps1; uv sync
  ```
- Run the agent locally with the `coder` personality:
  ```powershell
  uv run agent-c --personality coder
  ```
- Run with provider / model overrides:
  ```powershell
  uv run agent-c --personality coder --provider anthropic
  uv run agent-c --personality coder --model gpt-4
  ```

## Architecture

### Core Modules

- **`agent.py`**: Entry point and event loop orchestration
- **`core/agent_factory.py`**: Agent creation and configuration management
- **`core/cli.py`**: Command-line argument parsing
- **`core/commands.py`**: User command handling and execution
- **`core/config.py`**: TOML configuration file loading
- **`core/file_ops.py`**: File operations with backup/restore capability
- **`core/runner.py`**: Agent execution loop, streaming, and tool handling
- **`core/types.py`**: Type definitions, Pydantic models, and LoopCallbacks protocol
- **`core/_config.py`**: Configuration utilities
- **`core/_model.py`**: Model selection and validation
- **`core/_prompt.py`**: Prompt loading and management
- **`core/_provider.py`**: Provider selection and initialization
- **`core/tools/`**: Tool definitions and registry
  - **`file_tools.py`**: File read/write/search operations
  - **`agent_tools.py`**: Agent delegation functionality
  - **`backup_tools.py`**: Backup and restore operations
  - **`registry.py`**: Tool registry and discovery
- **`ui/console.py`**: Terminal UI using Rich library (handles streaming & thinking)
- **`ui/protocol.py`**: UI protocol definitions

### Repository layout notes

- `src/agentc/` contains the source for the `agentc` package. This project uses a `src` layout for cleaner imports and packaging.
- `build/` contains wheels and installed copies for distribution or quick local checks.
- `.venv/` is the recommended local virtual environment name to store project dependencies.

### Configuration Files (in `src/agentc/`)

- **`providers.toml`**: LLM provider definitions (Ollama, Anthropic, OpenAI, etc.)
- **`personalities.toml`**: Agent personality definitions with prompt and provider mappings
- **`config.toml`**: User overrides for provider settings, API keys, and model selection
- **`prompts/`**: Markdown files containing system prompts for each personality

## Code Style

- **Language**: Python 3.13+, use modern Python features freely
- **Type hints**: Full type annotations required (MyPy strict mode)
- **Linting**: Ruff for linting and formatting
- **Imports**: Standard library → third-party → local
- **Paths**: Use `pathlib.Path`, never string paths
- **Data**: Pydantic models for validation
- **Errors**: Custom exceptions with descriptive messages
- **Formatting**: Auto-format with `uv run ruff format`
- **Console output**: Rich library for terminal formatting
- **User input**: Prompt Toolkit library
- **Async**: Use `async`/`await` pattern for I/O operations

## Development

- Activate the local venv then run linters, type checks, and tests frequently:
  ```powershell
  .\.venv\Scripts\Activate.ps1; uv run ruff check; uv run mypy; uv run pytest
  ```
- Run a single test for quick feedback:
  ```powershell
  uv run pytest tests/test_core_interaction.py::test_command
  ```
- Run tests with coverage (if `pytest-cov` is in dev-deps):
  ```powershell
  uv run pytest --cov=src/agentc
  ```

## Configuration & secrets

- The `config.toml` in `src/agentc/` holds configuration overrides (provider settings, model defaults, and API keys). Set provider credentials with environment variables or copy `config.toml` into a local file and update values.

## Build and Distribution

- **Build system**: `uv_build`
- **Entry point**: `agentc.agent:main` (agent-c command)
- **Package includes**:
  - All Python files in `agentc/`
  - TOML config files
  - Markdown prompt files
  - UI module files
