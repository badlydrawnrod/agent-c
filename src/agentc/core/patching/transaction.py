"""Transactional file updates for patch application."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

from .errors import PatchTransactionError


def write_text_atomic(path: Path, content: str, *, temp_suffix: str) -> None:
    """Write text atomically via a temp file in the same directory."""
    temp_path = path.parent / f"{path.name}{temp_suffix}"
    try:
        temp_path.write_text(content, encoding="utf-8")
        written = temp_path.read_text(encoding="utf-8")
        if written != content:
            raise PatchTransactionError("Write verification failed: content mismatch")
        temp_path.replace(path)
    except PatchTransactionError:
        raise
    except Exception as exc:
        raise PatchTransactionError(f"Atomic write failed for {path}") from exc
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def create_backup(
    path: Path,
    *,
    backup_suffix: str,
    now: datetime | None = None,
) -> Path:
    """Create a timestamped backup of the file alongside the original."""
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = path.parent / f"{path.name}{backup_suffix}.{timestamp}"
    try:
        shutil.copy2(path, backup_path)
    except Exception as exc:
        raise PatchTransactionError(f"Failed to create backup for {path}") from exc
    return backup_path


def apply_updates_transactionally(
    updates: dict[Path, str],
    *,
    backup_suffix: str,
    temp_suffix: str,
    now: datetime | None = None,
) -> dict[Path, Path]:
    """Apply updates across multiple files atomically with rollback.

    Creates backups for all files before writing any changes. If any write fails,
    already-written files are restored from backups and an exception is raised.
    Returns a mapping of target files to their backup paths.
    """
    backups: dict[Path, Path] = {}
    written: list[Path] = []
    try:
        for target in updates:
            backups[target] = create_backup(
                target, backup_suffix=backup_suffix, now=now
            )
        for target, updated in updates.items():
            write_text_atomic(target, updated, temp_suffix=temp_suffix)
            written.append(target)
        return backups
    except PatchTransactionError:
        for target in written:
            backup = backups.get(target)
            if backup and backup.exists():
                shutil.copy2(backup, target)
        raise
    except Exception as exc:
        for target in written:
            backup = backups.get(target)
            if backup and backup.exists():
                shutil.copy2(backup, target)
        raise PatchTransactionError("Transactional update failed") from exc
