"""
Textual UI for Agent C Next: the `TextualAgentApp`.

Encapsulates the main Textual application that mounts the view,
manages agent lifecycle (start, cancel), and handles agent events
via the `TextualAgentAdapter`. UI widgets are defined in `widgets.py`.
"""

import asyncio


from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Footer, Markdown, Static, TextArea

from .widgets import (
    ApprovalWidget,
    HistoryTextArea,
    StatusBar,
    ToolCallWidget,
)
from ..adapters.textual_messages import (
    AgentApprovalRequestMessage,
    AgentCancelledMessage,
    AgentDoneMessage,
    AgentErrorMessage,
    AgentThinkingMessage,
    AgentTextMessage,
    AgentToolCallMessage,
    AgentToolResultMessage,
)
from ..adapters.textual import TextualAgentAdapter
from ..core.commands import CommandParser, execute_command
from ..core.provider_loader import load_providers
from ..core.types import AgentSessionProtocol, CommandType, RunDeps


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
        deps: RunDeps | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._session = session
        self._deps = deps or RunDeps()
        self._cancellation_event: asyncio.Event | None = None
        self._pending_tool_widgets: dict[str, ToolCallWidget] = {}

        self._scroll: VerticalScroll | None = None
        self._status_bar: StatusBar | None = None
        self._collapsible: Collapsible | None = None
        self._thinking_output: Static | None = None
        self._stream_writer: Any | None = None
        self._thinking_text = ""
        self.command_parser = CommandParser(load_providers())

    async def _reset_ui_state(self) -> None:
        """Clear the scroll area and reset tracking variables."""
        if self._scroll:
            await self._scroll.query("*").remove()
        self._thinking_text = ""
        self._pending_tool_widgets.clear()
        self._collapsible = None
        self._thinking_output = None
        self._stream_writer = None

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

    async def action_submit_input(self) -> None:
        input_widget = self.query_one("#input", HistoryTextArea)
        user_text = input_widget.text.strip()

        if not user_text:
            return

        # Parse command.
        result = self.command_parser.parse(user_text)

        # Handle framework-specific commands directly.
        if result.command_type == CommandType.EXIT:
            self.exit()
            return

        if result.command_type == CommandType.UNKNOWN:
            self.notify(result.args["error"], severity="error")
            return

        # Execute command and apply effect.
        effect = execute_command(result, deps=self._deps)
        if effect is not None:
            input_widget.clear()
            if effect.should_reset_ui:
                await self._reset_ui_state()
            if effect.new_session is not None:
                self._session = effect.new_session
            if effect.notification:
                self.notify(effect.notification)
            return

        # Normal input.
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

    @on(AgentToolResultMessage)
    async def handle_tool_result(self, message: AgentToolResultMessage) -> None:
        """Handle tool result completion."""
        # Remove the pending tool widget if it exists
        if message.tool_call_id in self._pending_tool_widgets:
            widget = self._pending_tool_widgets[message.tool_call_id]
            # Update the widget with result (success/failure status)
            if message.result.success:
                widget.mark_success()
            else:
                widget.mark_failure(message.result.error)

            del self._pending_tool_widgets[message.tool_call_id]

    @on(AgentApprovalRequestMessage)
    async def handle_approval_request(
        self, message: AgentApprovalRequestMessage
    ) -> None:
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
