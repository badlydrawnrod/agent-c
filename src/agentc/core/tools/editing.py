"""File editing and patching tools for Agent C.

Provides tools for reading, creating, editing files, and applying
structured patches with atomic writes and transactional guarantees.
"""

from dataclasses import asdict
import json
from pathlib import Path

from pydantic_ai import ModelRetry

from ._shared import resolve_path, RunContext, RunDeps, ToolResult
from ..config import BACKUP_SUFFIX, TEMP_SUFFIX
from ..patching.engine import apply_file_patch
from ..patching.errors import PatchTransactionError
from ..patching.transaction import (
    apply_updates_transactionally,
    create_backup,
    write_text_atomic,
)
from ..types import FilePatchResult, PatchApplySummary, PatchPlan


def _cat_n_format(text: str) -> str:
    """Return text with `cat -n` style line numbers, preserving trailing newline."""
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")
    numbered = [f"{i:6}\t{line}" for i, line in enumerate(lines, 1)]
    result = "\n".join(numbered)
    if trailing_newline:
        result += "\n"
    return result


def _serialize_patch_summary(summary: PatchApplySummary) -> str:
    """Serialize patch summary to JSON for tool output."""
    return json.dumps(asdict(summary), ensure_ascii=True)


def read_file(ctx: RunContext[RunDeps], path: str) -> ToolResult:
    """Read a UTF-8 text file and return cat -n style output.

    - Path must be inside the current working directory and must be a file; directories are rejected.
    - Output is line-numbered like `cat -n` (right-aligned 6-digit number, tab, then content); trailing newline is preserved.
    - Raises ModelRetry for invalid paths, directories, or non-UTF-8 content.
    """
    try:
        target = resolve_path(path, ctx.deps)
        if target.is_dir():
            raise ModelRetry(f"Path must be a file, not a directory: {path}")

        content = target.read_text(encoding="utf-8")
        return ToolResult(success=True, content=_cat_n_format(content))
    except UnicodeDecodeError:
        raise ModelRetry(f"File must be UTF-8 encoded text: {path}")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def create_file(ctx: RunContext[RunDeps], path: str, content: str) -> ToolResult:
    """Create a new file with the given content.

    - Path must be inside currently working directory.
    - Path must NOT exist (use edit_file to modify existing files).
    - Creates parent directories if needed.
    - Writes atomically via a temp file.
    """
    try:
        target = resolve_path(path, ctx.deps, must_exist=False)
        if target.exists():
            raise ModelRetry(
                f"File already exists: {path}. Use edit_file to modify it."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(target, content, temp_suffix=TEMP_SUFFIX)
        return ToolResult(success=True, content="File created successfully")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def edit_file(
    ctx: RunContext[RunDeps], path: str, old_str: str, new_str: str
) -> ToolResult:
    """Replace a unique occurrence of old_str with new_str in a UTF-8 text file.

    Use this tool for making a SINGLE edit to a file. For making multiple
    non-contiguous edits to the same file, use `apply_hunks` instead — it's
    more efficient (single tool call) and atomic (all changes succeed or none apply).

    - Path must be inside the current working directory and must be a file; directories are rejected.
    - The file must decode as UTF-8; otherwise ModelRetry is raised.
    - old_str must appear exactly once; otherwise ModelRetry is raised requesting more context.
    - A timestamped backup is created alongside the file before writing; writes are atomic via temp file.
    - Returns a short success or error message; on error, backup name is included when available.
    """
    try:
        target = resolve_path(path, ctx.deps)
        if target.is_dir():
            raise ModelRetry(f"Path must be a file, not a directory: {path}")

        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ModelRetry(f"File must be UTF-8 encoded text: {path}")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))

    occurrences = content.count(old_str)
    if occurrences == 0:
        raise ModelRetry("old_str not found in file")
    if occurrences > 1:
        raise ModelRetry(
            "old_str appears multiple times; provide more context to match uniquely"
        )

    backup_path = create_backup(target, backup_suffix=BACKUP_SUFFIX)

    try:
        new_content = content.replace(old_str, new_str, 1)
        write_text_atomic(target, new_content, temp_suffix=TEMP_SUFFIX)
        return ToolResult(success=True, content="Edit completed successfully")
    except Exception as e:
        return ToolResult(
            success=False, content="", error=f"{e}. Backup saved to {backup_path.name}"
        )


def apply_hunks(ctx: RunContext[RunDeps], plan: PatchPlan) -> ToolResult:
    """Apply structured patch hunks to one or more files atomically.

    IMPORTANT: Before using this tool, ALWAYS use `read_file` to see the exact
    file contents. Lines must match EXACTLY — including heading levels (e.g.,
    `##` vs `###`), whitespace, punctuation, and spelling. Even small mismatches
    will cause the hunk to fail with "No match found".

    The plan contains a list of FilePatch objects, each targeting a file with one
    or more hunks. All hunks must match successfully or no files are modified.

    Each hunk specifies:
    - anchor_before: Lines that must appear immediately before the edit location.
    - remove: Lines to be deleted (must match the file content EXACTLY).
    - add: Lines to insert in place of the removed lines.
    - anchor_after: Lines that must appear immediately after the removed lines.
    - expected_near_line: Optional 1-based line number hint to disambiguate when
      the anchor+remove+anchor pattern appears multiple times in the file.
    - match_options: Optional matching behavior (e.g., ignore_trailing_whitespace).

    The full match sequence is: anchor_before + remove + anchor_after. If found
    exactly once (or disambiguated by expected_near_line), remove is replaced
    with add. Anchors are preserved.

    To insert lines without removing any, set remove to an empty list.
    To delete lines without inserting, set add to an empty list.

    Structure (note the exact field names):
    - PatchPlan has field `files`: list of FilePatch
    - FilePatch has fields `path` and `hunks` (NOT 'patches')
    - Each PatchHunk has: anchor_before, remove, add, anchor_after, expected_near_line

    Example:
        {
            "files": [{
                "path": "/absolute/path/to/file.py",
                "hunks": [{
                    "anchor_before": ["def foo():"],
                    "remove": ["    old_line"],
                    "add": ["    new_line"],
                    "anchor_after": ["    return result"]
                }]
            }]
        }

    All paths must be absolute and inside the allowed working directories.
    Files must exist and be UTF-8 encoded text.
    Backups are created before each write; writes are atomic via temp files.
    """
    if not plan.files:
        raise ModelRetry("No patch files provided")

    pending_updates: dict[Path, str] = {}
    file_results: list[FilePatchResult] = []

    for file_patch in plan.files:
        if not file_patch.hunks:
            raise ModelRetry(f"No hunks provided for file: {file_patch.path}")
        try:
            target = resolve_path(file_patch.path, ctx.deps)
            if target.is_dir():
                raise ModelRetry(
                    f"Path must be a file, not a directory: {file_patch.path}"
                )
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ModelRetry(f"File must be UTF-8 encoded text: {file_patch.path}")
        except ModelRetry:
            raise
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))

        updated_content, result = apply_file_patch(file_patch, content)
        file_results.append(result)
        if not result.applied:
            summary = PatchApplySummary(applied=False, files=file_results)
            return ToolResult(
                success=False,
                content=_serialize_patch_summary(summary),
                error=f"Patch failed for {file_patch.path}: {result.error}",
            )

        pending_updates[target] = updated_content

    try:
        apply_updates_transactionally(
            pending_updates,
            backup_suffix=BACKUP_SUFFIX,
            temp_suffix=TEMP_SUFFIX,
        )
        summary = PatchApplySummary(applied=True, files=file_results)
        return ToolResult(success=True, content=_serialize_patch_summary(summary))
    except PatchTransactionError as exc:
        summary = PatchApplySummary(applied=False, files=file_results)
        return ToolResult(
            success=False,
            content=_serialize_patch_summary(summary),
            error=str(exc),
        )


__all__ = ["read_file", "create_file", "edit_file", "apply_hunks"]
