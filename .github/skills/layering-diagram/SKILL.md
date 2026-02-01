---
name: layering-diagram
description: Generate an SVG diagram showing the architectural layering of the codebase. Use this to understand the high-level architecture and dependencies between layers.
allowed-tools: Bash
---

# Layering Diagram Generator

Generates a visual SVG diagram of the codebase's architectural layering.

## Instructions for the Agent

1.  **Analyze the Codebase**:
    *   Explore the project structure (directories and files) to identify Key Architectural Layers. Look for patterns like:
        *   **Presentation/Interface**: `api`, `web`, `cli`, `entrypoints`, `ui`.
        *   **Application/Service**: `services`, `usecases`, `workflows`, `orchestration`.
        *   **Domain/Core**: `core`, `models`, `entities`, `logic`, `domain`.
        *   **Infrastructure/Data**: `db`, `repositories`, `adapters`, `external`, `backends`.
    *   Note the dependencies between these layers (who imports whom).

2.  **Generate SVG**:
    *   Create a clean, professional SVG diagram.
    *   Use **boxes** to represent layers and **arrows** to represent functional dependencies.
    *   **Group** related modules into standard architectural layers (e.g., "Presentation Layer", "Core Layer", "Infrastructure Layer").
    *   Use distinct **colors** for different layers to improve readability.
    *   Ensure the text is legible and the layout is balanced.
    *   **IMPORTANT**: You MUST escape special characters in text labels. For example, convert `&` to `&amp;`, `<` to `&lt;`, and `>` to `&gt;`. Failure to do this will break the SVG.

3.  **Save the File**:
    *   Write the SVG content to a file named `layering-diagram.svg` in the current directory.

4.  **Visualize**:
    *   **Immediately after saving**, run the following command to open the diagram in the user's browser:
        ```bash
        python -c "import webbrowser, os; webbrowser.open('file://' + os.path.abspath('layering-diagram.svg'))"
        ```

## Example Prompt

"Generate a layering diagram of this repository to show me the architecture."
