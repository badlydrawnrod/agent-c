"""Runtime dependency context and agent alias."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .types import UserInputHandler

@dataclass
class RunDeps:
    """Dependencies for the agent run context."""

    root_dirs: list[Path] = field(default_factory=list)
    skill_dirs: list[Path] = field(default_factory=list)
    user_input_handler: "UserInputHandler | None" = None

    def __post_init__(self) -> None:
        """Consolidate root_dirs and skill_dirs.

        Removes redundant paths (descendants) and duplicates. Ensures
        skill_dirs are included in root_dirs so tools can access them.
        """
        # Ensure all skill_dirs are covered by root_dirs
        self.root_dirs.extend(self.skill_dirs)

        self.root_dirs = self._consolidate_paths(self.root_dirs)
        self.skill_dirs = self._consolidate_paths(self.skill_dirs)

    def _consolidate_paths(self, paths: list[Path]) -> list[Path]:
        if not paths:
            return []
        # Resolve, remove duplicates, and sort by length (shallowest first)
        resolved = sorted({p.resolve() for p in paths}, key=lambda p: len(p.parts))
        unique: list[Path] = []
        for p in resolved:
            if not any(p.is_relative_to(parent) for parent in unique):
                unique.append(p)
        return unique


__all__ = ["RunDeps"]
