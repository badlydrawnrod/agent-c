# AgentC Next Generation

Layered, event-driven implementation of AgentC that keeps agent logic, middleware, adapters, and UIs decoupled while sharing a common toolset and skills library.

## What lives here
- **`core/`**: `AgentSession` wraps the `pydantic_ai` agent and maps streaming events into agnostic `AgentEvent` types (`AgentChunk`, `ToolCallInfo`, `ToolCallResultInfo`, `ApprovalRequest`, `AgentDone`). `factory.py` builds the agent with tools, skill discovery, and the Ollama-backed model (`gpt-oss:20b` at `http://localhost:11434/v1`). `tool_parsing.py` normalizes tool args; `skill_loader.py` discovers `SKILL.md` skills; `config.py` centralizes limits and suffixes.
- **`middleware/`**: `DebouncingMiddleware` buffers short text/thinking deltas while passing tool calls, approvals, and results through untouched.
- **`adapters/`**: Translate `AgentEvent` into UI-specific messages. `textual.py` posts Textual `Message` subclasses; `console.py` dispatches callback-based console events. Each preserves the async approval handshake.
- **`ui/`**: Entry points and UI code. `run_textual.py` launches `TextualAgentApp`; `run_console.py` demonstrates the console adapter with a sample prompt and auto-approval flow.

## Event flow
1. `AgentSession.run()` streams pydantic_ai events using the current history and optional deferred tool approvals.
2. Core maps pydantic_ai parts into `AgentEvent` items, including tool call results so UIs can display execution outcomes.
3. `DebouncingMiddleware` aggregates small text/thinking deltas based on a configurable threshold (default 40 chars).
4. Adapters consume the debounced stream, convert events to UI messages/callback events, and perform the approval handshake by sending an `ApprovalResponse` back into the generator.

## Tools and constraints
- `list_files`, `glob_paths`, `search_files`, `read_file`, `edit_file` (approval), `run_command` (approval).
- Paths are resolved relative to the current working directory; attempts to escape raise `ModelRetry`.
- `read_file` returns `cat -n` style output; `edit_file` enforces a single match, writes atomically, and creates timestamped backups (`.bak`).
- `glob_paths` and `search_files` respect combined ignore patterns (centralized defaults like `.git/` plus local `.gitignore` rules) and cap output at `MAX_TOOL_OUTPUT_LINES` (200).
- `run_command` uses asyncio subprocess execution and returns combined stdout/stderr.

## Skills library
`SkillLoader` scans `.github/skills` and `.claude/skills` (configurable) for `SKILL.md` descriptors. `create_agent` injects a table of discovered skills into the system prompt, with guidance to `cd` into the skill base directory before running documented commands.

## Defaults and configuration
- Model: `OpenAIChatModel` with `OllamaProvider`, model `gpt-oss:20b`, base URL `http://localhost:11434/v1`.
- Config: `MAX_TOOL_OUTPUT_LINES=200`, `BACKUP_SUFFIX=.bak`, `TEMP_SUFFIX=.tmp`, default skill dirs `.github/skills` and `.claude/skills`.
- Default ignore patterns: `.git/`, `__pycache__/`, `*.pyc`, `.venv/`, `node_modules/`, `.DS_Store`.
- System prompt encourages succinct, ASCII-first responses and leans on the skills table for specialized workflows.

## Running
```powershell
# Textual UI
uv run run-textual

# Console UI demo (auto-approves tool calls for the sample prompt)
uv run run-console
```
