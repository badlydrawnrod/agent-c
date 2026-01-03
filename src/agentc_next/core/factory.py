"""
Agent factory for Agent C Next.

This module assembles the agent using tools from `tools.py` and types from `types.py`.
"""

from typing import Union

from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    Tool,
)

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from pathlib import Path
from .config import DEFAULT_SKILL_DIRS
from .tools import list_files, glob_paths, search_files, read_file, edit_file, run_command
from .skill_loader import SkillLoader
from .types import RunDeps, NextAgent


def create_agent(skill_dirs: list[Path] | None = None) -> NextAgent:
    """Factory function to create a configured agent instance."""
    if skill_dirs is None:
        skill_dirs = [Path(p) for p in DEFAULT_SKILL_DIRS]

    model = OpenAIChatModel(
        provider=OllamaProvider(base_url="http://localhost:11434/v1"),
        model_name="gpt-oss:20b",
    )

    tools: list[Tool[RunDeps]] = [
        Tool(list_files, takes_ctx=True),
        Tool(glob_paths, takes_ctx=True),
        Tool(search_files, takes_ctx=True),
        Tool(read_file, takes_ctx=True),
        Tool(edit_file, takes_ctx=True, requires_approval=True),
        Tool(run_command, takes_ctx=True, requires_approval=True),
    ]

    # Dynamically load skills
    loader = SkillLoader()
    discovered_skills = loader.discover_skills(skill_dirs)
    skills_summary = loader.get_skills_summary(discovered_skills)

    return Agent(
        model=model,
        tools=tools,
        deps_type=RunDeps,
        output_type=Union[str, DeferredToolRequests],  # type: ignore
        system_prompt=f"""\
You are a helpful coding assistant that helps users edit code files. You have access to tools to
read and edit files. Use tools only when needed.

## Output requirements
Be succinct but informative in your responses. When providing code snippets, format them using
Markdown with appropriate syntax highlighting. Always ensure your final response is valid.

By default, ensure all output uses ASCII encoding. Only introduce non-ASCII or Unicode characters
if there is a compelling reason such as the file already containing them or a domain-specific need,
and clearly explain why.

## Agent Skills Library
You have access to specialized skills documented in the repository. Before attempting a task
that seems specialized, check the library below.

**Workflow for Skills**:
1. Check the table for a relevant skill.
2. Use `read_file` with the provided "Documentation Path".
3. To execute the skill, you MUST typically `cd` into the "Base Directory" first, then run the command as described in the documentation.

**CRITICAL RULES**:
- **NO IMPROVISATION**: Use the provided skill scripts; do not write your own.
- **ALWAYS CD**: Most skills expect to be run from their own directory. Use `run_command` so the command runs only if `cd` succeeds:
  - POSIX / cmd.exe: `run_command(command="cd <Base Directory> && <command>")`
  - PowerShell: `run_command(command="Set-Location '<Base Directory>'; if ($?) {{command> }}")`
- **STRICT PATHS**: Do not guess file locations. Use the paths from the library table and the documentation.

{skills_summary}

Reasoning: high
""",
    )


__all__ = [
    "create_agent",
]
