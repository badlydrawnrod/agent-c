---
name: zip-viewer
description: Generate an interactive collapsible tree visualization of a zip file's contents. Use when you want to explore the contents of a zip archive without extracting it.
allowed-tools: Bash(python *)
---

# Zip Viewer

Generate an interactive HTML tree view that shows the contents of a zip file.

## Usage

Run the visualization script pointing to a zip file:

```bash
python ~/.github/skills/zip-viewer/scripts/visualize_zip.py path/to/archive.zip
```

This creates `zip-content-map.html` in the current directory and opens it in your default browser.

## What the visualization shows

- **Collapsible directories**: Click folders to expand/collapse
- **File sizes**: Displayed next to each file
- **Colors**: Different colors for different file types
- **Directory totals**: Shows aggregate size of each folder
