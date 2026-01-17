"""Patch dataclasses for structured file edits."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HunkMatchOptions:
    """Options controlling hunk matching behavior."""

    ignore_trailing_whitespace: bool = False


@dataclass
class PatchHunk:
    """Structured edit hunk with context and replacement lines."""

    anchor_before: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)
    add: list[str] = field(default_factory=list)
    anchor_after: list[str] = field(default_factory=list)
    expected_near_line: int | None = None
    match_options: HunkMatchOptions | None = None


@dataclass
class FilePatch:
    """Patch containing one or more hunks for a single file."""

    path: str
    hunks: list[PatchHunk] = field(default_factory=list)


@dataclass
class PatchPlan:
    """Structured patch plan for multiple files."""

    files: list[FilePatch] = field(default_factory=list)


@dataclass
class HunkApplyResult:
    """Outcome of applying a single hunk."""

    index: int
    applied: bool
    error: str | None = None


@dataclass
class FilePatchResult:
    """Outcome of applying hunks to a file."""

    path: str
    applied: bool
    hunks: list[HunkApplyResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class PatchApplySummary:
    """Overall outcome of applying a patch plan."""

    applied: bool
    files: list[FilePatchResult] = field(default_factory=list)
