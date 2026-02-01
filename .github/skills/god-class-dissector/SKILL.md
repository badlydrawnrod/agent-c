---
name: god-class-dissector
description: Analyze large C++ classes for cohesion issues and suggest refactoring into smaller, focused classes. Use this to improve modularity in legacy codebases.
allowed-tools: Bash
---

# God Class Dissector

Analyzes large C++ classes to identify low cohesion and suggests how to split them into smaller, more maintainable classes.

## Instructions for the Agent

1.  **Identify Target Class**:
    *   User will specify a class name and file, OR
    *   Scan the codebase for large classes (e.g., >500 LOC, >20 methods, >15 member variables)

2.  **Analyze Class Structure**:
    *   **Extract Members**: Parse the class definition to identify:
        *   All member variables (with types)
        *   All member functions (public, private, protected)
    *   **Build Usage Matrix**: For each function, determine which member variables it accesses
        *   This can be approximate (look for variable names in function body)

3.  **Perform Cohesion Analysis**:
    *   **Cluster Functions**: Group functions that access similar sets of member variables
    *   **Identify Responsibilities**: Based on function names and clusters, infer distinct responsibilities
        *   Example clusters: "Rendering", "Physics", "Network", "Audio", "Resource Management"
    *   **Calculate Metrics**:
        *   LCOM (Lack of Cohesion of Methods) - higher values indicate lower cohesion
        *   Number of distinct clusters found

4.  **Generate Refactoring Report**:
    *   Create a markdown report: `god-class-analysis.md`
    *   **Include**:
        *   Class name and current metrics (LOC, method count, variable count, LCOM)
        *   **Identified Clusters**: For each cluster:
            *   Suggested new class name
            *   List of methods to move
            *   List of member variables to move
        *   **Refactoring Strategy**: Brief explanation of how to split the class
        *   **Optional**: Generate a visual diagram (SVG) showing clusters as colored groups

5.  **Save and Display**:
    *   Save the report to `god-class-analysis.md`
    *   If a diagram was created, open it in the browser

## Example Prompt

"Analyze the `GameManager` class in `src/game/manager.h` for cohesion issues."
