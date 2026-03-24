# Agent C

A modern code editing assistant powered by [Pydantic AI](https://ai.pydantic.dev/) or the [GitHub Copilot SDK](https://github.com/github/copilot-sdk), featuring an event-driven architecture with skills-based prompting, multiple LLM provider support, and a rich Textual TUI.

Hugely inspired by [How to Build an Agent](https://ampcode.com/how-to-build-an-agent) by Thorsten Ball of [AmpCode](https://ampcode.com/).

Agent C uses a layered, event-driven architecture with pluggable backends - see [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design and diagrams.

## Features

- **Event-Driven Architecture**: Layered design with core logic, middleware, adapters, and UI separation
- **Skills-Based System**: Discoverable `SKILL.md` files from project and home directory
- **Rich TUI**: Modern Textual interface with debounced streaming and approval workflows
- **Multiple LLM Providers**: Support for Ollama, Anthropic Claude, OpenAI GPT, and others
- **File Management Tools**: Read, edit, create, list, and search files with combined `.gitignore` support
- **Safe Editing**: Automatic backups before file modifications with rollback capability
- **Interactive CLI**: Rich terminal UI with conversation history and command support

## Prerequisites

- [Python](https://www.python.org/) 3.13 or higher (note: `uv sync` will install it if necessary)
- [`uv`](https://docs.astral.sh/uv/) package manager
- An LLM provider (Ollama, OpenAI, Anthropic, etc.)

## Quick Start

Agent C defaults to running with Ollama and the `ollama-gpt-oss-120b` model preset.

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

Type commands or questions. Exit with "/quit" or "/exit".

For other providers (OpenAI, Anthropic), see **Configuration** below.

### 4. Run in Docker (optional)

```bash
docker compose up --build
```

This runs the Textual UI in the container. The compose file sets `OLLAMA_HOST` to
`http://host.docker.internal:11434/v1` so the container can reach a host Ollama.
Override it if your Ollama host runs elsewhere.

## Installation

### For Development

```bash
git clone https://github.com/badlydrawnrod/agent-c.git
cd agent-c
uv sync
```

## Configuration

Agent C uses a single TOML configuration file (located in `src/agentc/`):

- **`providers.toml`**: Configure backends and model presets (Ollama, Anthropic, OpenAI, etc.)

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

### Custom Backends and Models

Agent C supports custom backend/model configurations via `providers.toml` files discovered in priority order:

1. **Repo-local**: `.agentc/providers.toml` (highest priority)
2. **User-global**: `~/.agentc/providers.toml`
3. **Bundled**: `src/agentc/providers.toml` (lowest priority)

Providers discovered earlier override those with the same name in later locations.

#### Example Custom Backend + Model

Create `.agentc/providers.toml` in your project or `~/.agentc/providers.toml` in your home directory:

```toml
[backends.my-custom-ollama]
provider_cls = "pydantic_ai.providers.ollama.OllamaProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
base_url_env = "OLLAMA_HOST"
base_url = "http://localhost:11434/v1"

[backends.openai]
provider_cls = "pydantic_ai.providers.openai.OpenAIProvider"
model_cls = "pydantic_ai.models.openai.OpenAIChatModel"
api_key_env = "OPENAI_API_KEY"

[models.local-dev]
backend = "my-custom-ollama"
model_name = "deepseek-r1:32b"
params = {temperature = 0.2}

[models.gpt-4o]
backend = "openai"
model_name = "gpt-4o"
```

- `provider_cls`: Full Python path to the provider class
- `model_cls`: Full Python path to the model class
- `model_name`: Model identifier (e.g., `gpt-4o`, `deepseek-r1:32b`)
- `api_key_env`: (Optional) Environment variable name for API key
- `base_url_env`: (Optional) Environment variable name for base URL overrides
- `base_url`: (Optional) Custom base URL for the backend
- `params`: (Optional) Keyword arguments forwarded to the model constructor (e.g., `temperature`)

Switch to your custom model preset:
```
/model local-dev
```

## Running the Agent

### Basic Usage (Textual TUI)

```bash
uv run agent-c
```

### Console UI

```bash
uv run run-console
```

### GitHub Copilot SDK Backend

```bash
uv run run-textual-gh
```

Requires the Copilot CLI to be installed and available in PATH.

### Override the Model Preset

Use the `/model` command within the agent:
```
/model claude-sonnet
```

Available presets (bundled): `ollama-gpt-oss-120b`, `ollama-gpt-oss-20b`, `ollama-kimi-k2-5`, `ollama-glm-4-7`, `gpt-4o-mini`, `claude-sonnet`, `gemini3-flash`, `hf-gpt-oss-120b`, `mistral-large`

### Run Without Installing

```bash
uvx --from . agent-c
```

### Interactive Commands

While in the agent, type:
- `/clear` or `/reset`: Clear conversation history
- `/model <name>`: Switch to a different model preset
- `/quit` or `/exit`: Exit the agent

## Skills System

Agent C uses a skills-based approach where skills are discovered from:
- Bundled skills: Installed to `~/.local/share/agentc/skills/` (or platform-equivalent user data directory)
- Project directories: `.github/skills/` and `.claude/skills/`

Each skill is a subdirectory containing a `SKILL.md` file with metadata and usage instructions. Skills are injected into the system prompt as a table, allowing the agent to understand available capabilities.

## Tools

Agent C provides these tools to assist with coding tasks:

- **list_files**: List directory contents
- **glob_paths**: Find files matching glob patterns
- **search_files**: Search for text in files recursively
- **read_file**: Read file contents with line numbers
- **create_file**: Create new files (creates parent directories if needed)
- **edit_file**: Replace a single occurrence in a file with safety backups
- **apply_hunks**: Apply multiple structured edits to one or more files atomically
  - Supports multiple non-contiguous edits in the same file
  - Atomic transactions: all hunks must succeed or no files are modified
  - Anchor-based matching with context lines for precision
  - Automatic backups and rollback on failure
- **run_command**: Execute shell commands asynchronously

### File Editing Strategy

The agent uses a smart editing strategy:
- **Single edit**: Use `edit_file` for one isolated change
- **Multiple edits**: Use `apply_hunks` for 2+ changes to the same file (more efficient and atomic)
- **New files**: Use `create_file` for files that don't exist

## Project Structure

```
└── src/
    └── agentc/               # Main Implementation
        ├── core/             # Agnostic agent logic
        │   ├── backends/     # Backend implementations
        │   │   ├── pydantic_ai/   # Pydantic AI backend (factory, loop, tools)
        │   │   └── github_copilot/ # GitHub Copilot SDK backend
        │   └── patching/     # Structured file patching engine
        ├── middleware/       # Cross-cutting concerns (debouncing)
        ├── adapters/         # UI framework bridges
        ├── entrypoints/      # Application composition roots
        ├── ui/               # User interfaces (Textual, Console)
        └── providers.toml    # Provider configuration
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

## Contributing

We welcome contributions. However, all contributors must follow the strict architectural and coding rules in [AGENTS.md](AGENTS.md).

Before contributing:
- Review the system design in [ARCHITECTURE.md](ARCHITECTURE.md)
- Follow the development rules in [AGENTS.md](AGENTS.md)

These rules ensure:
- Code quality and consistency
- Type safety (MyPy strict mode)
- Architectural integrity (layered design)
- Test coverage and reliability

Key guidelines:
- State which layers you're modifying before making changes
- Add full type annotations and docstrings to all public functions
- Maintain test coverage for all changes
- Run `ruff check`, `mypy`, and `pytest` before submitting

See [AGENTS.md](AGENTS.md) for complete development rules and [ARCHITECTURE.md](ARCHITECTURE.md) for system design details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.