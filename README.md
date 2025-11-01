# Agent C

A simple code editing assistant powered by [Pydantic AI](https://ai.pydantic.dev/), supporting multiple LLM providers and delegation to sub-agents. This agent provides tools for reading, listing, editing, searching, and creating files to help with code-related tasks.

Hugely inspired by [How to Build an Agent](https://ampcode.com/how-to-build-an-agent) by Thorsten Ball of [AmpCode](https://ampcode.com/).

## Quick Start

Agent C defaults to running locally using Ollama and `gpt-oss:20b`.

- Install [Ollama](https://ollama.com/) then download and serve `gpt-oss:20b`
- Install [`uv`](https://docs.astral.sh/uv/)
- Run `uvx git+https://github.com/badlydrawnrod/agent-c`

## Prerequisites

- [Python](https://www.python.org/) 3.13 or higher
- [`uv`](https://docs.astral.sh/uv/) package manager

## Installation

### Windows

1. Install `uv` using the standalone installer:
   ```
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Clone or download the project and navigate to the directory.

3. Install dependencies:
   ```
   uv sync
   ```

### Linux

1. Install `uv` using the standalone installer:
   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Clone or download the project and navigate to the directory.

3. Install dependencies:
   ```
   uv sync
   ```

## Configuration

The agent is configured using three [TOML](https://toml.io/) files:

- `providers.toml`: This file contains the master list of all supported LLM providers and their default settings. You generally won't need to edit this file.
- `config.toml`: This file is where you can override the default settings for each provider. For example, you can specify a different model to use for a particular provider.
- `personalities.toml`: This file defines different personalities for the agent, each with its own system prompt and potentially different provider/model settings. Personalities allow the agent to adopt different roles, such as a code reviewer or debugger.

To use a specific provider, you'll need to set the appropriate API key as an environment variable. The required environment variable for each provider is listed in `providers.toml`.

## Running the Agent

1. Set the appropriate API key environment variable based on the provider you want to use (see Configuration section). For example:
- Windows (command prompt): `set ANTHROPIC_API_KEY=your_api_key_here`
- Windows (PowerShell): `$env:ANTHROPIC_API_KEY = 'your_api_key_here'`
- Linux / Mac: `export ANTHROPIC_API_KEY=your_api_key_here`

For [Ollama](https://ollama.com/), no API key is needed, but ensure Ollama is running locally.

2. Run the agent with the desired personality:
```
uv run agentc --personality coder
```

Available personalities: coder, reviewer, debugger (default: coder).

Optionally override the model:
```
uv run agentc --personality reviewer --model gpt-4
```

Alternatively, run directly with [uvx](https://docs.astral.sh/uv/concepts/tools/) without installing dependencies:
```
uvx --from . agentc --personality coder
```

3. Interact with the agent by typing commands or questions. Type "quit" or "exit" to end the session.

## Development

To run tests or use development tools:

```
uv run [pytest](https://pytest.org/)
uv run [mypy](https://mypy-lang.org/)
uv run [ruff](https://ruff.rs/)
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
