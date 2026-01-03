import asyncio

from prompt_toolkit.styles import Style
from rich.console import Console

from agentc_legacy.ui.console import ConsoleUI


class _FakeSession:
    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc

    async def prompt_async(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        return self.value


def test_consoleui_ask_approval_yes() -> None:
    ui = ConsoleUI.__new__(ConsoleUI)
    ui.personalities = {}
    ui.console = Console()
    ui.session = _FakeSession("y")
    ui.approval_session = ui.session
    ui.style = Style.from_dict({})

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(ui.ask_approval("tool", "call-1", None))
    finally:
        loop.close()

    assert res is True


def test_consoleui_ask_approval_no() -> None:
    ui = ConsoleUI.__new__(ConsoleUI)
    ui.personalities = {}
    ui.console = Console()
    ui.session = _FakeSession("n")
    ui.approval_session = ui.session
    ui.style = Style.from_dict({})

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(ui.ask_approval("tool", "call-1", None))
    finally:
        loop.close()

    assert res is False


def test_consoleui_ask_approval_keyboard_interrupt() -> None:
    ui = ConsoleUI.__new__(ConsoleUI)
    ui.personalities = {}
    ui.console = Console()
    ui.session = _FakeSession(exc=KeyboardInterrupt())
    ui.approval_session = ui.session
    ui.style = Style.from_dict({})

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(ui.ask_approval("tool", "call-1", None))
    finally:
        loop.close()

    # KeyboardInterrupt should return False (treated as denial)
    assert res is False
