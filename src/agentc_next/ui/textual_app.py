"""
Textual UI for Agent C Next: widgets and the `TextualAgentApp`.

Contains UI widgets, approval/tool-call components, and the
`TextualAgentApp` that mounts the Textual view, posts agent messages, and
manages background agent tasks and cancellation.
"""

import asyncio


from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Collapsible, Footer, Markdown, Static, TextArea

from ..adapters.textual_messages import (
    AgentApprovalRequestMessage,
    AgentCancelledMessage,
    AgentDoneMessage,
    AgentErrorMessage,
    AgentThinkingMessage,
    AgentTextMessage,
    AgentToolCallMessage,
)
from ..adapters.textual import TextualAgentAdapter
from ..core.types import AgentSessionProtocol


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
            self._animation_timer = self.set_interval(0.1, self._update_animation)

    def _stop_animation(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None

    def _update_animation(self) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._animation_frame = (self._animation_frame + 1) % len(frames)
        self.update(f"{frames[self._animation_frame]} {self._current_message}")


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
    .tool-args {
        color: $text-muted;
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


class TextualAgentApp(App):
    """Textual application with message-based agent event handling."""

    DEFAULT_CSS = """
    .thinking {
        color: $text-secondary;
        padding-right: 1;
        text-overflow: fold;
        text-style: italic;
        text-wrap: wrap;
    }
    .user {
        border: solid $primary;
        color: $text-primary;
        padding: 0 1;
        text-overflow: fold;
        text-wrap: wrap;
    }
    .error {
        color: $error;
        border: solid $error;
        padding: 0 1;
    }
    .cancelled {
        color: $warning;
        border: solid $warning;
        padding: 0 1;
    }
    #input {
        height: auto;
        min-height: 3;
        max-height: 7;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("ctrl+enter", "submit_input", "Submit"),
        ("ctrl+j", "submit_input", "Submit"),
        ("ctrl+s", "submit_input", "Submit"),
        ("escape", "cancel_operation", "Cancel"),
    ]

    def __init__(
        self,
        session: AgentSessionProtocol,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._session = session
        self._cancellation_event: asyncio.Event | None = None
        self._pending_tool_widgets: dict[str, ToolCallWidget] = {}

        self._scroll: VerticalScroll | None = None
        self._status_bar: StatusBar | None = None
        self._collapsible: Collapsible | None = None
        self._thinking_output: Static | None = None
        self._stream_writer: Any | None = None
        self._thinking_text = ""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="scroll"):
            pass
        yield StatusBar(id="status")
        input_widget = HistoryTextArea(
            placeholder="Type here (multi-line supported). Use Ctrl+Enter to submit.",
            id="input",
            language="markdown",
        )
        input_widget.focus()
        yield input_widget
        yield Footer()

    def action_submit_input(self) -> None:
        input_widget = self.query_one("#input", HistoryTextArea)
        user_text = input_widget.text.strip()

        if not user_text:
            return

        input_widget.add_to_history(user_text)
        input_widget.clear()
        input_widget.focus()
        self._cancellation_event = asyncio.Event()
        self.background_task(user_text)

    def action_cancel_operation(self) -> None:
        if self._cancellation_event is None:
            return
        if not self._cancellation_event.is_set():
            self._cancellation_event.set()
            if self._status_bar:
                self._status_bar.set_status("Cancelling...", animate=True)

    async def _create_output_widgets(
        self, scroll: VerticalScroll
    ) -> tuple[Static, Collapsible, Markdown]:
        thinking_output = Static(classes="thinking")
        thinking_output.border_title = "Thinking"
        thinking_output.display = True
        collapsible = Collapsible(thinking_output, collapsed=False, title="Thinking")
        collapsible.display = False
        await scroll.mount(collapsible)

        new_md = Markdown()
        await scroll.mount(new_md)

        return thinking_output, collapsible, new_md

    @on(AgentThinkingMessage)
    async def handle_thinking(self, message: AgentThinkingMessage) -> None:
        if self._status_bar:
            self._status_bar.set_status("Thinking...")
        if self._collapsible and not self._collapsible.display:
            self._collapsible.display = True
        self._thinking_text += message.text
        if self._thinking_output:
            self._thinking_output.update(self._thinking_text)

    @on(AgentTextMessage)
    async def handle_text(self, message: AgentTextMessage) -> None:
        if self._status_bar:
            self._status_bar.set_status("Responding...")
        if self._stream_writer:
            await self._stream_writer.write(message.text)

    @on(AgentToolCallMessage)
    async def handle_tool_call(self, message: AgentToolCallMessage) -> None:
        if self._status_bar:
            self._status_bar.set_status(f"Calling tool: {message.tool_name}")
        tool_widget = ToolCallWidget(
            message.tool_call_id, message.tool_name, message.args
        )
        if self._scroll and self._collapsible:
            await self._scroll.mount(tool_widget, before=self._collapsible)
            self._scroll.anchor(anchor=True)
        self._pending_tool_widgets[message.tool_call_id] = tool_widget

    @on(AgentApprovalRequestMessage)
    async def handle_approval_request(self, message: AgentApprovalRequestMessage) -> None:
        for call in message.tool_calls:
            if call.tool_call_id in self._pending_tool_widgets:
                self._pending_tool_widgets[call.tool_call_id].remove()
                del self._pending_tool_widgets[call.tool_call_id]

        tool_names = ", ".join(call.tool_name for call in message.tool_calls)
        if self._status_bar:
            self._status_bar.set_status(f"Awaiting approval for: {tool_names}")

        widget = ApprovalWidget(message)
        if self._scroll:
            await self._scroll.mount(widget)
            self._scroll.anchor(anchor=True)

        await self._reset_output()

    async def _reset_output(self) -> None:
        if self._collapsible:
            self._collapsible.collapsed = True
        if self._scroll:
            self._thinking_output, self._collapsible, new_md = (
                await self._create_output_widgets(self._scroll)
            )
            self._stream_writer = Markdown.get_stream(new_md)
        self._thinking_text = ""

    @on(AgentDoneMessage)
    async def handle_done(self, message: AgentDoneMessage) -> None:
        if self._collapsible:
            self._collapsible.collapsed = True
        if self._status_bar:
            self._status_bar.clear_status()
        self._finish_run()

    @on(AgentErrorMessage)
    async def handle_error(self, message: AgentErrorMessage) -> None:
        error_widget = Static(f"Error: {message.error}", classes="error")
        if self._scroll:
            await self._scroll.mount(error_widget)
        if self._collapsible:
            self._collapsible.collapsed = True
        if self._status_bar:
            self._status_bar.clear_status()
        self._finish_run()

    @on(AgentCancelledMessage)
    async def handle_cancelled(self, message: AgentCancelledMessage) -> None:
        cancelled_widget = Static("Operation cancelled by user", classes="cancelled")
        if self._scroll:
            await self._scroll.mount(cancelled_widget)
        if self._status_bar:
            self._status_bar.clear_status()

        for widget in self._pending_tool_widgets.values():
            widget.remove()
        self._pending_tool_widgets.clear()
        self._finish_run()

    def _finish_run(self) -> None:
        self._cancellation_event = None
        input_widget = self.query_one("#input", TextArea)
        input_widget.disabled = False
        input_widget.focus()

    @work(exclusive=True)
    async def background_task(self, message: str) -> None:
        scroll = self.query_one(VerticalScroll)
        status_bar = self.query_one("#status", StatusBar)

        new_label = Static(classes="user")
        new_label.border_title = "You"
        new_label.update(message)
        await scroll.mount(new_label)

        thinking_output, collapsible, new_md = await self._create_output_widgets(scroll)
        scroll.anchor(anchor=True)

        stream_writer = Markdown.get_stream(new_md)

        self._scroll = scroll
        self._status_bar = status_bar
        self._collapsible = collapsible
        self._thinking_output = thinking_output
        self._stream_writer = stream_writer
        self._thinking_text = ""
        self._pending_tool_widgets = {}

        self.query_one("#input", TextArea).disabled = True
        status_bar.set_status("Thinking...")

        adapter = TextualAgentAdapter(
            app=self,
            session=self._session,
            prompt=message,
            cancellation_event=self._cancellation_event,
        )
        await adapter.run()
