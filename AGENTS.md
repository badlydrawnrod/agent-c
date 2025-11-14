# Agent C Development Guide

## Environment

- **Python**: 3.13+ required (no legacy Python support needed)
- **Package Manager**: `uv` (standalone installer)

## Commands

- **Install deps**: `uv sync`
- **Run agent**: `uv run agent-c --personality coder`
- **Run agent with provider override**: `uv run agent-c --personality coder --provider anthropic`
- **Run agent with model override**: `uv run agent-c --personality coder --model gpt-4`
- **Test all**: `uv run pytest`
- **Test single**: `uv run pytest path/to/test.py::test_function`
- **Type check**: `uv run mypy`
- **Lint**: `uv run ruff check`
- **Format**: `uv run ruff format`
- **Run without install**: `uvx --from . agent-c --personality coder`

## Architecture

### Core Modules

- **`agent.py`**: Entry point and event loop orchestration
- **`core/agent_factory.py`**: Agent creation and configuration management
- **`core/config.py`**: TOML configuration file loading
- **`core/file_ops.py`**: File operations with backup/restore capability
- **`core/tools.py`**: Tool definitions used by agents
- **`core/types.py`**: Type definitions and Pydantic models
- **`ui/console.py`**: Terminal UI using Rich library
- **`ui/protocol.py`**: UI protocol definitions

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

## Build and Distribution

- **Build system**: `uv_build`
- **Entry point**: `agentc.agent:main` (agent-c command)
- **Package includes**:
  - All Python files in `agentc/`
  - TOML config files
  - Markdown prompt files
  - UI module files
