---
name: spaghetti-detective
description: Trace execution paths through complex C++ code and generate sequence diagrams to understand dynamic behavior. Use this to document complex workflows in legacy code.
allowed-tools: Bash
---

# Spaghetti Detective

Traces execution paths through C++ code and generates Mermaid sequence diagrams to visualize dynamic behavior.

## Instructions for the Agent

1.  **Identify Entry Point**:
    *   User specifies a function to trace (e.g., `GameEngine::OnLogin()`)
    *   Locate the function definition in the codebase

2.  **Trace Execution Path**:
    *   **Parse Function Body**: Identify all function calls within the entry point
    *   **Follow Call Chain**: For each called function:
        *   Determine which object/class it belongs to
        *   Recursively trace its implementation (up to a reasonable depth, e.g., 3-4 levels)
    *   **Track Interactions**: Note which objects call methods on which other objects
    *   **Identify Control Flow**: Look for loops, conditionals, and error handling

3.  **Generate Sequence Diagram**:
    *   Create a Mermaid sequence diagram showing:
        *   **Participants**: Objects/classes involved (e.g., `GameEngine`, `Database`, `Logger`)
        *   **Calls**: Method invocations as arrows (e.g., `GameEngine->>Database: connect()`)
        *   **Returns**: Return values as dashed arrows
        *   **Notes**: Add notes for important logic (e.g., `Note over Database: Validates credentials`)
        *   **Control Flow**: Use `alt`/`else` for conditionals, `loop` for iterations

4.  **Generate Report**:
    *   Create a markdown file: `execution-trace.md`
    *   **Include**:
        *   Summary of the traced function
        *   Mermaid sequence diagram
        *   Key observations (e.g., "Makes 3 database calls", "No error handling")
        *   Suggestions for improvement (if applicable)

5.  **Save Report**:
    *   Save to `execution-trace.md`

## Example Prompt

"Trace the execution of `GameEngine::OnLogin()` and show me a sequence diagram."
