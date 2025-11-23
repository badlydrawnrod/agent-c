import re

from pydantic_ai import ModelRetry, RunContext

from ..file_ops import (
    cleanup_old_backups,
    create_backup,
    safe_resolve,
    safe_resolve_create,
    write_and_verify,
)
from ..types import RunDeps


def _cat_n_format(text: str) -> str:
    """Return `text` with `cat -n` style line numbers.

    Each line is prefixed with a right-aligned 6-character line number
    followed by a tab, matching the typical `cat -n` output.
    """
    lines = text.splitlines()
    # Preserve a trailing newline if present on the original text
    trailing_newline = text.endswith("\n")
    numbered = [f"{i:6}\t{line.rstrip()}" for i, line in enumerate(lines, 1)]
    result = "\n".join(numbered)
    if trailing_newline:
        result += "\n"
    return result


def read_file(ctx: RunContext[RunDeps], path: str) -> str:
    """Read the contents of a text file and return cat -n style output.

    Usage:
    - The output will be numbered like `cat -n` (leading line numbers, tab,
      then line text).
    - If the file cannot be decoded as UTF-8 it will raise `ModelRetry`
      indicating the path must be a text file.
    """
    ctx.deps.info(f"Reading file: {path}")
    resolved_path = safe_resolve(path)
    if not resolved_path.is_file():
        raise ModelRetry("Path must be a file")
    try:
        text = resolved_path.read_text(encoding="utf-8")
    except Exception:
        # Can't decode as text - treat as non-text/binary for tools
        raise ModelRetry("Path must be a text file")

    return _cat_n_format(text)


def list_files(ctx: RunContext[RunDeps], path: str) -> str:
    """List files in the specified directory."""
    ctx.deps.info(f"Listing files in: {path}")
    resolved_path = safe_resolve(path)
    if not resolved_path.is_dir():
        raise ModelRetry("Path must be a directory")
    return "\n".join(sorted(p.name for p in resolved_path.iterdir()))


def edit_file(ctx: RunContext[RunDeps], path: str, old_str: str, new_str: str) -> str:
    """Edit a file by replacing old_str with new_str.

    Usage:
    - You must use the `read_file` tool at least once in the conversation
      before editing. The tool will error if you attempt an edit without
      reading the file first.
    - When editing text from `read_file` tool output, ensure you preserve
      the exact indentation (tabs/spaces) as it appears AFTER the line
      number prefix. The line number prefix format is: spaces + line number
      + tab. Everything after that tab is the actual file content to match.
      Never include any part of the line number prefix in old_str or new_str.
    - old_str must be unique in the file. If the string appears multiple
      times, provide a larger string with more surrounding context to make
      it unique, or you can ask the user for clarification.
    - Always preserve the exact formatting and indentation of the original
      code when making replacements.
    """
    ctx.deps.info(f"Editing file: {path}")
    resolved_path = safe_resolve(path)
    if not resolved_path.is_file():
        raise ModelRetry("Path must be a file")

    # Read original.
    content = resolved_path.read_text(encoding="utf-8")
    occurrence_count = content.count(old_str)
    if occurrence_count == 0:
        raise ModelRetry("old_str not found in file")
    if occurrence_count > 1:
        raise ModelRetry(
            f"old_str appears {occurrence_count} times; provide more context to match uniquely"
        )

    # Create backup BEFORE modification.
    backup_path = create_backup(resolved_path)
    ctx.deps.info(f"Backup created: {backup_path.name}")

    try:
        # Calculate new content.
        new_content = content.replace(old_str, new_str)

        # Write and verify atomically.
        write_and_verify(resolved_path, new_content)

        # Clean up old backups (keep last 5).
        cleanup_old_backups(resolved_path)

        return "Edit completed successfully"
    except Exception as e:
        ctx.deps.info(f"Edit failed, backup available at {backup_path.name}")
        raise ModelRetry(f"Failed to edit file: {e}")


def create_file(ctx: RunContext[RunDeps], path: str, content: str) -> str:
    """Create a new file with the given content, creating parent directories if needed."""
    ctx.deps.info(f"Creating file: {path}")
    resolved_path = safe_resolve_create(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    # Create backup if file already exists.
    if resolved_path.exists():
        backup_path = create_backup(resolved_path)
        ctx.deps.info(f"Existing file backed up: {backup_path.name}")

    try:
        # Write and verify atomically.
        write_and_verify(resolved_path, content)
        return "File created successfully"
    except Exception as e:
        ctx.deps.info("File creation failed")
        raise ModelRetry(f"Failed to create file: {e}")


def search_files(ctx: RunContext[RunDeps], path: str, query: str) -> str:
    """Recursively search for a query string in files within a given path."""
    resolved_path = safe_resolve(path)
    if not resolved_path.is_dir():
        raise ModelRetry("Path must be a directory")
    results = []
    for file_path in resolved_path.rglob("*"):
        if file_path.is_file():
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if query in line:
                        results.append(f"{file_path}:{line_num}: {line.strip()}")
    return "\n".join(results)
