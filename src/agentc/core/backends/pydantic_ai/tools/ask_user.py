"""Ask-user tool for interactive prompts."""

from typing import Any

from pydantic_ai import ModelRetry

from ._shared import RunContext, RunDeps, ToolResult
from ....types import UserInputOption, UserInputRequest


def _parse_options(options: list[dict[str, Any]] | None) -> list[UserInputOption]:
    """Parse option dictionaries into UserInputOption instances."""
    if not options:
        return []

    parsed: list[UserInputOption] = []
    for option in options:
        if not isinstance(option, dict):
            raise ModelRetry("Each option must be an object with a 'label' field")
        label = option.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ModelRetry("Each option must include a non-empty 'label' field")
        description = option.get("description")
        if description is not None and not isinstance(description, str):
            raise ModelRetry("Option 'description' must be a string if provided")
        parsed.append(UserInputOption(label=label, description=description))

    return parsed


async def ask_user(
    ctx: RunContext[RunDeps],
    question: str,
    options: list[dict[str, Any]] | None = None,
    allow_freeform: bool = False,
    placeholder: str | None = None,
) -> ToolResult:
    """Ask the user a question and return the response text."""
    if not isinstance(question, str) or not question.strip():
        raise ModelRetry("Question must be a non-empty string")

    parsed_options = _parse_options(options)
    if not parsed_options and not allow_freeform:
        raise ModelRetry("Provide options or enable allow_freeform")

    handler = ctx.deps.user_input_handler
    if handler is None:
        return ToolResult(
            success=False,
            content="",
            error="User input handler is not configured for this session",
        )

    request = UserInputRequest(
        question=question,
        options=parsed_options,
        allow_freeform=allow_freeform,
        placeholder=placeholder,
    )
    response = await handler.request_user_input(request)
    return ToolResult(success=True, content=response.response)


__all__ = ["ask_user"]
