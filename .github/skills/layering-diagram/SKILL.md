---
name: layering-diagram
description: Generate an SVG diagram showing the architectural layering of the codebase. Use this to understand the high-level architecture and dependencies between layers.
allowed-tools: Bash
---

# Layering Diagram Generator

Generates a visual SVG diagram of the codebase's architectural layering.

## Instructions for the Agent

1.  **Analyze the Codebase**:
    *   **Deep Dive**: Don't just list files. Look inside them.
    *   **Identify Responsibilities**: For each layer, determine its primary responsibility (e.g., "Manages User Input", "Business Logic", "Database Access").
    *   **Key Components**: Inside each module, identify the *most important* Classes, Functions, or Interfaces.
        *   Look for `class` definitions, especially those that implement protocols or abstract base classes.
        *   Look for main entry point functions (e.g., `run()`, `main()`).

2.  **Generate SVG**:
    *   **Aesthetics**: Create a "Premium" and "State of the Art" diagram.
        *   **Background**: Use a dark, professional background (e.g., `#0d1117` or `#1a1b26`).
        *   **Font**: Use a clean, sans-serif font (e.g., 'Segoe UI', 'Roboto', 'Helvetica'). Title should be large and centered.
    *   **Layers (Horizontal Bands)**:
        *   Draw distinct, full-width horizontal bands for each layer.
        *   Use soft, pastel or distinct background colors for each layer band to separate them clearly.
        *   **Add a Subtitle**: Under the layer label, add a small subtitle describing its responsibility (e.g., *Handle HTTP Requests*).
    *   **Modules (Cards)**:
        *   Represent key files or modules as "cards".
        *   **Inside the Card**: List the **Key Classes** or **Functions** found during analysis. Use a separator line or smaller font to list them inside the module box.
        *   Use a white or light background for modules with a subtle drop shadow.
    *   **Connections**:
        *   Use thick, clear arrows to show dependencies.
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
