import asyncio
import contextlib
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.input import create_input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, ToolDenied
from pydantic_ai.messages import ModelMessage

from .protocol import UIProtocol


class InteractionController:
    """Manages the agent-user conversation loop with pause/resume/cancel support."""

    def __init__(
        self,
        agent: Agent[Any, str | DeferredToolRequests],
        user_input: str,
        conversation: list[ModelMessage],
        run_deps: Any,
        console: Console,
        ui: "ConsoleUI",
    ):
        """
        Initialize the interaction controller.

        Args:
            agent: The Pydantic AI agent to run.
            user_input: Initial user input for the agent.
            conversation: Current message history.
            run_deps: Dependencies to pass to the agent.
            console: Rich console for output.
            ui: The ConsoleUI instance for approvals.
        """
        self.agent = agent
        self.user_input = user_input
        self.conversation = conversation
        self.run_deps = run_deps
        self.console = console
        self.ui = ui

        # State management
        self.pause_event = asyncio.Event()
        self.cancel_event = asyncio.Event()
        self.input_source = create_input()
        self.loop_task: asyncio.Task[None] | None = None

        # Run parameters that evolve through the loop
        self.run_args: tuple[str, ...] = (user_input,)
        self.run_params: dict[str, Any] = {
            "message_history": conversation,
            "deps": run_deps,
        }
        self.messages = conversation

    async def run(self) -> list[ModelMessage]:
        """
        Run the interaction loop until completion.

        Returns:
            Updated conversation message history.

        Raises:
            asyncio.CancelledError: If the interaction is cancelled.
        """
        try:
            self.loop_task = asyncio.current_task()
            await self._interaction_loop()
        except asyncio.CancelledError:
            pass
        return self.messages

    async def _interaction_loop(self) -> None:
        """
        Main algorithm: stream response -> check if deferred -> collect approvals -> loop.

        Continues until the agent returns a non-DeferredToolRequests output.
        """
        while True:
            output, result = await self._stream_response()
            self.messages = result.all_messages()

            if not isinstance(output, DeferredToolRequests):
                break

            approval_results = await self._collect_tool_approvals(output)
            self._prepare_next_run_params(approval_results)

    async def _stream_response(
        self,
    ) -> tuple[str | DeferredToolRequests, Any]:
        """
        Stream agent response with pause/resume and cancel support.

        Returns:
            Tuple of (output, result) where output is either a string or
            DeferredToolRequests, and result is the agent's run result.
        """
        thinking_text = "[bold green]Agent C is thinking...[/bold green]"
        responding_base = "[bold green]Agent C is replying...[/bold green]"
        paused_text = "[bold yellow]Paused - Press spacebar to resume[/bold yellow]"

        with self._setup_interaction_context(thinking_text) as (live, status):
            try:
                if self.cancel_event.is_set():
                    raise asyncio.CancelledError()

                has_output = False
                accumulated_text = ""
                async with self.agent.run_stream(
                    *self.run_args, **self.run_params
                ) as result:
                    async for text in result.stream_text(delta=True):
                        if self.cancel_event.is_set():
                            raise asyncio.CancelledError()

                        accumulated_text += text

                        if not has_output:
                            has_output = True

                        # Update status with character count
                        if accumulated_text:
                            status.update(
                                f"{responding_base} ({len(accumulated_text)} chars)"
                            )

                        await self._render_status_update(
                            live, status, text, paused_text, responding_base
                        )

                    if self.cancel_event.is_set():
                        raise asyncio.CancelledError()

                    # Clear the live display and render the complete markdown output
                    live.stop()
                    self.console.print(Markdown(accumulated_text))

                    output = await result.get_output()
            except asyncio.CancelledError:
                self.console.print(
                    Text(
                        "**Cancelled** - Exiting.",
                        style="bold red",
                    )
                )
                raise

        return output, result

    @contextlib.contextmanager
    def _setup_interaction_context(self, initial_status_text: str):
        """
        Set up interactive environment with Live display, raw mode, and key handling.

        Args:
            initial_status_text: Status text to display initially.

        Yields:
            Tuple of (live, status) for managing display during interaction.
        """
        with Live(
            console=self.console,
            vertical_overflow="visible",
            refresh_per_second=1,
        ) as live:
            with self.input_source.raw_mode():
                with self.input_source.attach(self._handle_keyboard_input):
                    with self.console.status(initial_status_text) as status:
                        yield live, status

    def _handle_keyboard_input(self) -> None:
        """
        Handle keyboard input: spacebar (pause/resume), Ctrl+C (cancel).
        """
        for key_press in self.input_source.read_keys():
            if key_press.key == " ":
                if self.pause_event.is_set():
                    self.pause_event.clear()
                else:
                    self.pause_event.set()
            elif key_press.key == Keys.ControlC:
                self.cancel_event.set()
                if self.loop_task is not None:
                    self.loop_task.cancel()

    async def _render_status_update(
        self,
        live: Live,
        status,
        text: str,
        paused_text: str,
        responding_base: str,
    ) -> None:
        """
        Update status while handling pause state.

        Args:
            live: Rich Live display object.
            status: Rich status context.
            text: Current text being streamed (for pause state display).
            paused_text: Status text to show when paused.
            responding_base: Base status text to show when responding (without spinner).
        """
        while self.pause_event.is_set():
            status.update(paused_text)
            await asyncio.sleep(0.05)
            if self.cancel_event.is_set():
                raise asyncio.CancelledError()

    async def _collect_tool_approvals(
        self, deferred_output: DeferredToolRequests
    ) -> DeferredToolResults:
        """
        Collect user approvals for deferred tool requests.

        Args:
            deferred_output: The deferred tool requests from the agent.

        Returns:
            DeferredToolResults with user approval decisions.
        """
        approval_results = DeferredToolResults()
        for call in deferred_output.approvals:
            approved = await self.ui.ask_approval(
                call.tool_name, call.tool_call_id, call.args
            )
            approval_results.approvals[call.tool_call_id] = (
                True if approved else ToolDenied("Tool denied by user")
            )
        return approval_results

    def _prepare_next_run_params(self, approval_results: DeferredToolResults) -> None:
        """
        Prepare parameters for the next agent run with approval results.

        Args:
            approval_results: User approval decisions from the previous run.
        """
        self.run_args = ()
        self.run_params = {
            "message_history": self.messages,
            "deferred_tool_results": approval_results,
            "deps": self.run_deps,
        }


class ConsoleUI(UIProtocol):
    """Terminal-based UI implementation using Rich and prompt_toolkit."""

    def __init__(self, personalities: dict[str, Any]):
        self.personalities = personalities
        self.console = Console()
        self.session = self._create_prompt_session()
        self.style = self._create_style()

    def _create_prompt_session(self) -> PromptSession:
        """Create prompt session with key bindings and command completion."""
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
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
        intro = f"""\
I'm Agent C, a helpful coding agent.

You can ask me to perform various code editing tasks using the available tools:
{tools_info}

[bold red]This is a tech demo, so please be sensible. You are responsible for your files[/bold red].
"""
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
        result = await self.session.prompt_async(prompt, show_frame=True)
        result = result.lower().strip()
        return result == "y"

    async def run_agent_interaction(
        self,
        agent: Agent[Any, str | DeferredToolRequests],
        user_input: str,
        conversation: list[ModelMessage],
        run_deps: Any,
    ) -> list[ModelMessage]:
        """Run the agent interaction loop and return updated conversation."""
        controller = InteractionController(
            agent, user_input, conversation, run_deps, self.console, self
        )
        return await controller.run()
