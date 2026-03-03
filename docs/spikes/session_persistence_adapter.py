from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CommonSessionRecord:
    role: str
    content: str
    kind: str
    checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionCheckpoint:
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CommonSessionState:
    session_key: str
    active_checkpoint_id: str | None = None
    checkpoints: list[SessionCheckpoint] = field(default_factory=list)
    records: list[CommonSessionRecord] = field(default_factory=list)


class SessionCheckpointStore(Protocol):
    """Durable native state storage with branching checkpoint support."""

    def create_checkpoint(
        self,
        session_key: str,
        parent_checkpoint_id: str | None = None,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a checkpoint node and return its checkpoint identifier."""
        ...

    def set_active_checkpoint(self, session_key: str, checkpoint_id: str | None) -> None:
        """Set or clear the active checkpoint pointer for a session."""
        ...

    def get_active_checkpoint(self, session_key: str) -> str | None:
        """Get the active checkpoint identifier for a session, if any."""
        ...

    def save_native(
        self,
        session_key: str,
        native_state: list[Any],
        checkpoint_id: str | None = None,
    ) -> str:
        """Persist native state at a checkpoint and return the target checkpoint id."""
        ...

    def load_native(
        self,
        session_key: str,
        checkpoint_id: str | None = None,
    ) -> list[Any] | None:
        """Load native state for the requested or active checkpoint."""
        ...

    def build_context(
        self,
        session_key: str,
        checkpoint_id: str | None = None,
    ) -> list[Any] | None:
        """Build active-path native context from root to a target checkpoint."""
        ...


class SessionInterchangeCodec(Protocol):
    """Optional conversion between native checkpoint data and common handoff format."""

    def export_common(self, session_key: str) -> CommonSessionState:
        """Export persisted state into a backend-agnostic common format."""
        ...

    def import_common(
        self,
        common_state: CommonSessionState,
        target_session_key: str | None = None,
    ) -> str:
        """Import common state and return the effective session key."""
        ...


__all__ = [
    "CommonSessionRecord",
    "CommonSessionState",
    "SessionCheckpoint",
    "SessionCheckpointStore",
    "SessionInterchangeCodec",
]
