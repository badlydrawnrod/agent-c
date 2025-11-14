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


class ConsoleUI:
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
        run_args = (user_input,)
        run_params = {
            "message_history": conversation,
            "deps": run_deps,
        }
        messages = conversation

        pause_event = asyncio.Event()
        cancel_event = asyncio.Event()
        input_source = create_input()
        loop_task: asyncio.Task[None] | None = None

        def handle_keys():
            for key_press in input_source.read_keys():
                if key_press.key == Keys.ControlP:
                    if not pause_event.is_set():
                        pause_event.set()
                elif key_press.key == Keys.ControlR:
                    if pause_event.is_set():
                        pause_event.clear()
                elif key_press.key == Keys.ControlC:
                    cancel_event.set()
                    if loop_task is not None:
                        loop_task.cancel()

        @contextlib.contextmanager
        def interaction_context(initial_status_text: str):
            """Context manager that sets up interactive environment with Live display."""
            with Live(
                console=self.console,
                vertical_overflow="visible",
                refresh_per_second=1,
            ) as live:
                with input_source.raw_mode():
                    with input_source.attach(handle_keys):
                        with self.console.status(initial_status_text) as status:
                            yield live, status

        async def stream_agent_response():
            """Stream agent response with pause/cancel support. Returns (output, result)."""
            thinking_text = "[bold green]Agent C is thinking...[/bold green]"
            responding_text = "[bold green]Agent C is replying...[/bold green]"
            paused_text = "[bold yellow]Paused - Press Ctrl+R to resume[/bold yellow]"

            with interaction_context(thinking_text) as (live, status):
                try:
                    if cancel_event.is_set():
                        raise asyncio.CancelledError()
                    has_output = False
                    async with agent.run_stream(*run_args, **run_params) as result:
                        async for text in result.stream_text():
                            if cancel_event.is_set():
                                raise asyncio.CancelledError()
                            if not has_output:
                                status.update(responding_text)
                                has_output = True
                            while pause_event.is_set():
                                status.update(paused_text)
                                live.update(text)
                                await asyncio.sleep(0.05)
                                if cancel_event.is_set():
                                    raise asyncio.CancelledError()
                            status.update(responding_text)
                            if not cancel_event.is_set():
                                live.update(Markdown(text))
                        if cancel_event.is_set():
                            raise asyncio.CancelledError()
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

        async def process_tool_approvals(
            deferred_output: DeferredToolRequests,
        ) -> DeferredToolResults:
            """Process deferred tool requests and collect user approvals."""
            approval_results = DeferredToolResults()
            for call in deferred_output.approvals:
                approved = await self.ask_approval(
                    call.tool_name, call.tool_call_id, call.args
                )
                approval_results.approvals[call.tool_call_id] = (
                    True if approved else ToolDenied("Tool denied by user")
                )
            return approval_results

        async def run_agent_loop():
            nonlocal messages, run_args, run_params
            while True:
                output, result = await stream_agent_response()
                messages = result.all_messages()

                if not isinstance(output, DeferredToolRequests):
                    break

                approval_results = await process_tool_approvals(output)

                run_args = ()
                run_params = {
                    "message_history": messages,
                    "deferred_tool_results": approval_results,
                    "deps": run_deps,
                }

        try:
            loop_task = asyncio.current_task()
            await run_agent_loop()
        except asyncio.CancelledError:
            pass

        return messages

    async def handle_command(self, command: str) -> tuple[str | None, bool]:
        """Handle special commands. Returns (new_personality, should_exit)."""
        command = command.strip().lower()

        if command in ("/clear", "/reset"):
            self.console.print("Context cleared.")
            return None, False

        if command in ("/bye", "/exit", "/quit"):
            return None, True

        parts = command.split()
        if len(parts) >= 2 and parts[0] == "/personality":
            new_personality = parts[1]
            if new_personality in self.personalities:
                self.console.print(f"Switched to personality: {new_personality}")
                return new_personality, False
            else:
                self.console.print(f"Unknown personality: {new_personality}")
                return None, False

        return None, False
