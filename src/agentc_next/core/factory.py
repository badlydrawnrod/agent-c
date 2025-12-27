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

from .tools import list_files, read_file, edit_file
from .types import RunDeps, NextAgent


def create_agent() -> NextAgent:
    """Factory function to create a configured agent instance."""
    model = OpenAIChatModel(
        provider=OllamaProvider(base_url="http://localhost:11434/v1"),
        model_name="gpt-oss:20b",
    )

    tools: list[Tool[RunDeps]] = [
        Tool(list_files, takes_ctx=True),
        Tool(read_file, takes_ctx=True),
        Tool(edit_file, takes_ctx=True, requires_approval=True),
    ]

    return Agent(
        model=model,
        tools=tools,
        deps_type=RunDeps,
        output_type=Union[str, DeferredToolRequests],  # type: ignore
        system_prompt="""\
You are a helpful coding assistant that helps users edit code files. You have access to tools to
read and edit files. Use tools only when needed.

## Output requirements
Be succinct but informative in your responses. When providing code snippets, format them using
Markdown with appropriate syntax highlighting. Always ensure your final response is valid.

By default, ensure all output uses ASCII encoding. Only introduce non-ASCII or Unicode characters
if there is a compelling reason such as the file already containing them or a domain-specific need,
and clearly explain why.
""",
    )


__all__ = [
    "create_agent",
]
