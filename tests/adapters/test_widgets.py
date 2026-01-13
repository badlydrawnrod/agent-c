import pytest
from textual.app import App

from agentc.ui.widgets import CommandSuggestions, compute_suggestions


class _SuggestionTestApp(App[None]):
    def compose(self):
        yield CommandSuggestions(id="suggestions")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_compute_suggestions_returns_commands_for_slash() -> None:
    suggestions, mode = compute_suggestions("/he", ["alpha"])
    assert mode == "command"
    commands = [
        suggestion["command"]
        for suggestion in suggestions
        if isinstance(suggestion, dict)
    ]
    assert "/help" in commands


def test_compute_suggestions_model_empty_prefix_lists_all() -> None:
    model_names = ["claude-sonnet", "ollama-gpt-oss-120b"]
    suggestions, mode = compute_suggestions("/model ", model_names)
    assert mode == "model"
    assert suggestions == model_names


def test_compute_suggestions_model_prefix_case_insensitive() -> None:
    model_names = ["claude-sonnet", "ollama-gpt-oss-120b"]
    suggestions, mode = compute_suggestions("/model CL", model_names)
    assert mode == "model"
    assert suggestions == ["claude-sonnet"]


@pytest.mark.anyio("asyncio")
async def test_command_suggestions_selected_command_handles_models() -> None:
    app = _SuggestionTestApp()
    async with app.run_test() as pilot:  # noqa: F841
        widget = app.query_one(CommandSuggestions)
        widget.set_model_names(["alpha", "beta"])
        widget.set_suggestions(["beta"], mode="model")
        assert widget.selected_command == "/model beta"
        widget.set_suggestions(
            [
                {
                    "command": "/clear",
                    "description": "Clear conversation history",
                },
            ],
            mode="command",
        )
        assert widget.selected_command == "/clear"
