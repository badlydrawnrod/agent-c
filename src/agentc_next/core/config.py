"""
Configuration constants for Agent C Next.

Centralizes system-level magic numbers, limits, and file suffixes.
This module must remain agnostic of any specific UI implementation.
"""

# Tool execution limits
# Maximum number of entries returned by glob or search to prevent flooding
MAX_TOOL_OUTPUT_LINES: int = 200

# File operations
BACKUP_SUFFIX: str = ".bak"
TEMP_SUFFIX: str = ".tmp"

# Default skill discovery paths
DEFAULT_SKILL_DIRS: list[str] = [".github/skills", ".claude/skills"]

# Default ignore patterns for file discovery (glob, search)
DEFAULT_IGNORE_PATTERNS: list[str] = [
    ".git/",
    "__pycache__/",
    "*.pyc",
    ".venv/",
    "node_modules/",
    ".DS_Store",
]
