"""File operation utilities for Agent C.

This module provides safe file operations including path resolution,
backup/restore functionality, and write verification. All operations
respect the working directory boundary for security.
"""

import shutil
from datetime import datetime
from pathlib import Path

# Configuration constants
BACKUP_SUFFIX = ".backup"
TEMP_SUFFIX = ".tmp"
KEEP_BACKUP_COUNT = 5


def safe_resolve(path_str: str) -> Path:
    """Safely resolve a path within the current working directory.

    Args:
        path_str: Path to resolve.

    Returns:
        Absolute resolved path.

    Raises:
        ValueError: If path doesn't exist, is invalid, or is outside cwd.
    """
    p = Path(path_str)
    base_dir = Path.cwd()
    try:
        resolved = (base_dir / p).resolve(strict=True)
    except FileNotFoundError:
        raise ValueError("Path does not exist.")
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")
    if not resolved.is_relative_to(base_dir):
        raise ValueError("Path is outside the allowed directory.")
    return resolved


def safe_resolve_create(path_str: str) -> Path:
    """Safely resolve a path for creation within the current working directory.

    Args:
        path_str: Path to resolve for creation.

    Returns:
        Absolute resolved path.

    Raises:
        ValueError: If path is invalid or outside cwd.
    """
    p = Path(path_str)
    base_dir = Path.cwd()
    try:
        resolved = (base_dir / p).resolve()
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")
    if not resolved.is_relative_to(base_dir):
        raise ValueError("Path is outside the allowed directory.")
    return resolved


def get_backup_path(path: Path, timestamp: str) -> Path:
    """Generate backup filename: file.ext.backup.TIMESTAMP

    Args:
        path: Original file path.
        timestamp: Timestamp string for backup.

    Returns:
        Path to the backup file.
    """
    return path.parent / f"{path.name}{BACKUP_SUFFIX}.{timestamp}"


def get_temp_path(path: Path) -> Path:
    """Generate temp filename: file.ext.tmp

    Args:
        path: Original file path.

    Returns:
        Path to the temporary file.
    """
    return path.parent / f"{path.name}{TEMP_SUFFIX}"


def create_backup(path: Path) -> Path:
    """Create timestamped backup of existing file.

    Args:
        path: Path to the file to backup.

    Returns:
        Path to the created backup.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = get_backup_path(path, timestamp)
    shutil.copy2(path, backup_path)
    return backup_path


def cleanup_old_backups(path: Path, keep_count: int = KEEP_BACKUP_COUNT) -> None:
    """Keep only the N most recent backups.

    Args:
        path: Path to the original file.
        keep_count: Number of backups to keep.
    """
    backups = sorted(path.parent.glob(f"{path.name}{BACKUP_SUFFIX}.*"))
    for old_backup in backups[:-keep_count]:
        old_backup.unlink()


def write_and_verify(path: Path, content: str) -> None:
    """Write to temp, verify, then commit. Raises on mismatch.

    This ensures atomic writes with verification. If verification fails,
    the temp file is cleaned up and an exception is raised.

    Args:
        path: Path to write to.
        content: Content to write.

    Raises:
        ValueError: If write verification fails.
        Exception: If writing fails.
    """
    temp_path = get_temp_path(path)
    try:
        # Write to temporary file.
        temp_path.write_text(content, encoding="utf-8")

        # Read back and verify.
        written = temp_path.read_text(encoding="utf-8")
        if written != content:
            raise ValueError("Write verification failed: content mismatch")

        # Atomic move (on most filesystems).
        temp_path.replace(path)
    except Exception:
        # Clean up temp if something went wrong.
        if temp_path.exists():
            temp_path.unlink()
        raise
