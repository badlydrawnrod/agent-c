"""Patch application utilities for Agent C."""

from .engine import apply_file_patch
from .errors import PatchError, PatchMatchError, PatchPlanError, PatchTransactionError
from .transaction import apply_updates_transactionally, create_backup, write_text_atomic
from .types import (
    FilePatch,
    FilePatchResult,
    HunkApplyResult,
    HunkMatchOptions,
    PatchApplySummary,
    PatchHunk,
    PatchPlan,
)

__all__ = [
    "PatchError",
    "PatchMatchError",
    "PatchPlanError",
    "PatchTransactionError",
    "apply_file_patch",
    "apply_updates_transactionally",
    "create_backup",
    "write_text_atomic",
    "FilePatch",
    "FilePatchResult",
    "HunkApplyResult",
    "HunkMatchOptions",
    "PatchApplySummary",
    "PatchHunk",
    "PatchPlan",
]
