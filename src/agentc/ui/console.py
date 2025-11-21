from __future__ import annotations

import contextlib
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.input import create_input
from prompt_toolkit.input.base import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import ModelMessage
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from agentc.core.runner import AgentRunner
from agentc.core.types import ApprovalRequest, StreamChunk

from .protocol import UIProtocol

# Human-facing UI text (owned by the UI implementation).
DEFAULT_THINKING_TEXT = "Agent C is thinking..."
DEFAULT_RESPONDING_BASE = "Agent C is replying..."


class ConsoleUI(UIProtocol):
    """Terminal-based UI implementation using Rich and prompt_toolkit."""

    def __init__(self, personalities: dict[str, Any]):
        self.personalities = personalities
        self.console = Console()
        self.session = self._create_prompt_session()
        self.approval_session = self._create_approval_session()
        self.style = self._create_style()
        # Live/status reactive state used by callbacks
        self._live: Live | None = None
        self._spinner_text: str = DEFAULT_THINKING_TEXT
        self._accumulated_text: str = ""
        self._accumulated_thinking: str = ""
        self._input_source: Input | None = None

    def _create_prompt_session(self) -> PromptSession:
        """Create prompt session with key bindings and command completion."""
        kb = KeyBindings()

        from prompt_toolkit.application.current import get_app
        from prompt_toolkit.filters import Condition

        @kb.add(
            "enter",
            filter=Condition(
                lambda: bool(get_app().current_buffer)
                and get_app().current_buffer.multiline()
            ),
        )
        def _(event):
            # Only insert a newline when the active buffer is in multiline mode.
            # This prevents single-line prompts (like approvals) from capturing
            # the Enter key and *not* submitting the input.
            event.current_buffer.newline()

        @kb.add("escape", "enter")
        def _(event):
            event.current_buffer.validate_and_handle()

        @kb.add("c-j")
        def _(event):
            event.current_buffer.validate_and_handle()

        class SlashCommandCompleter(Completer):
            def __init__(self, personalities: dict[str, Any]):
                self.personalities = personalities

            def get_completions(self, document, complete_event):
                text = document.text_before_cursor
                if text.strip() == "" or text.startswith("/"):
                    command_help = {
                        "/bye": "Exit the chat",
                        "/clear": "Clear the context",
                        "/exit": "Exit the chat",
                        "/personality": "Switch to a different personality",
                        "/quit": "Exit the chat",
                        "/reset": "Clear the context",
                    }
                    for cmd in command_help:
                        if cmd.startswith(text):
                            yield Completion(
                                cmd,
                                start_position=-len(text),
                                display_meta=command_help[cmd],
                            )
                    if text.startswith("/personality "):
                        prefix = "/personality "
                        remaining = text[len(prefix) :]
                        for name, config in self.personalities.items():
                            if name.startswith(remaining):
                                yield Completion(
                                    name,
                                    start_position=-len(remaining),
                                    display_meta=config.description,
                                )

        return PromptSession(
            key_bindings=kb,
            multiline=True,
            completer=SlashCommandCompleter(self.personalities),
        )

    def _create_approval_session(self) -> PromptSession:
        """Create a dedicated single-line prompt session for approvals."""
        # Use a fresh session so approval prompts don't inherit the multiline
        # bindings from the main chat prompt.
        return PromptSession(multiline=False)

    @contextlib.contextmanager
    def _suspend_keyboard_capture(self):
        """Temporarily release the low-level stdin hook used for hotkeys."""
        if self._input_source is None:
            yield
            return

        with self._input_source.detach():
            yield

    def _create_style(self) -> Style:
        """Create the prompt style."""
        return Style.from_dict(
            {
                "bottom-toolbar": "#000000 bg:#007f00",
                "rprompt": "#ff0000",
                "frame.border": "#884444",
                "completion-menu": "bg:#000000 #ffffff",
                "completion-menu.meta.completion": "bg:#000000 #7f7f7f",
                "completion-menu.meta.completion.current": "bg:#000000 #bfbfbf",
                "scrollbar.background": "bg:#000000",
                "scrollbar.button": "bg:#000000",
                "scrollbar.track": "bg:#000000",
                "scrollbar.track.hover": "bg:#000000",
            }
        )

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
        intro = Text(logo)
        intro.append("\nI'm Agent C, a helpful coding agent.\n\n")
        intro.append(
            "You can ask me to perform various code editing tasks using the available tools:\n"
        )
        intro.append(tools_info)
        intro.append("\n\n")
        intro.append(
            "This is a tech demo, so please be sensible. You are responsible for your files",
            style="bold red",
        )

        self.console.print(intro)

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        self.console.print(f"[dim]--- {message}[/dim]")

    async def get_user_input(self) -> str | None:
        """Get input from the user. Returns None if user wants to exit."""

        def bottom_toolbar():
            return [("class:bottom-toolbar", "Ctrl+Enter submits")]

        def rprompt():
            return [("class:rprompt", "")]

        try:
            user_input = await self.session.prompt_async(
                "> ",
                style=self.style,
                show_frame=True,
                bottom_toolbar=bottom_toolbar,
                rprompt=rprompt,
            )
            return user_input
        except KeyboardInterrupt:
            return None

    async def ask_approval(
        self, tool_name: str, tool_call_id: str, params: dict | str | None
    ) -> bool:
        """Ask the user to approve a tool call. Returns True if approved."""
        prompt = f"The LLM wants to call {tool_name}. Allow (y/n): "
        # Approval prompts should be single-line so that Enter submits the
        # choice. A dedicated prompt session prevents the multiline bindings
        # from the main chat input from intercepting Enter.
        try:
            result = await self.approval_session.prompt_async(
                prompt,
                show_frame=True,
                multiline=False,
                style=self.style,
            )
        except KeyboardInterrupt:
            # Treat keyboard interrupt as a denial to keep semantics simple.
            return False
        result = result.lower().strip()
        return result == "y"

    # -- LoopCallbacks implementation -------------------------------------------------
    def _update_live_display(self) -> None:
        """Update the live display with current markdown and spinner."""
        if self._live is not None:
            from rich.console import Group
            from rich.spinner import Spinner
            from rich.styled import Styled

            # Create the spinner with current text
            spinner = Spinner("dots", text=Text(self._spinner_text, style="bold green"))

            # Mixed renderable types (Markdown/Spinner) - give the list a
            # broad type so static checkers are satisfied.
            items: list[Any] = []
            if self._accumulated_thinking:
                items.append(Styled(Markdown(self._accumulated_thinking), "italic dim"))

            # If we have content, show it above the spinner
            if self._accumulated_text:
                items.append(Styled(Markdown(self._accumulated_text), "dim"))

            items.append(spinner)

            renderable = Group(*items)

            self._live.update(renderable)

    def on_thinking(self) -> None:
        """Called when the agent starts thinking. Display initial status."""
        self._spinner_text = DEFAULT_THINKING_TEXT
        self._update_live_display()

    def on_thinking_chunk(self, chunk: str) -> None:
        """Accumulate streamed thinking text."""
        self._accumulated_thinking += chunk
        self._update_live_display()

    def on_stream_chunk(self, chunk: StreamChunk) -> None:
        """Accumulate streamed text for later rendering."""
        self._accumulated_text += chunk.text
        self._update_live_display()

    def on_stream_complete(self) -> None:
        """Render accumulated markdown once streaming is complete."""
        # When complete, we want to stop the Live display (which clears the transient parts)
        # and print the final markdown permanently.
        if self._live is not None:
            self._live.stop()

        if self._accumulated_thinking:
            self.console.print(Text("Thinking:", style="italic dim"))
            self.console.print(Markdown(self._accumulated_thinking), style="italic dim")
            self.console.print()

        if self._accumulated_text:
            self.console.print(Markdown(self._accumulated_text))

        self._accumulated_text = ""
        self._accumulated_thinking = ""
        self._spinner_text = DEFAULT_THINKING_TEXT

    def on_status_update(self, status: str) -> None:
        """Called for ad-hoc status updates (e.g., char counts)."""
        self._spinner_text = f"{DEFAULT_RESPONDING_BASE} {status}"
        self._update_live_display()

    def on_cancelled(self, message: str) -> None:
        """Show cancelled message to the user."""
        if self._live is not None:
            self._live.stop()
        self.console.print(Text(message, style="bold red"))

    async def request_approval(self, req: ApprovalRequest) -> bool:
        """Adapter to ask_approval for LoopCallbacks."""
        # We need to stop the live display before asking for input,
        # otherwise the prompt will interfere with the live render.
        if self._live is not None:
            self._live.stop()

        with self._suspend_keyboard_capture():
            try:
                return await self.ask_approval(
                    req.tool_name, req.tool_call_id, req.params
                )
            finally:
                # Restart live display if we're still in the loop (though typically approval happens between turns)
                if self._live is not None:
                    self._live.start()

    async def run_agent_interaction(
        self,
        agent: Agent[Any, str | DeferredToolRequests],
        user_input: str,
        conversation: list[ModelMessage],
        run_deps: Any,
    ) -> list[ModelMessage]:
        """Run the agent interaction loop and return updated conversation."""
        runner = AgentRunner(
            agent,
            user_input,
            conversation,
            run_deps,
            callbacks=self,
        )

        # Interaction context (Live display + keyboard input) is handled here
        input_source = create_input()
        self._input_source = input_source

        # Initialize state
        self._spinner_text = DEFAULT_THINKING_TEXT
        self._accumulated_text = ""
        self._accumulated_thinking = ""

        from rich.spinner import Spinner

        initial_renderable = Spinner(
            "dots", text=Text(self._spinner_text, style="bold green")
        )

        with Live(
            renderable=initial_renderable,
            console=self.console,
            vertical_overflow="visible",
            refresh_per_second=1,
            transient=True,  # Clear the live display when done (we print final result manually).
        ) as live:
            self._live = live

            with input_source.raw_mode():
                # Attach keyboard input handler for pause/resume/cancel
                def _handle_keyboard_input() -> None:
                    for key_press in input_source.read_keys():
                        if key_press.key == " ":
                            if runner.is_paused:
                                runner.resume()
                            else:
                                runner.pause()
                        elif key_press.key == Keys.ControlC:
                            runner.cancel()

                with input_source.attach(_handle_keyboard_input):
                    try:
                        return await runner.run()
                    finally:
                        self._live = None
                        self._input_source = None
