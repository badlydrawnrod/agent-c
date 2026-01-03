"""Backup operation tools for Agent C."""

import shutil

from pydantic_ai import ModelRetry, RunContext

from ..file_ops import safe_resolve
from ..types import RunDeps


def list_backups(ctx: RunContext[RunDeps], path: str) -> str:
    """List available backups for a file."""
    ctx.deps.info(f"Listing backups for: {path}")
    resolved_path = safe_resolve(path)
    backups = sorted(resolved_path.parent.glob(f"{resolved_path.name}.backup.*"))
    if not backups:
        return "No backups found"
    return "\n".join(b.name for b in backups)


def restore_backup(ctx: RunContext[RunDeps], path: str, backup_name: str) -> str:
    """Restore a file from a backup."""
    ctx.deps.info(f"Restoring {path} from {backup_name}")
    resolved_path = safe_resolve(path)
    backup_path = resolved_path.parent / backup_name
    if not backup_path.exists():
        raise ModelRetry("Backup not found")
    shutil.copy2(backup_path, resolved_path)
    return f"Restored {path} from {backup_name}"
