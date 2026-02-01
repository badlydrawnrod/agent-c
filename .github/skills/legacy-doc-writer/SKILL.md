---
name: legacy-doc-writer
description: Generate high-level architectural documentation and Architecture Decision Records (ADRs) from existing legacy code. Use this to capture the "why" and "how" of a system's design.
allowed-tools: Bash
---

# Legacy Doc Writer

Analyzes C++ codebases to generate high-level architectural overviews and Architecture Decision Records (ADRs) based on the observed implementation.

## Instructions for the Agent

1.  **Analyze Subsystem/Module**:
    *   Scan the target directory to identify the primary responsibility of the code.
    *   Identify key classes, their relationships, and their lifecycle (e.g., how they are created and destroyed).
    *   Look for recurring design patterns (e.g., Singletons, Managers, Factories, Listener/Observer).

2.  **Synthesize Architecture Overview**:
    *   Write a high-level summary of the subsystem.
    *   Document **Key Components** and their specific roles.
    *   Explain the **Data Flow** and **State Management** patterns observed.

3.  **Generate Architecture Decision Records (ADRs)**:
    *   Infer the "intent" behind significant design choices.
    *   Draft an ADR for each major choice (e.g., "Use of a centralized Manager class for Resource Allocation").
    *   **ADR Sections**:
        *   **Title**: Clear name for the decision.
        *   **Context**: What problem was being solved? (Inferred from code).
        *   **Decision**: What was implemented?
        *   **Consequences**: Pros and cons of this approach (e.g., "Simplifies access but creates a God Class").

4.  **Generate Report**:
    *   Create a markdown file: `architecture-overview.md`.
    *   Use clear headings, bullet points, and code snippets where helpful.

5.  **Save Report**:
    *   Save to `architecture-overview.md`.

## Example Prompt

"Generate an architectural overview and ADRs for the `src/storage` subsystem."
