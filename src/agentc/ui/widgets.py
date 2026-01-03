"""
Reusable widgets for the Agent C Next Textual UI.

Contains the status bar, tool call indicators, approval requests,
and the history-enabled text area.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static, TextArea

from ..adapters.textual_messages import AgentApprovalRequestMessage

__all__ = [
    "StatusBar",
    "ApprovalWidget",
    "ToolCallWidget",
    "HistoryTextArea",
]

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

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._animation_frame = 0
        self._animation_timer = None
        self._current_message = ""

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

    def __init__(self, tool_call_id: str, tool_name: str, args: dict, **kwargs):
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


class HistoryTextArea(TextArea):
    """TextArea with command history support."""

    BINDINGS = [
        ("up", "history_up", "History Up"),
        ("down", "history_down", "History Down"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command_history: list[str] = []
        self.history_index: int | None = None
        self.current_draft: str = ""

    def action_history_up(self) -> None:
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
