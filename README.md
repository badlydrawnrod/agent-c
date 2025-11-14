# Agent C

A code editing assistant powered by [Pydantic AI](https://ai.pydantic.dev/), supporting multiple LLM providers and delegatable sub-agents. Agent C provides tools for reading, editing, creating, and searching files with built-in backup and restoration capabilities.

Hugely inspired by [How to Build an Agent](https://ampcode.com/how-to-build-an-agent) by Thorsten Ball of [AmpCode](https://ampcode.com/).

## Features

- **Multiple LLM Providers**: Support for Ollama, Anthropic Claude, OpenAI GPT, and others
- **Configurable Personalities**: Pre-built coder, reviewer, and debugger personas with custom prompts
- **File Management Tools**: Read, edit, create, list, and search files
- **Safe Editing**: Automatic backups before file modifications with rollback capability
- **Agent Delegation**: Personalities can delegate tasks to other personalities
- **Interactive CLI**: Rich terminal UI with conversation history and command support

## Prerequisites

- [Python](https://www.python.org/) 3.13 or higher
- [`uv`](https://docs.astral.sh/uv/) package manager
- An LLM provider (Ollama, OpenAI, Anthropic, etc.)

## Quick Start

Agent C defaults to running with Ollama and the `gpt-oss:120b-cloud` model.

### 1. Install Ollama (for local inference)

- Download and install [Ollama](https://ollama.com/)
- Sign in: `ollama signin` (creates account if needed)
- Pull model: `ollama pull gpt-oss:120b-cloud`
- Start Ollama: `ollama serve`

### 2. Install uv

Install [`uv`](https://docs.astral.sh/uv/) using the standalone installer for your OS.

### 3. Run Agent C

```bash
uvx git+https://github.com/badlydrawnrod/agent-c
```

Type commands or questions. Exit with "quit" or "exit".

For other providers (OpenAI, Anthropic), see **Configuration** below.

## Installation

### For Development

```bash
git clone https://github.com/badlydrawnrod/agent-c.git
cd agent-c
uv sync
```

## Configuration

Agent C uses three TOML configuration files (located in `src/agentc/`):

- **`providers.toml`**: Built-in list of supported LLM providers
- **`personalities.toml`**: Define agent personalities with custom prompts and provider mappings
- **`config.toml`**: Override default settings per provider (API keys, models, etc.)

### Setting API Keys

For providers requiring API keys (Anthropic, OpenAI):

```bash
# Windows (Command Prompt)
set ANTHROPIC_API_KEY=your_key

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = 'your_key'

# Linux/macOS
export ANTHROPIC_API_KEY=your_key
```

Ollama requires no API key but must be running locally.

## Running the Agent

### Basic Usage

```bash
uv run agent-c --personality coder
```

### Available Personalities

- `coder` (default): Assists with code development and editing
- `reviewer`: Code review and analysis
- `debugger`: Debugging and troubleshooting

### Override the Model

```bash
uv run agent-c --personality reviewer --model gpt-4
```

### Override the Provider

```bash
uv run agent-c --personality coder --provider anthropic
```

Available providers: `anthropic`, `google`, `huggingface`, `mistral`, `ollama`, `openai`

### Run Without Installing

```bash
uvx --from . agent-c --personality coder
```

### Interactive Commands

While in the agent, type:
- `/clear` or `/reset`: Clear conversation history
- `/personality <name>`: Switch to a different personality
- `/quit` or `/exit`: Exit the agent

## Tools

Agent C provides these tools to assist with coding tasks:

- **read_file**: Read file contents
- **list_files**: List directory contents
- **edit_file**: Modify file contents with safety backups
- **create_file**: Create new files (creates parent directories if needed)
- **search_files**: Search for text in files recursively
- **list_backups**: List available backups for a file
- **restore_backup**: Restore a file from a timestamped backup
- **delegate_to_agent**: Delegate tasks to other personalities

## Project Structure

```
src/agentc/
├── agent.py              # Entry point and event loop
├── config.toml           # User configuration overrides
├── personalities.toml    # Personality definitions
├── providers.toml        # LLM provider definitions
├── prompts/              # System prompts for each personality
│   ├── coder.md
│   ├── reviewer.md
│   └── debugger.md
├── core/
│   ├── agent_factory.py  # Agent creation and configuration
│   ├── config.py         # Configuration loading
│   ├── file_ops.py       # File operations with backup/restore
│   ├── tools.py          # Tool definitions
│   ├── types.py          # Type definitions
│   └── __init__.py       # Core exports
└── ui/
    ├── console.py        # Terminal UI with Rich library
    ├── protocol.py       # UI protocol definitions
    └── __init__.py
```

## Development

### Run Tests

```bash
uv run pytest
```

### Type Checking

```bash
uv run mypy
```

### Linting and Formatting

```bash
uv run ruff check
uv run ruff format
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
