# pyright: reportMissingImports=false

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any, cast
from uuid import uuid4

from copilot import CopilotClient, CopilotSession
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.types import (
    PostToolUseHookInput,
    PostToolUseHookOutput,
    PreToolUseHookInput,
    PreToolUseHookOutput,
    SessionConfig as CopilotSessionConfig,
    SessionHooks,
)
from tool_pipeline_common import (
    AgentChunk,
    AgentDone,
    AgentEventStream,
    AgentSessionProtocol,
    SessionConfig,
    SessionFactoryProtocol,
    ToolCallInfo,
    ToolCallResultInfo,
    ToolPipeline,
    ToolPipelineInteractionRequest,
    ToolPipelineInteractionResponse,
    ToolResult,
)


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


class HookInteractionBroker:
    def __init__(self, pipeline: ToolPipeline) -> None:
        self._pipeline = pipeline
        self._queue: asyncio.Queue[
            tuple[ToolPipelineInteractionRequest, asyncio.Future[bool]]
        ] = asyncio.Queue()

    async def request_decision(self, tool_call: ToolCallInfo) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        request = self._pipeline.build_interaction_request(
            tool_call,
            {"source": "copilot_sdk_hook"},
        )
        await self._queue.put((request, future))
        return await future

    async def next_request(
        self,
    ) -> tuple[ToolPipelineInteractionRequest, asyncio.Future[bool]]:
        return await self._queue.get()


class CopilotToolHooks:
    def __init__(self, pipeline: ToolPipeline, interaction_broker: HookInteractionBroker) -> None:
        self._pipeline = pipeline
        self._interaction_broker = interaction_broker

    async def on_pre_tool_use(
        self,
        hook_input: PreToolUseHookInput,
        args: dict[str, str],
    ) -> PreToolUseHookOutput | None:
        del args
        tool_name = hook_input.get("toolName") or "unknown"
        tool_args = hook_input.get("toolArgs")
        mapped_args = tool_args if isinstance(tool_args, Mapping) else {}
        tool_call = ToolCallInfo(
            tool_name=tool_name,
            args=mapped_args,
            tool_call_id=str(uuid4()),
        )

        decision = await self._pipeline.before_tool_use(tool_call)
        if decision.kind == "deny":
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": decision.reason or "Denied by pipeline.",
            }

        if decision.kind == "ask":
            approved = await self._interaction_broker.request_decision(tool_call)
            if not approved:
                return {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Denied by pipeline authority.",
                }

        return {"permissionDecision": "allow"}

    async def on_post_tool_use(
        self,
        hook_input: PostToolUseHookInput,
        args: dict[str, str],
    ) -> PostToolUseHookOutput | None:
        del args
        tool_name = hook_input.get("toolName") or "unknown"
        tool_args = hook_input.get("toolArgs")
        mapped_args = tool_args if isinstance(tool_args, Mapping) else {}
        raw_result = hook_input.get("toolResult")
        result = ToolResult(success=True, content=str(raw_result), error=None)

        tool_call = ToolCallInfo(
            tool_name=tool_name,
            args=mapped_args,
            tool_call_id=str(uuid4()),
        )
        piped_result = await self._pipeline.after_tool_use(tool_call, result)
        return {"modifiedResult": piped_result.content}


class GhToolPipelineSession(AgentSessionProtocol):
    def __init__(
        self,
        session: CopilotSession,
        interaction_broker: HookInteractionBroker,
        pipeline: ToolPipeline,
    ) -> None:
        self._session = session
        self._interaction_broker = interaction_broker
        self._pipeline = pipeline
        self._event_queue: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._history: list[Any] = []
        self._run_active = False
        self._tool_calls_by_id: dict[str, ToolCallInfo] = {}

        def _on_event(event: SessionEvent) -> None:
            self._event_queue.put_nowait(event)

        self._session.on(_on_event)

    @property
    def history(self) -> tuple[Any, ...]:
        return tuple(self._history)

    def run(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> AgentEventStream:
        return self._run_impl(prompt=prompt, cancellation_event=cancellation_event)

    async def _run_impl(
        self,
        prompt: str,
        cancellation_event: asyncio.Event | None,
    ) -> AgentEventStream:
        if self._run_active:
            raise RuntimeError("Only one active run is allowed per session.")

        self._run_active = True
        self._history.append({"role": "user", "content": prompt})

        event_task: asyncio.Task[SessionEvent] | None = None
        interaction_task: asyncio.Task[
            tuple[ToolPipelineInteractionRequest, asyncio.Future[bool]]
        ] | None = None

        try:
            await self._session.send({"prompt": prompt})

            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    return

                if event_task is None:
                    event_task = asyncio.create_task(self._event_queue.get())
                if interaction_task is None:
                    interaction_task = asyncio.create_task(
                        self._interaction_broker.next_request()
                    )

                done, _ = await asyncio.wait(
                    {event_task, interaction_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if interaction_task in done:
                    request, future = interaction_task.result()
                    interaction_task = None

                    response = cast(ToolPipelineInteractionResponse | None, (yield request))
                    if response is None:
                        future.set_result(False)
                        return
                    if response.request_id != request.request_id:
                        raise ValueError(
                            "Interaction response request_id does not match request."
                        )

                    tool_call = request.tool_calls[0]
                    decision = self._pipeline.resolve_interaction_response(
                        tool_call,
                        response,
                    )
                    future.set_result(decision.kind == "allow")
                    continue

                if event_task in done:
                    event = event_task.result()
                    event_task = None

                    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                        delta = getattr(event.data, "delta_content", "") or ""
                        if delta:
                            yield AgentChunk(content=delta, is_thought=False)
                        continue

                    if event.type == SessionEventType.ASSISTANT_REASONING_DELTA:
                        delta = getattr(event.data, "delta_content", "") or ""
                        if delta:
                            yield AgentChunk(content=delta, is_thought=True)
                        continue

                    if event.type == SessionEventType.TOOL_EXECUTION_START:
                        tool_name = getattr(event.data, "tool_name", None) or "unknown"
                        if tool_name != "report_intent":
                            tool_call = ToolCallInfo(
                                tool_name=tool_name,
                                args=_to_mapping(getattr(event.data, "arguments", {})),
                                tool_call_id=(
                                    getattr(event.data, "tool_call_id", None)
                                    or str(uuid4())
                                ),
                            )
                            self._tool_calls_by_id[tool_call.tool_call_id] = tool_call
                            yield tool_call
                        continue

                    if event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
                        tool_call_id = getattr(event.data, "tool_call_id", None) or str(uuid4())
                        success = bool(getattr(event.data, "success", False))
                        content = str(getattr(event.data, "result", "") or "")
                        error_value = getattr(event.data, "error", None)
                        error_text = str(error_value) if error_value else None

                        tool_call = self._tool_calls_by_id.get(
                            tool_call_id,
                            ToolCallInfo(
                                tool_name="unknown",
                                args={},
                                tool_call_id=tool_call_id,
                            ),
                        )
                        result = ToolResult(
                            success=success,
                            content=content,
                            error=error_text,
                        )
                        piped_result = await self._pipeline.after_tool_use(tool_call, result)
                        self._tool_calls_by_id.pop(tool_call_id, None)
                        yield ToolCallResultInfo(
                            tool_call_id=tool_call_id,
                            result=piped_result,
                        )
                        continue

                    if event.type == SessionEventType.SESSION_IDLE:
                        self._history.append({"role": "assistant", "content": "<session idle>"})
                        yield AgentDone()
                        return
        finally:
            self._run_active = False
            if event_task is not None:
                event_task.cancel()
            if interaction_task is not None:
                interaction_task.cancel()


CopilotSessionConfigBuilder = Callable[
    [SessionConfig, SessionHooks],
    CopilotSessionConfig,
]


class CopilotToolPipelineFactory(SessionFactoryProtocol):
    def __init__(
        self,
        client: CopilotClient,
        pipeline: ToolPipeline,
        session_config_builder: CopilotSessionConfigBuilder,
    ) -> None:
        self._client = client
        self._pipeline = pipeline
        self._session_config_builder = session_config_builder

    async def create_session(self, config: SessionConfig) -> AgentSessionProtocol:
        interaction_broker = HookInteractionBroker(self._pipeline)
        hooks_adapter = CopilotToolHooks(self._pipeline, interaction_broker)
        hooks: SessionHooks = {
            "on_pre_tool_use": hooks_adapter.on_pre_tool_use,
            "on_post_tool_use": hooks_adapter.on_post_tool_use,
        }
        session_config = self._session_config_builder(config, hooks)
        sdk_session = await self._client.create_session(session_config)
        return GhToolPipelineSession(
            sdk_session,
            interaction_broker=interaction_broker,
            pipeline=self._pipeline,
        )
