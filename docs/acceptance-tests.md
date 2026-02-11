# Agent C — Agentic Loop Acceptance Tests

Acceptance tests for the [Agentic Loop Specification](file:///C:/Users/rodhy/.gemini/antigravity/brain/8532ea15-15d0-4693-a1b4-396e25e5aaab/agentic_loop_spec.md), written in Gherkin. These are backend-agnostic — any conforming implementation must pass all scenarios.

---

## Feature 1: Basic Event Streaming

> Spec references: §2.1, §2.4, §4.1, Appendix B

```gherkin
Feature: Basic Event Streaming
  The loop streams AgentChunk events and terminates with AgentDone.

  Scenario: Simple text response
    Given a session with no tools registered
    When the user sends "Hello"
    Then the loop yields one or more AgentChunk events
    And each AgentChunk has is_thought = false
    And the concatenated content forms a coherent response
    And the final event is AgentDone
    And no further events are yielded after AgentDone

  Scenario: Thinking tokens
    Given a session using a model that emits thinking tokens
    When the user sends "Solve 2+2"
    Then the loop yields AgentChunk events with is_thought = true
    And the loop yields AgentChunk events with is_thought = false
    And all thinking chunks precede the first non-thinking chunk
    And the final event is AgentDone

  Scenario: Empty response
    Given a session with no tools registered
    When the LLM produces no content
    Then the loop yields AgentDone
    And no AgentChunk events are yielded
```

---

## Feature 2: Tool Execution

> Spec references: §2.2, §2.3, Appendix B

```gherkin
Feature: Tool Execution
  The loop yields ToolCallInfo before execution and ToolCallResultInfo after.

  Scenario: Successful tool call
    Given a session with a tool "read_file" that returns "file contents"
    When the user sends "Read the file foo.txt"
    And the LLM invokes tool "read_file" with args {"path": "foo.txt"}
    Then the loop yields a ToolCallInfo with tool_name = "read_file"
    And the ToolCallInfo has args as a read-only Mapping
    And the ToolCallInfo has a non-empty tool_call_id
    Then the loop yields a ToolCallResultInfo with the same tool_call_id
    And the ToolResult has success = true
    And the ToolResult has content = "file contents"
    And the final event is AgentDone

  Scenario: Tool execution failure
    Given a session with a tool "read_file" that raises an exception
    When the LLM invokes tool "read_file"
    Then the loop yields a ToolCallInfo
    Then the loop yields a ToolCallResultInfo with same tool_call_id
    And the ToolResult has success = false
    And the ToolResult has a non-empty error message
    And the final event is AgentDone

  Scenario: Multiple tool calls
    Given a session with tools "read_file" and "list_dir"
    When the LLM invokes both tools in sequence
    Then the loop yields ToolCallInfo for "read_file"
    And the loop yields ToolCallResultInfo for "read_file"
    And the loop yields ToolCallInfo for "list_dir"
    And the loop yields ToolCallResultInfo for "list_dir"
    And every ToolCallInfo precedes its matching ToolCallResultInfo

  Scenario: Tool args are immutable
    Given a session with a tool "write_file"
    When the LLM invokes "write_file" with args {"path": "a.txt", "content": "hi"}
    Then the yielded ToolCallInfo has args of type Mapping[str, Any]
    And attempting to mutate the args raises an error or is not possible
```

---

## Feature 3: Notifications

> Spec references: §2.4, Appendix B

```gherkin
Feature: Notifications
  The loop can emit unidirectional status messages that require no response.

  Scenario: Info notification
    Given a session that emits a progress notification
    When the backend yields Notification(message="Searching 1,432 files...", severity=INFO)
    Then the consumer receives a Notification event
    And the Notification has message = "Searching 1,432 files..."
    And the Notification has severity = INFO
    And no response is sent back via asend

  Scenario: Warning notification
    Given a session that encounters a transient issue
    When the backend yields Notification(message="Rate limited, retrying in 5s...", severity=WARNING)
    Then the consumer receives the Notification
    And the adapter displays it with warning-level styling
    And the loop continues streaming normally

  Scenario: Error notification
    Given a session that encounters a non-fatal error
    When the backend yields Notification(message="Failed to load cache", severity=ERROR)
    Then the consumer receives the Notification
    And the loop does not terminate (unlike a propagated exception)
    And the final event is AgentDone

  Scenario: Notifications interleaved with streaming
    Given a session
    When the backend yields AgentChunk, then Notification, then AgentChunk
    Then all three events are received in order
    And the Notification does not disrupt the text stream
    And the final event is AgentDone

  Scenario: Notifications pass through middleware
    Given the DebouncingMiddleware
    When the event stream contains a Notification
    Then the middleware passes it through without buffering
    And any buffered AgentChunks are not flushed by the Notification

  Scenario: Multiple notifications in one turn
    Given a session
    When the backend yields three Notifications with different messages
    Then all three are received by the consumer in order
    And each has the correct message and severity
```

---

## Feature 4: Approval Handshake

> Spec references: §3.2, §5.1, §6

```gherkin
Feature: Approval Handshake
  Tools flagged as requiring approval trigger an ApprovalRequest before execution.

  Scenario: User approves tool execution
    Given a session with a tool "delete_file" that requires approval
    When the LLM invokes "delete_file" with args {"path": "foo.txt"}
    Then the loop yields an ApprovalRequest
    And the ApprovalRequest contains a ToolCallInfo for "delete_file"
    And the ApprovalRequest has a non-empty request_id
    When the consumer sends an ApprovalResponse with approved = true
    Then the tool executes
    And the loop yields a ToolCallResultInfo with success = true
    And the LLM receives the tool result and may produce further output
    And the final event is AgentDone

  Scenario: User denies tool execution
    Given a session with a tool "delete_file" that requires approval
    When the LLM invokes "delete_file"
    Then the loop yields an ApprovalRequest
    When the consumer sends ApprovalResponse with approved = false, reason = "Too risky"
    Then the tool does not execute
    And the LLM receives the denial reason as a tool error
    And the LLM may produce a text response acknowledging the denial
    And the final event is AgentDone

  Scenario: Consumer disconnects during approval
    Given a session with a tool "delete_file" that requires approval
    When the LLM invokes "delete_file"
    Then the loop yields an ApprovalRequest
    When the consumer sends None instead of an ApprovalResponse
    Then the loop terminates immediately
    And no AgentDone is yielded

  Scenario: Multiple approval rounds in one turn
    Given a session with a tool "delete_file" that requires approval
    When the LLM invokes "delete_file" and the user approves
    And the LLM then invokes "delete_file" again with different args
    Then the loop yields a second ApprovalRequest
    When the user approves the second request
    Then the tool executes again
    And the final event is AgentDone

  Scenario: Mix of approved and non-approved tools
    Given a session with tool "read_file" (no approval) and "delete_file" (requires approval)
    When the LLM invokes both tools
    Then "read_file" executes immediately and yields ToolCallResultInfo
    And "delete_file" is deferred into an ApprovalRequest
    When the user approves
    Then "delete_file" executes and yields ToolCallResultInfo
```

---

## Feature 5: User Input Flow

> Spec references: §3.3, §5.2, §7, §8

```gherkin
Feature: User Input Flow
  Tools can request user input mid-stream via the broker.

  Scenario: Tool requests and receives user input
    Given a session with a tool that calls request_user_input
    And the tool asks "Which option?" with options ["A", "B"]
    When the LLM invokes the tool
    Then the loop yields a UserInputRequest with question = "Which option?"
    And the UserInputRequest has 2 options
    And the UserInputRequest has a non-empty request_id
    When the consumer sends UserInputResponse with response = "A"
    Then the tool receives the response "A"
    And the tool completes execution
    And the final event is AgentDone

  Scenario: User input arrives concurrently with streaming
    Given a session with a tool that calls request_user_input
    When the LLM begins streaming text and the tool requests input
    Then the loop may yield AgentChunk events before the UserInputRequest
    And the UserInputRequest is yielded when the broker dequeues it
    When the consumer responds
    Then streaming continues
    And the final event is AgentDone

  Scenario: Consumer disconnects during user input
    Given a session with a tool that calls request_user_input
    When the tool requests input
    Then the loop yields a UserInputRequest
    When the consumer sends None instead of a UserInputResponse
    Then the broker resolves the tool's future with an empty response
    And the loop terminates immediately
    And no AgentDone is yielded

  Scenario: Broker wiring
    Given a new session with RunDeps
    Then deps.user_input_handler is set to the session's broker
    And the broker implements the UserInputHandler protocol
```

---

## Feature 6: Cancellation

> Spec reference: §14

```gherkin
Feature: Cancellation
  A cancellation_event causes the loop to terminate without AgentDone.

  Scenario: Cancel before any events
    Given a session
    And a cancellation_event that is already set
    When the user calls run()
    Then the loop returns immediately
    And no events are yielded
    And no AgentDone is yielded

  Scenario: Cancel during streaming
    Given a session
    When the user sends "Tell me a long story"
    And the cancellation_event is set after the first AgentChunk
    Then the loop stops yielding events
    And no AgentDone is yielded
    And all pending asyncio tasks are cancelled

  Scenario: Cancel during approval
    Given a session with a tool that requires approval
    When the LLM invokes the tool
    And the loop yields an ApprovalRequest
    And the cancellation_event is set before the consumer responds
    Then the loop returns without waiting for a response
    And no AgentDone is yielded
```

---

## Feature 7: Error Handling

> Spec reference: §10

```gherkin
Feature: Error Handling
  Errors propagate as exceptions, not as events.

  Scenario: LLM network error
    Given a session where the LLM call raises a ConnectionError
    When the user sends "Hello"
    Then the generator raises ConnectionError
    And no AgentDone is yielded

  Scenario: LLM authentication error
    Given a session with an invalid API key
    When the user sends "Hello"
    Then the generator raises an authentication-related exception
    And no AgentDone is yielded

  Scenario: Tool error is captured in ToolResult
    Given a session with a tool that raises ValueError("bad input")
    When the LLM invokes the tool
    Then the loop yields ToolCallResultInfo with success = false
    And the ToolResult.error contains "bad input"
    And the loop continues normally (LLM sees the error)
    And the final event is AgentDone

  Scenario: No AgentDone on abnormal exit
    Given any error scenario
    When the loop exits due to an exception
    Then AgentDone is never yielded before the exception propagates
```

---

## Feature 8: History Management

> Spec references: §4.1, §15

```gherkin
Feature: History Management
  The session maintains conversation history across turns.

  Scenario: History persists across turns
    Given a session
    When the user sends "My name is Alice"
    And the turn completes with AgentDone
    And the user sends "What is my name?"
    Then the LLM has access to the previous conversation
    And the response references "Alice"

  Scenario: History accessible via property
    Given a session that has completed one turn
    Then session.history returns a non-None value
    And session.history is backend-specific (opaque)

  Scenario: Clear history via session factory
    Given a session that has completed several turns
    When create_session is called with clear_history = true
    Then the new session has empty history
    And the LLM has no memory of prior turns

  Scenario: History updated after approval round-trip
    Given a session with a tool that requires approval
    When the LLM invokes the tool and the user approves
    Then the session's internal history includes the tool call and result
    And the next turn has access to this history
```

---

## Feature 9: Interaction Protocol Extensibility

> Spec references: §3.1, §3.4, §5.3

```gherkin
Feature: Interaction Protocol Extensibility
  New interaction types extend the base without changing the stream contract.

  Scenario: Custom interaction type
    Given a new interaction type FilePickerRequest extending InteractionRequest
    And a new response type FilePickerResponse extending InteractionResponse
    When the loop yields a FilePickerRequest
    Then the middleware forwards it without modification
    And the middleware flushes buffers before forwarding
    And the consumer receives it as an InteractionRequest subtype
    When the consumer sends a FilePickerResponse via asend
    Then the loop receives it as an InteractionResponse subtype

  Scenario: Middleware handles unknown interaction types generically
    Given the DebouncingMiddleware
    And a new InteractionRequest subtype it has never seen
    When the new request arrives in the event stream
    Then the middleware flushes all buffers
    And forwards the request via yield
    And relays the response back via asend
    And no code changes were required in the middleware

  Scenario: Event union covers subtypes
    Given the type AgentEvent includes InteractionRequest
    When a new subtype of InteractionRequest is created
    Then it is automatically a valid AgentEvent
    And the AgentEventStream type signature does not change
```

---

## Feature 10: Concurrency Guard

> Spec reference: §11

```gherkin
Feature: Concurrency Guard
  Only one run() may be active per session at a time.

  Scenario: Second run() while first is active
    Given a session with an active run() that is still yielding events
    When run() is called a second time
    Then a RuntimeError is raised
    And the first run() is not affected

  Scenario: Sequential runs are allowed
    Given a session
    When run() completes with AgentDone
    And run() is called again with a new prompt
    Then the second run() proceeds normally
    And events stream as expected
```

---

## Feature 11: Backpressure

> Spec reference: §12

```gherkin
Feature: Backpressure
  The loop does not produce events faster than the consumer can process them.

  Scenario: Slow consumer does not cause event loss
    Given a session
    And a consumer that delays 100ms between each asend/anext call
    When the user sends a prompt
    Then every event is received by the consumer
    And no events are dropped or buffered internally
    And the order of events matches the production order

  Scenario: No unbounded internal queue
    Given a session producing many AgentChunk events
    When the consumer has not yet called anext
    Then the loop is suspended at the yield point
    And at most one event is buffered (the one being yielded)
```
