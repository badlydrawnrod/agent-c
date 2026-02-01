---
name: dependency-inversion-finder
description: Identify Dependency Inversion Principle violations in C++ code and suggest interface-based refactorings to improve modularity and testability.
allowed-tools: Bash
---

# Dependency Inversion Finder

Analyzes C++ code to find violations of the Dependency Inversion Principle and suggests how to introduce abstractions for better modularity.

## Instructions for the Agent

1.  **Scan for Concrete Dependencies**:
    *   Look for classes that depend on concrete implementations rather than abstractions
    *   **Patterns to identify**:
        *   Direct instantiation: `new FileLogger()`, `MySQLDatabase db;`
        *   Member variables of concrete types: `FileLogger* logger;`
        *   Function parameters using concrete types: `void process(MySQLDatabase* db)`
        *   Hard-coded type names in factory methods

2.  **Classify Violations**:
    *   **High → Low**: High-level business logic depending on low-level infrastructure (e.g., `GameEngine` → `FileLogger`)
    *   **Tight Coupling**: Classes that can't be tested in isolation due to hard dependencies
    *   **Inflexibility**: Code that can't swap implementations without modification

3.  **Suggest Abstractions**:
    *   For each violation, propose:
        *   **Interface Name**: Following C++ conventions (e.g., `ILogger`, `IDatabase`)
        *   **Method Signatures**: Pure virtual methods based on how the concrete class is used
        *   **Implementation Classes**: Which concrete classes should implement this interface
        *   **Injection Strategy**: Constructor injection, setter injection, or factory pattern

4.  **Generate Refactoring Report**:
    *   Create a markdown report: `dependency-inversion-report.md`
    *   **Include**:
        *   Summary of violations found
        *   For each violation:
            *   Current code snippet showing the problem
            *   Proposed interface definition
            *   Refactored code example
            *   Benefits (testability, flexibility, modularity)
        *   Prioritization (which violations to fix first)

5.  **Save Report**:
    *   Save to `dependency-inversion-report.md`

## Example Prompt

"Find dependency inversion violations in the `src/engine` directory."
