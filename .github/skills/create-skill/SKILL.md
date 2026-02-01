---
name: create-skill
description: Create a new Agent Skill in the .github/skills directory. Use when the user asks to "create a skill" or "add a new capability" to the agent.
allowed-tools: Bash(mkdir), Write
---

# Create Agent Skill

Refactor user requests into a reusable "Skill" that persists in the repository.

## Usage

When a user asks to create a new skill (e.g., "Create a skill to generate SQL diagrams"):

1.  **Plan the Skill**:
    *   **Name**: Kebab-case name (e.g., `sql-diagram`).
    *   **Description**: What it does and *when to use it*.
    *   **Scripts**: Does it need a Python/Bash script? (Put in `scripts/`).

2.  **Create Directory**:
    *   Create the directory: `.github/skills/<skill-name>/`

3.  **Create SKILL.md**:
    *   Create `.github/skills/<skill-name>/SKILL.md` with the required frontmatter.

    ```yaml
    ---
    name: <skill-name>
    description: <description>
    ---

    # <Human Readable Title>

    ## Usage
    ... instructions ...
    ```

4.  **Create Scripts (Optional)**:
    *   If the skill needs code, put it in `.github/skills/<skill-name>/scripts/<script_name>`.
    *   Ensure scripts are standalone and executable.

## Example

**User**: "Make a skill called 'check-links' that checks for broken URLs in markdown files."

**Agent Action**:
1.  **Create Directory**: Execute command to create directory `.github/skills/check-links/scripts`.
2.  **Create SKILL.md**: Write the skill definition to `.github/skills/check-links/SKILL.md`.
3.  **Create Script**: Write the python script to `.github/skills/check-links/scripts/check.py`.

## Agent Skills Specification Reference

### 1. Directory Structure
A skill is a directory containing at minimum a `SKILL.md` file:
```
skill-name/
└── SKILL.md          # Required
```
Optional subdirectories:
- `scripts/`: Executable code (Python, Bash, etc).
- `references/`: Documentation loaded on demand.
- `assets/`: Static resources (templates, images).

### 2. SKILL.md Format
The `SKILL.md` file must contain YAML frontmatter followed by Markdown content.

#### Frontmatter
```yaml
---
name: skill-name
description: A description of what this skill does and when to use it.
allowed-tools: Bash(python *)  # Optional list of pre-approved tools
---
```

**Field Rules**:
- `name`: 1-64 chars, lowercase alphanumeric + hyphens. No consecutive hyphens. Must match directory name.
- `description`: 1-1024 chars. Describe WHAT it does and WHEN to use it.
- `allowed-tools` (Optional): Space-delimited list of tools.

#### Body Content
Markdown instructions for the agent.
- Step-by-step instructions.
- Examples of inputs and outputs.
- Edge cases.
