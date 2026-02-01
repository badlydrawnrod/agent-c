---
name: dependency-mapper
description: Visualize C++ physical dependencies by analyzing #include directives. Use this to identify include cycles, tight coupling, and unnecessary dependencies.
allowed-tools: Bash
---

# C++ Dependency Mapper

Generates a visual SVG dependency graph by analyzing `#include` directives in C++ source files.

## Instructions for the Agent

1.  **Analyze C++ Files**:
    *   Scan the provided directory (and subdirectories) for C++ files: `.h`, `.hpp`, `.cc`, `.cpp`, `.cxx`.
    *   **Parse Includes**: For each file, extract all `#include` directives:
        *   Local includes: `#include "header.h"`
        *   System includes: `#include <vector>`
    *   **Build Graph**: 
        *   Nodes = Files (use relative paths from the scan root)
        *   Edges = Include relationships (File A includes File B)
        *   Track both local and system includes separately

2.  **Generate SVG**:
    *   **Aesthetics**: Create a "Premium" and "State of the Art" diagram.
        *   **Background**: Use a dark, professional background (e.g., `#0d1117`).
        *   **Layout**: Use a directed graph layout (hierarchical or force-directed).
    *   **Nodes (Files)**:
        *   **Color Coding**:
            *   Headers (`.h`, `.hpp`): Blue tones
            *   Source files (`.cc`, `.cpp`): Green tones
            *   System headers (`<...>`): Gray/dimmed (optional: can be excluded for clarity)
        *   Display filename (not full path) in the node
    *   **Edges (Includes)**:
        *   Use arrows pointing from includer to included file
        *   **Highlight Cycles**: If circular dependencies are detected, highlight those edges in red or orange
    *   **IMPORTANT**: Escape special characters in text labels (e.g., `&` -> `&amp;`).

3.  **Save and Open**:
    *   Save the SVG to `cpp-dependencies.svg`.
    *   **Immediately** open it in the browser:
        ```bash
        python -c "import webbrowser, os; webbrowser.open('file://' + os.path.abspath('cpp-dependencies.svg'))"
        ```

## Example Prompt

"Map the C++ dependencies in the `src` directory."
