---
name: class-diagram
description: Generate an interactive class diagram visualization from Python source files. Use when exploring class relationships, understanding inheritance hierarchies, or documenting object-oriented architecture.
allowed-tools: Bash(python *)
---

# Class Diagram Generator

Generate an interactive HTML visualization showing class hierarchies, inheritance relationships, and class members from Python source files.

## Usage

Run the class diagram generator from your project root or any directory:

```bash
python .github/skills/class-diagram/scripts/generate_class_diagram.py [path]
```

If no path is provided, it scans the current directory.

This creates `class-diagram.html` in the current directory and opens it in your default browser.

## What the visualization shows

- **Class boxes**: Each class with its methods and attributes
- **Inheritance arrows**: Visual connections showing parent-child relationships
- **Protocols/ABCs**: Highlighted differently from concrete classes
- **Interactive**: Click and drag to rearrange classes
- **Zoom/Pan**: Navigate large class hierarchies

## When to Use

- Exploring a new codebase's architecture
- Understanding class relationships
- Documenting OOP design
- Identifying inheritance patterns
- Code reviews and architecture discussions

## Example

```bash
# Analyze the entire agentc package
python .github/skills/class-diagram/scripts/generate_class_diagram.py src/agentc

# Analyze a specific module
python .github/skills/class-diagram/scripts/generate_class_diagram.py src/agentc/core
```
