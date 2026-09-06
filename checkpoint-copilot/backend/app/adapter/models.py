"""Pydantic models for parsed checkpoint data.

These models form the contract between the adapter (filesystem) and the
analysis layer (pure logic) and the API layer (HTTP responses).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ContextStatus = Literal["complete", "limited", "redacted", "unavailable"]


def merge_context_status(statuses: list[ContextStatus]) -> ContextStatus:
    """Return the most restrictive context status from a group of inputs."""
    if "unavailable" in statuses:
        return "unavailable"
    if "redacted" in statuses:
        return "redacted"
    if "limited" in statuses:
        return "limited"
    return "complete"


def looks_redacted(value: Any) -> bool:
    """Detect common redaction sentinels without assuming one upstream format."""
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    redaction_markers = (
        "[redacted]",
        "<redacted>",
        "(redacted)",
        "redacted",
        "[sensitive]",
        "<sensitive>",
        "[omitted]",
        "<omitted>",
    )
    return any(marker in text for marker in redaction_markers)


class TranscriptEntry(BaseModel):
    """One line of a session transcript (full.jsonl).

    Shape is intentionally loose — we only extract fields we actually use.
    """

    type: str = ""
    role: str = ""
    content: str | list[Any] = ""
    timestamp: datetime | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    is_tool_use: bool = False
    is_tool_result: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class SessionCheckpoint(BaseModel):
    """A single checkpoint within a session.

    Maps to the on-disk structure under `.entire/metadata/<session>/` and
    committed refs under `entire/checkpoints/v1`.
    """

    id: str
    session_id: str
    timestamp: datetime | None = None
    message: str = ""
    commit_hash: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    files_added: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    is_task_checkpoint: bool = False
    metadata_dir: str = ""
    context_complete: bool = True
    context_status: ContextStatus = "complete"
    context_warnings: list[str] = Field(default_factory=list)


class Session(BaseModel):
    """A full session with its checkpoints and metadata.

    Sourced from `.entire/metadata/<session-id>/` and `.git/entire-sessions/`.
    """

    id: str
    description: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    agent_type: str = ""
    status: Literal["active", "ended", "unknown"] = "unknown"
    checkpoints: list[SessionCheckpoint] = Field(default_factory=list)
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    metadata_dir: str = ""
    context_complete: bool = True
    context_status: ContextStatus = "complete"
    context_warnings: list[str] = Field(default_factory=list)

    @property
    def total_checkpoints(self) -> int:
        return len(self.checkpoints)

    @property
    def all_files_changed(self) -> set[str]:
        files: set[str] = set()
        for cp in self.checkpoints:
            files.update(cp.files_changed)
            files.update(cp.files_added)
            files.update(cp.files_deleted)
        return files

    @property
    def first_user_prompt(self) -> str:
        """Extract the first user prompt from the transcript."""
        for entry in self.transcript:
            if entry.role == "user" and entry.content:
                if isinstance(entry.content, str):
                    return entry.content[:500]
                # Content may be a list of content blocks
                return str(entry.content)[:500]
        return self.description


class Checkpoint(BaseModel):
    """A checkpoint with its associated session, ready for analysis.

    This is the "enriched" view that joins a checkpoint with its session
    context, so the analysis layer doesn't need to do lookups.
    """

    id: str
    session_id: str
    timestamp: datetime | None = None
    message: str = ""
    commit_hash: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    session: Session | None = None
    context_complete: bool = True
    context_status: ContextStatus = "complete"
    context_warnings: list[str] = Field(default_factory=list)

    @property
    def user_intent(self) -> str:
        """The user's stated intent for this work."""
        if self.session:
            return self.session.first_user_prompt
        return self.message
