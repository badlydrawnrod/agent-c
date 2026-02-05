import asyncio
from collections.abc import AsyncGenerator

from agentc.core.types import (
    AgentChunk,
    AgentDone,
    ApprovalRequest,
    ApprovalResponse,
    UserInputRequest,
    UserInputResponse,
)
from agentc.middleware.debouncing import DebouncingMiddleware, ContentBuffer

def test_content_buffer():
    buffer = ContentBuffer(threshold=5)
    assert buffer.add("abc") is None
    assert buffer.add("de") == "abcde"
    assert buffer.add("fg") is None
    assert buffer.flush() == "fg"
    assert buffer.flush() is None

async def _test_debouncing_middleware_buffering():
    middleware = DebouncingMiddleware(threshold=10)
    
    async def mock_events() -> AsyncGenerator[AgentChunk | AgentDone, ApprovalResponse | None]:
        yield AgentChunk(content="Hello ", is_thought=False)
        yield AgentChunk(content="world!", is_thought=False)
        yield AgentDone(history=[])

    events = mock_events()
    processed = middleware.process(events)
    
    results = []
    async for event in processed:
        results.append(event)
    
    assert len(results) == 2
    assert isinstance(results[0], AgentChunk)
    assert results[0].content == "Hello world!"
    assert isinstance(results[1], AgentDone)

def test_debouncing_middleware_buffering():
    asyncio.run(_test_debouncing_middleware_buffering())

async def _test_debouncing_middleware_handshake():
    middleware = DebouncingMiddleware(threshold=10)
    
    async def mock_events() -> AsyncGenerator[AgentChunk | ApprovalRequest | AgentDone, ApprovalResponse | None]:
        yield AgentChunk(content="Thinking...", is_thought=True)
        resp = yield ApprovalRequest(tool_calls=[])
        assert resp is not None
        assert resp.approved is True
        
        yield AgentChunk(content="Done.", is_thought=False)
        yield AgentDone(history=[])

    events = mock_events()
    processed = middleware.process(events)
    
    it = aiter(processed)
    
    event1 = await anext(it)
    assert isinstance(event1, AgentChunk)
    assert event1.content == "Thinking..."
    
    event2 = await anext(it)
    assert isinstance(event2, ApprovalRequest)
    
    event3 = await it.asend(ApprovalResponse(approved=True))
    assert isinstance(event3, AgentChunk)
    assert event3.content == "Done."
    
    event4 = await anext(it)
    assert isinstance(event4, AgentDone)

def test_debouncing_middleware_handshake():
    asyncio.run(_test_debouncing_middleware_handshake())


async def _test_debouncing_middleware_user_input_handshake():
    middleware = DebouncingMiddleware(threshold=10)

    async def mock_events() -> AsyncGenerator[
        AgentChunk | UserInputRequest | AgentDone, UserInputResponse | None
    ]:
        yield AgentChunk(content="Thinking...", is_thought=True)
        resp = yield UserInputRequest(
            question="Type something",
            options=[],
            allow_freeform=True,
        )
        assert resp is not None
        assert resp.response == "ok"

        yield AgentChunk(content="Done.", is_thought=False)
        yield AgentDone(history=[])

    events = mock_events()
    processed = middleware.process(events)

    it = aiter(processed)

    event1 = await anext(it)
    assert isinstance(event1, AgentChunk)
    assert event1.content == "Thinking..."

    event2 = await anext(it)
    assert isinstance(event2, UserInputRequest)

    event3 = await it.asend(UserInputResponse(response="ok"))
    assert isinstance(event3, AgentChunk)
    assert event3.content == "Done."

    event4 = await anext(it)
    assert isinstance(event4, AgentDone)


def test_debouncing_middleware_user_input_handshake():
    asyncio.run(_test_debouncing_middleware_user_input_handshake())
