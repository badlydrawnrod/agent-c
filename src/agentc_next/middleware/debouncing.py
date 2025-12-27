"""
Middleware that buffers small text and thinking deltas.

Aggregates short streaming deltas into larger `PartStartEvent` chunks to
reduce UI chattiness while preserving the agentic loop's async
send/receive protocol.
"""

from collections.abc import AsyncGenerator

from ..core.types import (
    AgentChunk,
    AgentDone,
    AgentEvent,
    ApprovalRequest,
    ApprovalResponse,
)


class ContentBuffer:
    """Buffers content until a threshold is reached."""

    def __init__(self, threshold: int = 40):
        self._buffer: list[str] = []
        self._current_len = 0
        self._threshold = threshold

    def add(self, content: str) -> str | None:
        self._buffer.append(content)
        self._current_len += len(content)
        if self._current_len >= self._threshold:
            return self.flush()
        return None

    def flush(self) -> str | None:
        if not self._buffer:
            return None
        content = "".join(self._buffer)
        self._buffer = []
        self._current_len = 0
        return content


class DebouncingMiddleware:
    """Buffers text and thinking chunks to reduce UI chattiness."""

    def __init__(self, threshold: int = 40):
        self._text_buffer = ContentBuffer(threshold)
        self._thinking_buffer = ContentBuffer(threshold)

    def _flush_all(self) -> list[AgentChunk]:
        events: list[AgentChunk] = []
        if text := self._text_buffer.flush():
            events.append(AgentChunk(content=text, is_thought=False))
        if thinking := self._thinking_buffer.flush():
            events.append(AgentChunk(content=thinking, is_thought=True))
        return events

    async def process(
        self,
        events: AsyncGenerator[AgentEvent, ApprovalResponse | None],
    ) -> AsyncGenerator[AgentEvent, ApprovalResponse | None]:
        response: ApprovalResponse | None = None

        while True:
            try:
                event = await events.asend(response)
                response = None

                if isinstance(event, AgentChunk):
                    buffer = (
                        self._thinking_buffer if event.is_thought else self._text_buffer
                    )
                    if buffered := buffer.add(event.content):
                        yield AgentChunk(content=buffered, is_thought=event.is_thought)

                elif isinstance(event, ApprovalRequest):
                    for flushed in self._flush_all():
                        yield flushed
                    response = yield event

                elif isinstance(event, AgentDone):
                    for flushed in self._flush_all():
                        yield flushed
                    yield event
                    return

                else:
                    yield event

            except StopAsyncIteration:
                for flushed in self._flush_all():
                    yield flushed
                return


__all__ = ["DebouncingMiddleware", "ContentBuffer"]
