---
name: bazel-dependency-mapper
description: Generate a visual dependency graph from Bazel BUILD files. Use this to understand the build graph and dependencies between targets.
allowed-tools: Bash
---

# Bazel Dependency Mapper

Generates a visual SVG dependency graph by analyzing Bazel `BUILD` files.

## Instructions for the Agent

1.  **Analyze BUILD Files**:
    *   Scan the provided directory (and subdirectories) for `BUILD` or `BUILD.bazel` files.
    *   **Parse Targets**: Look for rules like `cc_library`, `cc_binary`, `py_library`, `java_library`, etc.
    *   **Extract Dependencies**: For each target, look for the `deps` attribute (list of strings).
        *   Resolve relative labels (e.g., `:mylib` -> `//package:mylib`) and absolute labels (`//package:mylib`).
    *   **Construct Graph**: Build a directed graph where Nodes are targets and Edges are dependencies.

2.  **Generate SVG**:
    *   **Aesthetics**: Create a "Premium" and "State of the Art" diagram.
        *   **Background**: Use a dark, professional background (e.g., `#0d1117`).
        *   **Layout**: Use a directed graph layout (e.g., Left-to-Right or Top-to-Bottom).
    *   **Nodes (Targets)**:
        *   Represent targets as styled "cards" or boxes.
        *   **Color Coding**: Use different border colors or subtle background tints for different rule types (e.g., Blue for `cc_library`, Green for `cc_binary`, Yellow for `test`).
        *   **Label**: Display the full label (e.g., `//core:logic`).
    *   **Edges (Dependencies)**:
        *   Use clear, curved or straight connection lines with arrowheads.
        *   Line color should be subtle but visible (e.g., gray or soft blue).
    *   **IMPORTANT**: Escape special characters in text labels (e.g., `&` -> `&amp;`).

3.  **Save and Open**:
    *   Save the SVG to `bazel-graph.svg`.
    *   **Immediately** open it in the browser:
        ```bash
        python -c "import webbrowser, os; webbrowser.open('file://' + os.path.abspath('bazel-graph.svg'))"
        ```

## Example Prompt

"Map the Bazel dependencies in the `src` directory."
