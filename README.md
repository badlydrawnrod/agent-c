# Agent C

A simple code editing assistant powered by [Pydantic AI](https://ai.pydantic.dev/), supporting multiple LLM providers and delegation to sub-agents. This agent provides tools for reading, listing, editing, searching, and creating files to help with code-related tasks.

Hugely inspired by [How to Build an Agent](https://ampcode.com/how-to-build-an-agent) by Thorsten Ball of [AmpCode](https://ampcode.com/).

## Prerequisites

- [Python](https://www.python.org/) 3.13 or higher
- [`uv`](https://docs.astral.sh/uv/) package manager

## Quick Start

Agent C defaults to running with [Ollama](https://ollama.com/) and the `gpt-oss:120b-cloud` model.

1. **Install Ollama**:
   - Download and install [Ollama](https://ollama.com/).
   - Sign in: `ollama signin` (this will prompt you to create an account if you don't have one)
   - Pull the model: `ollama pull gpt-oss:120b-cloud`
   - Start Ollama: `ollama serve`

2. **Install uv**:
   - Install [`uv`](https://docs.astral.sh/uv/) using the standalone installer for your OS.

3. **Run Agent C**:
   - Run: `uvx git+https://github.com/badlydrawnrod/agent-c`
   - Interact with the agent by typing commands or questions. Type "quit" or "exit" to end.

For other providers (e.g., OpenAI, Anthropic), see Configuration below.

## Installation

### For Development or Custom Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/badlydrawnrod/agent-c.git
   cd agent-c
   ```
2. Install [`uv`](https://docs.astral.sh/uv/):

   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Linux/macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`

3. Install dependencies:

   - Run: `uv sync`

## Configuration

The agent uses three TOML files for configuration:

- `providers.toml`: Master list of supported LLM providers (usually no need to edit).
- `config.toml`: Override default settings for providers (e.g., change models).
- `personalities.toml`: Define agent personalities with custom prompts and settings (e.g., coder, reviewer, debugger).

To use providers requiring API keys (like Anthropic or OpenAI), set environment variables:
- Windows (Command Prompt): `set ANTHROPIC_API_KEY=your_key`
- Windows (PowerShell): `$env:ANTHROPIC_API_KEY = 'your_key'`
- Linux/macOS: `export ANTHROPIC_API_KEY=your_key`

Ollama requires no API key but must be running locally.

## Running the Agent

Run the agent with:
```bash
uv run agent-c --personality coder
```

Available personalities: `coder` (default), `reviewer`, `debugger`.

Override the model:
```bash
uv run agent-c --personality reviewer --model gpt-4
```

Run without installing (using uvx):
```bash
uvx --from . agent-c --personality coder
```

Interact by typing commands or questions. Exit with "quit" or "exit".

## Development

Run tests and linting:
```bash
uv run pytest
uv run mypy
uv run ruff
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
