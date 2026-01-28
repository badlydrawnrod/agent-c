"""File editing and patching tools for the Pydantic_AI backend."""

from dataclasses import asdict
import json
from pathlib import Path

from pydantic_ai import ModelRetry

from ._shared import resolve_path, RunContext, RunDeps, ToolResult
from ....config import BACKUP_SUFFIX, TEMP_SUFFIX
from ....patching.engine import apply_file_patch
from ....patching.errors import PatchTransactionError
from ....patching.transaction import (
    apply_updates_transactionally,
    create_backup,
    write_text_atomic,
)
from ....types import FilePatchResult, PatchApplySummary, PatchPlan


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
    """Read a UTF-8 text file and return cat -n style output."""
    try:
        target = resolve_path(path, ctx.deps)
        if target.is_dir():
            raise ModelRetry(f"Path must be a file, not a directory: {path}")

        text = target.read_text(encoding="utf-8")
        content = _cat_n_format(text)
        return ToolResult(success=True, content=content)
    except UnicodeDecodeError:
        # Signal retry so caller can decide how to proceed with binary files
        raise ModelRetry("File is not UTF-8 text")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def create_file(ctx: RunContext[RunDeps], path: str, content: str) -> ToolResult:
    """Create a new file with the given content."""
    try:
        target = resolve_path(path, ctx.deps, must_exist=False)
        if target.exists():
            raise ModelRetry(f"File already exists: {path}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(success=True, content=f"Created file: {path}")
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def edit_file(ctx: RunContext[RunDeps], path: str, find: str, replace: str) -> ToolResult:
    """Replace a unique string occurrence in a file."""
    try:
        target = resolve_path(path, ctx.deps)
        if target.is_dir():
            raise ModelRetry(f"Path must be a file, not a directory: {path}")

        text = target.read_text(encoding="utf-8")
        occurrences = text.count(find)
        if occurrences == 0:
            raise ModelRetry("String to replace was not found in the file")
        if occurrences > 1:
            raise ModelRetry("String to replace was found multiple times; please be specific")

        updated = text.replace(find, replace, 1)
        backup_path = create_backup(target, backup_suffix=BACKUP_SUFFIX)
        target.write_text(updated, encoding="utf-8")
        return ToolResult(
            success=True,
            content=(
                f"Edit completed successfully for {path}\n"
                f"Backup created at: {backup_path.name}"
            ),
        )
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))


def apply_hunks(ctx: RunContext[RunDeps], plan: PatchPlan) -> ToolResult:
    """Apply structured patch hunks to one or more files atomically."""
    backups: dict[Path, Path] = {}
    try:
        file_results: list[FilePatchResult] = []

        for file_patch in plan.files:
            target = resolve_path(file_patch.path, ctx.deps)
            if target.is_dir():
                raise ModelRetry(f"Path must be a file, not a directory: {file_patch.path}")

            original = target.read_text(encoding="utf-8")
            patched, file_result = apply_file_patch(file_patch, original)
            file_results.append(file_result)

            if not file_result.applied:
                for target, backup in backups.items():
                    if backup.exists():
                        backup.replace(target)
                summary = PatchApplySummary(applied=False, files=file_results)
                return ToolResult(
                    success=False,
                    content="",
                    error=_serialize_patch_summary(summary),
                )

            backups[target] = create_backup(target, backup_suffix=BACKUP_SUFFIX)
            write_text_atomic(target, patched, temp_suffix=TEMP_SUFFIX)

        summary = PatchApplySummary(
            applied=all(result.applied for result in file_results),
            files=file_results,
        )
        return ToolResult(success=True, content=_serialize_patch_summary(summary))
    except ModelRetry:
        raise
    except PatchTransactionError as e:
        for target, backup in backups.items():
            if backup.exists():
                backup.replace(target)
        return ToolResult(success=False, content="", error=str(e))
    except Exception as e:
        for target, backup in backups.items():
            if backup.exists():
                backup.replace(target)
        return ToolResult(success=False, content="", error=str(e))


def apply_updates(ctx: RunContext[RunDeps], plan: PatchPlan) -> ToolResult:
    """Apply multiple file updates transactionally using patch plan."""
    try:
        resolved = {resolve_path(path, ctx.deps): content for path, content in plan.updates.items()}
        backups = apply_updates_transactionally(
            resolved, backup_suffix=BACKUP_SUFFIX, temp_suffix=TEMP_SUFFIX
        )
        summary = PatchApplySummary(
            applied=True,
            files=[FilePatchResult(path=p.as_posix(), applied=True, hunks=[]) for p in resolved],
        )
        backup_names = ", ".join(b.name for b in backups)
        return ToolResult(
            success=True,
            content=(
                _serialize_patch_summary(summary)
                + f"\nBackups created: {backup_names}"
            ),
        )
    except ModelRetry:
        raise
    except Exception as e:
        return ToolResult(success=False, content="", error=str(e))
