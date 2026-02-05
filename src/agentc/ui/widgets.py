"""
Reusable widgets for the Agent C Next Textual UI.

Contains the status bar, tool call indicators, approval requests,
and the history-enabled text area.
"""

from typing import Any, Literal, TypeAlias, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Button, Static, TextArea

from ..adapters.textual_messages import (
    AgentApprovalRequestMessage,
    AgentUserInputRequestMessage,
)
from ..core.commands import COMMAND_METADATA

__all__ = [
    "StatusBar",
    "ApprovalWidget",
    "AskUserWidget",
    "ToolCallWidget",
    "HistoryTextArea",
    "CommandSuggestions",
    "compute_suggestions",
]

CommandSuggestion: TypeAlias = dict[str, str] | str
SuggestionMode = Literal["command", "model"]


def _filter_models(prefix: str, model_names: list[str]) -> list[CommandSuggestion]:
    """Filter model names by prefix (case-insensitive)."""
    prefix_lower = prefix.lower()
    if not prefix_lower:
        return list(model_names)
    return [name for name in model_names if name.lower().startswith(prefix_lower)]


def compute_suggestions(
    text: str, model_names: list[str]
) -> tuple[list[CommandSuggestion], SuggestionMode]:
    """Compute suggestions for the given input text.

    Returns model suggestions when the input starts with `/model `, otherwise
    returns command suggestions. Newlines disable suggestions.
    """
    if not text.startswith("/") or "\n" in text:
        return [], "command"

    lower_text = text.lower()
    if lower_text.startswith("/model "):
        model_prefix = text[len("/model ") :]
        return _filter_models(model_prefix, model_names), "model"

    prefix = lower_text
    matches: list[CommandSuggestion] = [
        cmd
        for cmd in COMMAND_METADATA
        if cmd["command"].startswith(prefix)
        or any(alias.startswith(prefix) for alias in cmd.get("aliases", "").split(", "))
    ]
    return matches, "command"


# UI Animation constants
SPINNER_FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
SPINNER_INTERVAL: float = 0.1


class StatusBar(Static):
    """A status bar widget that shows agent state with an animated indicator."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
        text-style: italic;
        display: none;
    }
    StatusBar.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._animation_frame: int = 0
        self._animation_timer: Timer | None = None
        self._current_message: str = ""

    def set_status(self, message: str, animate: bool = True) -> None:
        self._current_message = message
        if animate:
            self._start_animation()
        else:
            self._stop_animation()
            self.update(message)

    def clear_status(self) -> None:
        self._stop_animation()
        self._current_message = ""
        self.update("")
        self.remove_class("visible")

    def _start_animation(self) -> None:
        self.add_class("visible")
        self._animation_frame = 0
        if self._animation_timer is None:
            self._animation_timer = self.set_interval(
                SPINNER_INTERVAL, self._update_animation
            )

    def _stop_animation(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None

    def _update_animation(self) -> None:
        self._animation_frame = (self._animation_frame + 1) % len(SPINNER_FRAMES)
        self.update(f"{SPINNER_FRAMES[self._animation_frame]} {self._current_message}")


class ApprovalWidget(Static):
    """Widget to display and handle tool approval requests."""

    DEFAULT_CSS = """
    ApprovalWidget {
        border: solid $accent;
        background: $boost;
        height: auto;
    }
    ApprovalWidget.status-success {
        border: solid $success;
    }
    ApprovalWidget.status-error {
        border: solid $error;
    }
    .request-container {
        border: solid $primary;
        padding: 0 1;
        height: auto;
    }
    .approval-args {
        color: $text-muted;
    }
    .button-container {
        height: auto;
        width: 100%;
        align: right middle;
    }
    Button {
        height: auto;
        min-height: 1;
        margin-right: 1;
        min-width: 12;
    }
    """

    def __init__(self, request: AgentApprovalRequestMessage, **kwargs):
        super().__init__(**kwargs)
        self._request = request
        self.border_title = "Tool Approval Request"

    def on_mount(self) -> None:
        self.query_one("#approve").focus()

    def compose(self) -> ComposeResult:
        for call in self._request.tool_calls:
            with VerticalScroll(classes="request-container") as vs:
                vs.border_title = f"Tool: {call.tool_name}"
                if isinstance(call.args, dict):
                    args_str = "\n".join(f"{k}: {v}" for k, v in call.args.items())
                else:
                    args_str = str(call.args)
                yield Static(f"Args:\n{args_str}", classes="approval-args")

        with Horizontal(classes="button-container"):
            yield Button("Approve", id="approve", variant="success", compact=True)
            yield Button("Deny", id="deny", variant="error", compact=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        is_approved = event.button.id == "approve"
        self._request.resolve(is_approved)
        self._update_ui_post_decision(is_approved)

    def _update_ui_post_decision(self, is_approved: bool) -> None:
        self.query_one(Horizontal).remove()

        self.remove_class("status-success")
        self.remove_class("status-error")

        if is_approved:
            self.add_class("status-success")
            self.border_title = "Tool Request Approved"
        else:
            self.add_class("status-error")
            self.border_title = "Tool Request Denied"


class AskUserWidget(Static):
    """Widget to display and handle user input requests."""

    DEFAULT_CSS = """
    AskUserWidget {
        border: solid $accent;
        background: $boost;
        height: auto;
        padding: 0 1;
    }
    AskUserWidget.status-submitted {
        border: solid $success;
    }
    .question-text {
        padding: 0 0 1 0;
    }
    .option-container {
        height: auto;
        padding: 0 0 1 0;
    }
    .option-description {
        color: $text-muted;
        padding-left: 1;
    }
    .freeform-container {
        height: auto;
        padding: 1 0 0 0;
    }
    #user-input {
        height: 3;
    }
    """

    def __init__(self, request: AgentUserInputRequestMessage, **kwargs) -> None:
        super().__init__(**kwargs)
        self._request = request
        self.border_title = "User Input Requested"

    def on_mount(self) -> None:
        first_button = self.query(Button).first()
        if first_button is not None:
            first_button.focus()

    def compose(self) -> ComposeResult:
        yield Static(self._request.request.question, classes="question-text")

        for index, option in enumerate(self._request.request.options):
            with Vertical(classes="option-container"):
                yield Button(option.label, id=f"option-{index}", variant="primary")
                if option.description:
                    yield Static(option.description, classes="option-description")

        if self._request.request.allow_freeform:
            with Vertical(classes="freeform-container"):
                yield TextArea(
                    id="user-input",
                    placeholder=self._request.request.placeholder
                    or "Type a response",
                )
                yield Button("Submit", id="submit", variant="success", compact=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("option-"):
            try:
                index = int(button_id.split("-")[-1])
                option = self._request.request.options[index]
            except (ValueError, IndexError):
                return
            self._finalize(option.label)
            return

        if button_id == "submit":
            response = self._get_freeform_response()
            if response is None:
                return
            self._finalize(response)

    def _get_freeform_response(self) -> str | None:
        if not self._request.request.allow_freeform:
            return None
        input_field = self.query_one("#user-input", TextArea)
        text = input_field.text.strip()
        if not text:
            return None
        return text

    def _finalize(self, response: str) -> None:
        self._request.resolve(response)
        for button in self.query(Button):
            button.disabled = True
        if self._request.request.allow_freeform:
            input_field = self.query_one("#user-input", TextArea)
            input_field.disabled = True
        self.add_class("status-submitted")
        self.border_title = "User Input Submitted"


class ToolCallWidget(Static):
    """Widget to display a tool call notification."""

    DEFAULT_CSS = """
    ToolCallWidget {
        border: solid $secondary;
        background: $boost;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }
    ToolCallWidget.status-success {
        border: solid $success;
    }
    ToolCallWidget.status-failure {
        border: solid $error;
    }
    .tool-args {
        color: $text-muted;
    }
    .tool-success {
        color: $success;
    }
    .tool-failure {
        color: $error;
    }
    """

    def __init__(
        self, tool_call_id: str, tool_name: str, args: dict[str, Any], **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.args = args
        self.border_title = f"Tool: {tool_name} ({tool_call_id})"

    def compose(self) -> ComposeResult:
        if self.args:
            args_str = "\n".join(f"{k}: {v}" for k, v in self.args.items())
            yield Static(args_str, classes="tool-args")
        else:
            yield Static("(no arguments)", classes="tool-args")

    def mark_success(self) -> None:
        """Mark the tool call as successful."""
        self.add_class("status-success")
        self.remove_class("status-failure")
        self.border_title = f"Tool: {self.tool_name} ✓"

    def mark_failure(self, error: str | None = None) -> None:
        """Mark the tool call as failed."""
        self.add_class("status-failure")
        self.remove_class("status-success")
        error_text = f" ({error})" if error else ""
        self.border_title = f"Tool: {self.tool_name} ✗{error_text}"


class CommandSuggestions(Static):
    """A floating suggestion list for commands with theme-aware styling."""

    DEFAULT_CSS = """
    CommandSuggestions {
        background: $surface;
        border: round $accent;
        height: auto;
        max-height: 12;
        overflow: auto;
        width: 100%;
        display: none;
        padding: 0 1;
        margin-bottom: 1;
    }
    CommandSuggestions.visible {
        display: block;
    }
    CommandSuggestions .suggestion-line {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    CommandSuggestions .suggestion-line.selected {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    CommandSuggestions .cmd-name {
        color: $primary;
        text-style: bold;
    }
    CommandSuggestions .cmd-desc {
        color: $text-muted;
    }
    CommandSuggestions .glyph {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, model_names: list[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_names: list[str] = model_names or []
        self.suggestions: list[CommandSuggestion] = []
        self.suggestion_mode: SuggestionMode = "command"
        self.selected_index: int = 0
        self.border_title = "Commands"

    def set_model_names(self, model_names: list[str]) -> None:
        """Replace the list of model names used for autocomplete."""
        self.model_names = model_names

    def set_suggestions(
        self, suggestions: list[CommandSuggestion], mode: SuggestionMode = "command"
    ) -> None:
        """Update visible suggestions and presentation mode."""
        self.suggestion_mode = mode
        self.border_title = "Models" if mode == "model" else "Commands"
        self.suggestions = suggestions
        self.selected_index = 0
        self._update_display()
        if suggestions:
            self.add_class("visible")
        else:
            self.remove_class("visible")

    def _update_display(self) -> None:
        if not self.suggestions:
            self.update("")
            return

        from rich.text import Text

        content = Text()
        for i, suggestion in enumerate(self.suggestions):
            is_selected = i == self.selected_index

            if self.suggestion_mode == "model":
                model_name = str(suggestion)
                glyph = "▸ " if is_selected else "  "
                content.append(glyph, style="bold" if is_selected else "dim")
                content.append(model_name, style="bold" if is_selected else "")
            else:
                cmd = cast(dict[str, str], suggestion)
                glyph = "▸ " if is_selected else "  "
                content.append(glyph, style="bold" if is_selected else "dim")
                content.append(cmd["command"], style="bold" if is_selected else "")
                content.append(
                    f"  {cmd['description']}", style="" if is_selected else "dim"
                )

            if i < len(self.suggestions) - 1:
                content.append("\n")

        self.update(content)

    def move_selection(self, delta: int) -> None:
        if not self.suggestions:
            return
        self.selected_index = (self.selected_index + delta) % len(self.suggestions)
        self._update_display()

    @property
    def selected_command(self) -> str | None:
        if not self.suggestions or not 0 <= self.selected_index < len(self.suggestions):
            return None

        if self.suggestion_mode == "model":
            suggestion = self.suggestions[self.selected_index]
            return f"/model {suggestion}"

        suggestion = cast(dict[str, str], self.suggestions[self.selected_index])
        return suggestion["command"]


class HistoryTextArea(TextArea):
    """TextArea with command history support and slash-command autocomplete."""

    class Submitted(Message):
        """Event message indicating that input has been submitted."""

        def __init__(self, sender: "HistoryTextArea") -> None:
            super().__init__()
            self.sender = sender

    BINDINGS = [
        ("ctrl+enter,esc+enter,ctrl+j", "submit_input", "Submit"),
        ("up", "history_up", "History Up"),
        ("down", "history_down", "History Down"),
        Binding("tab", "complete_command", "Complete", show=False),
        Binding("escape", "hide_suggestions", "Hide", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.command_history: list[str] = []
        self.history_index: int | None = None
        self.current_draft: str = ""
        self._suggestions_widget: CommandSuggestions | None = None

    def on_mount(self) -> None:
        # Try to find suggestions widget in parents or app
        self._suggestions_widget = self.app.query_one(
            "#suggestions", CommandSuggestions
        )

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if not self._suggestions_widget:
            return

        text = self.text
        suggestions, mode = compute_suggestions(
            text, self._suggestions_widget.model_names
        )
        self._suggestions_widget.set_suggestions(suggestions, mode=mode)

    def action_submit_input(self) -> None:
        # Prevent submitting if suggestions are visible
        if self._suggestions_widget and self._suggestions_widget.has_class("visible"):
            return
        self.post_message(self.Submitted(self))

    def action_complete_command(self) -> None:
        if self._suggestions_widget and self._suggestions_widget.has_class("visible"):
            cmd = self._suggestions_widget.selected_command
            if cmd:
                self.load_text(cmd + " ")
                self.move_cursor_to_end()
                self._suggestions_widget.set_suggestions([])
        else:
            # Fallback to default tab behavior if no suggestions
            self.insert("\t")

    def action_hide_suggestions(self) -> None:
        if self._suggestions_widget:
            self._suggestions_widget.set_suggestions([])

    def action_history_up(self) -> None:
        if self._suggestions_widget and self._suggestions_widget.has_class("visible"):
            self._suggestions_widget.move_selection(-1)
            return

        if self.cursor_location[0] == 0:
            if not self.command_history:
                return
            if self.history_index is None:
                self.current_draft = self.text
                self.history_index = len(self.command_history) - 1
            elif self.history_index > 0:
                self.history_index -= 1
            else:
                return
            self._load_history_entry()
        else:
            self.action_cursor_up()

    def action_history_down(self) -> None:
        if self._suggestions_widget and self._suggestions_widget.has_class("visible"):
            self._suggestions_widget.move_selection(1)
            return

        last_line_idx = self.document.line_count - 1
        if self.cursor_location[0] == last_line_idx:
            if self.history_index is None:
                return
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self._load_history_entry()
            else:
                self.history_index = None
                self.load_text(self.current_draft)
                self.move_cursor_to_end()
        else:
            self.action_cursor_down()

    def _load_history_entry(self) -> None:
        if self.history_index is not None and 0 <= self.history_index < len(
            self.command_history
        ):
            self.load_text(self.command_history[self.history_index])
            self.move_cursor_to_end()

    def move_cursor_to_end(self) -> None:
        row = self.document.line_count - 1
        if row >= 0:
            col = len(self.document.get_line(row))
            self.cursor_location = (row, col)

    def add_to_history(self, text: str) -> None:
        if text.strip():
            self.command_history.append(text)
        self.history_index = None
        self.current_draft = ""
