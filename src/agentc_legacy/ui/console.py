from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, HSplit, Layout, VerticalAlign, Window
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    DynamicContainer,
    Float,
    FloatContainer,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style, merge_styles
from prompt_toolkit.styles.pygments import style_from_pygments_cls
from prompt_toolkit.widgets import Frame, TextArea
from pygments.lexers.markup import MarkdownLexer
from pygments.styles import get_style_by_name

from agentc_legacy.core.types import ApprovalRequest, StreamChunk
from agentc_legacy.tui.widgets import (
    InstrumentedScrollablePane,
    ScrollablePaneConfig,
    ScrollController,
)

from .protocol import UIProtocol

# -- Styles & Constants -------------------------------------------------------

BASE_UI_STYLE = Style.from_dict(
    {
        "frame.border": "#2f3542",
        "frame.label": "#ced6e0 italic",
        "text-area": "bg:#0b1220 #dbeafe",
        "thinking-text": "bg:default #94a3b8 italic",
        "user-prompt": "bg:#1e3a5f #60a5fa bold",
        "user-prompt-label": "#60a5fa bold",
        "placeholder": "#64748b italic",
        "status-indicator": "bg:#1e293b #f59e0b",
        "status-hint": "#94a3b8",
        "bottom-toolbar": "#000000 bg:#007f00",
    }
)
PYGMENTS_STYLE = style_from_pygments_cls(get_style_by_name("nord"))
APP_STYLE = merge_styles([BASE_UI_STYLE, PYGMENTS_STYLE])


# -- Helpers ------------------------------------------------------------------


def _to_container(obj: Any) -> Any:
    """Convert a widget-like object to its container representation."""
    c = getattr(obj, "__pt_container__", None)
    if callable(c):
        return c()
    if c is not None:
        return c
    return obj


def _display_only_text_area(text: str = "", style: str | None = None) -> TextArea:
    """Create a TextArea configured for read-only display."""
    area = TextArea(
        text=text,
        read_only=True,
        focusable=False,
        wrap_lines=True,
        lexer=PygmentsLexer(MarkdownLexer),
    )
    _update_textarea_height(area)
    return area


def _thinking_text_area() -> TextArea:
    area = TextArea(
        text="",
        read_only=True,
        focusable=False,
        wrap_lines=True,
        style="class:thinking-text",
    )
    _update_textarea_height(area)
    return area


def _user_prompt_area(text: str = "") -> TextArea:
    """Create a TextArea configured for displaying user prompts."""
    area = TextArea(
        text=text,
        read_only=True,
        focusable=False,
        wrap_lines=True,
        style="class:user-prompt",
    )
    _update_textarea_height(area)
    return area


def _update_textarea_height(area: TextArea) -> None:
    line_count = max(1, area.text.count("\n") + 1 if area.text else 1)
    area.window.height = Dimension(preferred=line_count, max=line_count)


class ThrottledInvalidator:
    """Coalesce frequent invalidate() requests into a fixed interval."""

    def __init__(
        self,
        invalidate_fn: Callable[[], None],
        interval: float,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._invalidate = invalidate_fn
        self._interval = interval
        self._loop = loop
        self._last_call = 0.0
        self._pending_handle: asyncio.TimerHandle | None = None

    def request(self) -> None:
        # Ensure we are on the loop
        try:
            curr = asyncio.get_running_loop()
        except RuntimeError:
            curr = None

        if curr == self._loop:
            self._request_on_loop()
        else:
            self._loop.call_soon_threadsafe(self._request_on_loop)

    def _request_on_loop(self) -> None:
        now = self._loop.time()
        elapsed = now - self._last_call
        if elapsed >= self._interval:
            self._last_call = now
            self._invalidate()
            return

        if self._pending_handle is None:
            delay = self._interval - elapsed
            self._pending_handle = self._loop.call_later(delay, self._flush)

    def _flush(self) -> None:
        self._pending_handle = None
        self._last_call = self._loop.time()
        self._invalidate()


class ThinkingPane:
    def __init__(self, index: int) -> None:
        self.index = index
        self.collapsed = False
        self.textarea = _thinking_text_area()
        self.frame = Frame(self.textarea, title=f"Thinking #{index}")
        self.container = ConditionalContainer(
            content=self.frame,
            filter=Condition(lambda: not self.collapsed),
        )

    def toggle(self) -> None:
        self.collapsed = not self.collapsed


# -- ConsoleUI Implementation -------------------------------------------------


class ConsoleUI(UIProtocol):
    """Terminal-based UI implementation using prompt_toolkit and custom widgets."""

    def __init__(self, personalities: dict[str, Any]):
        self.personalities = personalities
        self.app: Application | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

        # UI Components
        self.hsplit = HSplit([], align=VerticalAlign.BOTTOM)
        self.input_buffer = Buffer(history=InMemoryHistory(), multiline=True)
        self.scroll_controller: ScrollController | None = None
        self.invalidator: ThrottledInvalidator | None = None

        # State
        self.thinking_panes: list[ThinkingPane] = []
        self.current_thinking_pane: ThinkingPane | None = None
        self.current_response_area: TextArea | None = None
        self.submit_event = asyncio.Event()
        self.exit_requested = False
        self.approval_event = asyncio.Event()
        self.approval_result = False
        self.is_approving = False
        self.input_handler: Callable[[str], Awaitable[None]] | None = None

    def _create_layout(self) -> Layout:
        # Input Panel
        def get_placeholder():
            if not self.input_buffer.text:
                if self.is_approving:
                    return [
                        (
                            "class:placeholder",
                            "Type 'y' to approve, 'n' to deny... (Ctrl+Enter to submit)",
                        )
                    ]
                return [
                    (
                        "class:placeholder",
                        "Type your message here... (Ctrl+Enter to submit, Enter for new line)",
                    )
                ]
            return []

        input_control = BufferControl(buffer=self.input_buffer, focus_on_click=True)
        input_window = Window(content=input_control, height=Dimension.exact(3))
        input_with_placeholder = FloatContainer(
            content=input_window,
            floats=[
                Float(
                    content=Window(
                        content=FormattedTextControl(get_placeholder),
                        dont_extend_height=True,
                    )
                )
            ],
        )
        def get_input_frame():
            if self.is_approving:
                return Frame(
                    input_with_placeholder,
                    title="Approval Required (y/n)",
                    style="class:status-indicator",
                )
            return Frame(input_with_placeholder, title="Input")

        input_panel = DynamicContainer(get_input_frame)

        # Scrollable Output
        def is_manual_scroll_active() -> bool:
            if self.scroll_controller:
                return not self.scroll_controller.is_auto_following
            return False

        scrollable_pane = InstrumentedScrollablePane(
            self.hsplit,
            config=ScrollablePaneConfig(
                keep_cursor_visible=Condition(lambda: not is_manual_scroll_active()),
                keep_focused_window_visible=Condition(
                    lambda: not is_manual_scroll_active()
                ),
            ),
        )

        # Status Bar (Manual Scroll Indicator)
        def get_status_text():
            if not is_manual_scroll_active():
                return []
            pct = 0
            if scrollable_pane.virtual_height > 0:
                max_scroll = max(
                    0, scrollable_pane.virtual_height - scrollable_pane.visible_height
                )
                if max_scroll > 0:
                    pct = int((scrollable_pane.vertical_scroll / max_scroll) * 100)
                else:
                    pct = 100
            return [
                ("class:status-indicator", f" 🔒 MANUAL SCROLL {pct}% "),
                ("class:status-hint", " Press Ctrl+End to resume auto-follow "),
            ]

        status_window = ConditionalContainer(
            content=Window(
                content=FormattedTextControl(get_status_text),
                height=Dimension.exact(1),
                style="class:status-bar",
            ),
            filter=Condition(is_manual_scroll_active),
        )

        # Approval Prompt (Overlay)
        def get_approval_prompt():
            if self.is_approving:
                return [("class:status-indicator", " APPROVAL REQUESTED (y/n) ")]
            return []

        approval_window = ConditionalContainer(
            content=Window(
                content=FormattedTextControl(get_approval_prompt),
                height=Dimension.exact(1),
                style="class:status-indicator",
            ),
            filter=Condition(lambda: self.is_approving),
        )

        # Main Layout
        root_container = HSplit(
            [
                scrollable_pane,
                status_window,
                approval_window,
                input_panel,
            ]
        )

        layout = Layout(container=root_container, focused_element=input_control)

        # Initialize Controller & Invalidator
        # Note: We can't fully init them until we have the app, but we can prep the pane
        # We'll attach the invalidator in run_agent_interaction
        self._scrollable_pane_ref = scrollable_pane

        return layout

    def _create_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("c-j")
        def _(event):
            """Submit input."""
            text = self.input_buffer.text
            if text.strip():
                self.input_buffer.append_to_history()
            self.input_buffer.reset()
            
            # If we are waiting for approval, signal it
            if self.is_approving:
                self.submit_event.set()
                return

            # Otherwise, handle as normal input
            if self.input_handler:
                asyncio.create_task(self.input_handler(text))

        @kb.add("up")
        def _(event):
            if event.app.layout.has_focus(self.input_buffer):
                if self.input_buffer.document.cursor_position_row == 0:
                    self.input_buffer.history_backward()
                else:
                    self.input_buffer.cursor_up()
            elif self.scroll_controller:
                self.scroll_controller.scroll_lines(-1)

        @kb.add("down")
        def _(event):
            if event.app.layout.has_focus(self.input_buffer):
                if (
                    self.input_buffer.document.cursor_position_row
                    == self.input_buffer.document.line_count - 1
                ):
                    self.input_buffer.history_forward()
                else:
                    self.input_buffer.cursor_down()
            elif self.scroll_controller:
                self.scroll_controller.scroll_lines(1)

        @kb.add("pageup")
        def _(event):
            if self.scroll_controller:
                self.scroll_controller.scroll_pages(-1)

        @kb.add("pagedown")
        def _(event):
            if self.scroll_controller:
                self.scroll_controller.scroll_pages(1)

        @kb.add("c-home")
        def _(event):
            if self.scroll_controller:
                self.scroll_controller.scroll_to_top()

        @kb.add("c-end")
        def _(event):
            if self.scroll_controller:
                self.scroll_controller.scroll_to_bottom()

        @kb.add("c-t")
        def _(event):
            if self.thinking_panes:
                self.thinking_panes[-1].toggle()
                if self.invalidator:
                    self.invalidator.request()

        return kb

    async def show_intro(self, tools_info: str) -> None:
        """Display the introduction message."""
        logo = r"""
     ___                    __     ______
    /   | ____ ____  ____  / /_   / ____/
   / /| |/ __ `/ _ \/ __ \/ __/  / /
  / ___ / /_/ /  __/ / / / /_   / /___
 /_/  |_\__, /\___/_/ /_/\__/   \____/
       /____/
"""
        intro_text = (
            f"{logo}\n"
            "I'm Agent C, a helpful coding agent.\n\n"
            "You can ask me to perform various code editing tasks using the available tools:\n"
            f"{tools_info}\n\n"
            "**This is a tech demo, so please be sensible. You are responsible for your files**"
        )
        area = _display_only_text_area(intro_text)
        self.hsplit.children.append(_to_container(area))

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        # Ensure we are on the loop
        try:
            curr = asyncio.get_running_loop()
        except RuntimeError:
            curr = None
            
        if self.loop and curr != self.loop:
            self.loop.call_soon_threadsafe(self.show_info, message)
            return

        area = _display_only_text_area(f"_{message}_")
        self.hsplit.children.append(_to_container(area))
        self._invalidate()

    async def get_user_input(self) -> str | None:
        """Deprecated: Input is now handled via callback."""
        raise NotImplementedError("get_user_input is deprecated in this UI")

    async def ask_approval(
        self, tool_name: str, tool_call_id: str, params: dict | str | None
    ) -> bool:
        """Ask for approval via the TUI."""
        self.is_approving = True
        msg = f"**Approval Request**\nTool: `{tool_name}`\nParams: `{params}`\n\nAllow? (y/n)"
        area = _display_only_text_area(msg)
        frame = Frame(area, title="Approval Needed", style="class:status-indicator")
        self.hsplit.children.append(_to_container(frame))
        self._invalidate()
        self._auto_scroll()

        try:
            await self.submit_event.wait()
            self.submit_event.clear()
            
            last_input = self.input_buffer.history.get_strings()[-1] if self.input_buffer.history.get_strings() else ""
            return last_input.strip().lower() == 'y'
            
        finally:
            self.is_approving = False
            self._invalidate()

    async def request_approval(self, req: ApprovalRequest) -> bool:
        return await self.ask_approval(req.tool_name, req.tool_call_id, req.params)

    # -- LoopCallbacks implementation -----------------------------------------

    def on_thinking(self) -> None:
        """Called when the agent starts thinking."""
        index = len(self.thinking_panes) + 1
        pane = ThinkingPane(index)
        self.thinking_panes.append(pane)
        self.current_thinking_pane = pane
        self.hsplit.children.append(pane.container)
        self._auto_scroll()
        self._invalidate()

    def on_thinking_chunk(self, chunk: str) -> None:
        """Accumulate streamed thinking text."""
        if self.current_thinking_pane:
            self.current_thinking_pane.textarea.text += chunk
            _update_textarea_height(self.current_thinking_pane.textarea)
            self._auto_scroll()
            self._invalidate()

    def on_stream_chunk(self, chunk: StreamChunk) -> None:
        """Accumulate streamed text."""
        if not self.current_response_area:
            self.current_response_area = _display_only_text_area()
            self.hsplit.children.append(_to_container(self.current_response_area))
        
        self.current_response_area.text += chunk.text
        _update_textarea_height(self.current_response_area)
        self._auto_scroll()
        self._invalidate()

    def on_stream_complete(self) -> None:
        """Finished streaming."""
        self.current_response_area = None
        self._auto_scroll()
        self._invalidate()

    def on_status_update(self, status: str) -> None:
        # We could show this in a status bar or ephemeral text
        pass

    def on_cancelled(self, message: str) -> None:
        self.show_info(f"Cancelled: {message}")

    def _invalidate(self) -> None:
        if self.invalidator:
            self.invalidator.request()

    def _auto_scroll(self) -> None:
        if self.scroll_controller:
            self.scroll_controller.request_follow()

    async def run(self, input_handler: Callable[[str], Awaitable[None]]) -> None:
        """Run the UI application."""
        self.input_handler = input_handler
        self.loop = asyncio.get_running_loop()
        layout = self._create_layout()
        kb = self._create_key_bindings()
        
        self.app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            style=APP_STYLE,
            mouse_support=True,
        )
        
        self.invalidator = ThrottledInvalidator(self.app.invalidate, 0.05, self.loop)
        self.scroll_controller = ScrollController(
            self._scrollable_pane_ref, self.invalidator.request
        )

        await self.app.run_async()
