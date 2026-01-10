"""
Agent factory for Agent C Next.

This module assembles the agent using tools from `tools.py` and types from `types.py`.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any, Union

from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    Tool,
)

from .config import DEFAULT_MODEL
from .tools import (
    list_files,
    glob_paths,
    search_files,
    read_file,
    edit_file,
    create_file,
    run_command,
)
from .skill_loader import SkillLoader
from .types import RunDeps, NextAgent
from .provider_loader import load_providers, build_model



def create_agent(
    skill_dirs: list[Path] | None = None,
    model_name: str | None = None,
    override_model_name: str | None = None,
    **model_params: Any,
) -> NextAgent:
    """Factory function to create a configured agent instance.

    Args:
        skill_dirs: Optional skill directories to include during skill discovery.
        model_name: Name of the model preset to load from providers.toml.
        override_model_name: Runtime override for the model string passed to the backend.
        **model_params: Extra model keyword arguments merged with preset params.
    """
    loader = SkillLoader()
    if skill_dirs is None:
        skill_dirs = loader.get_default_skill_dirs()

    backends, models = load_providers()
    preset_name = model_name or DEFAULT_MODEL
    if preset_name not in models:
        raise ValueError(
            f"Unknown model preset: {preset_name}. Available models: {list(models.keys())}"
        )

    preset = models[preset_name]
    backend = backends.get(preset.backend)
    if backend is None:
        raise ValueError(
            f"Backend '{preset.backend}' for model preset '{preset_name}' was not found"
        )

    merged_params = {**preset.params, **model_params}
    effective_model = replace(
        preset,
        model_name=override_model_name or preset.model_name,
        params=merged_params,
    )

    _, model = build_model(effective_model, backend)

    tools: list[Tool[RunDeps]] = [
        Tool(list_files, takes_ctx=True),
        Tool(glob_paths, takes_ctx=True),
        Tool(search_files, takes_ctx=True),
        Tool(read_file, takes_ctx=True),
        Tool(create_file, takes_ctx=True, requires_approval=True),
        Tool(edit_file, takes_ctx=True, requires_approval=True),
        Tool(run_command, takes_ctx=True, requires_approval=True),
    ]

    # Dynamically load skills
    discovered_skills = loader.discover_skills(skill_dirs)
    skills_summary = loader.get_skills_summary(discovered_skills)

    return Agent(
        model=model,
        tools=tools,
        deps_type=RunDeps,
        output_type=Union[str, DeferredToolRequests],  # type: ignore
        system_prompt=f"""\
You are an expert coding assistant with comprehensive file system access and command execution capabilities. You help users navigate, analyze, edit, and manage their codebase efficiently.

## Tool Usage Strategy
- **Verify before acting**: Always use tools to check file contents or state before modifying
- **Discover first**: Use `list_files` or `glob_paths` to find relevant files
- **Search when needed**: Use `search_files` to locate specific patterns across the codebase
- **Understand context**: Use `read_file` to understand code before making changes
- **Follow the chain**: discover → read → analyze → edit/execute

## Communication Guidelines
- **Be succinct but informative**: Provide clear, actionable responses
- **Use markdown**: Format code snippets with appropriate syntax highlighting
- **Ask when uncertain**: If a request is ambiguous, ask clarifying questions before acting
- **Explain errors**: When things go wrong, explain the issue and suggest alternatives
- **Summarize changes**: After modifications, clearly state what was changed and why
- **Warn about risks**: If uncertain about a change's impact, warn the user explicitly

## Output Encoding
By default, use ASCII encoding. Only introduce non-ASCII or Unicode characters if:
- The file already contains them
- There's a domain-specific need (e.g., internationalization, mathematical notation)
Always explain why non-ASCII characters are necessary.

## Agent Skills Library
{skills_summary}

## Success Criteria
- All requested changes are correctly implemented
- Changes align with existing code style and patterns  
- No syntax errors or regressions are introduced
- User's intent is fully addressed
""",
    )


__all__ = [
    "create_agent",
]
