"""Path resolution for Entire checkpoint data.

These are pure path computations — no filesystem access here, just string
operations. All disk reads happen in reader.py.
"""
from __future__ import annotations

from pathlib import Path

# On-disk layout we expect (from docs/architecture/sessions-and-checkpoints.md).
# Kept as repo-relative constants so adapter remains self-contained.

ENTIRE_DIR_NAME = ".entire"
METADATA_DIR_NAME = "metadata"
SESSION_STATE_DIR = ".git/entire-sessions"
CHECKPOINTS_REF = "refs/heads/entire/checkpoints/v1"
FULL_TRANSCRIPT_FILENAME = "full.jsonl"


def entire_root(repo_path: Path) -> Path:
    """Path to the .entire directory."""
    return repo_path / ENTIRE_DIR_NAME


def metadata_root(repo_path: Path) -> Path:
    """Path to .entire/metadata/."""
    return entire_root(repo_path) / METADATA_DIR_NAME


def session_metadata_dir(repo_path: Path, session_id: str) -> Path:
    """Path to .entire/metadata/<session_id>/."""
    return metadata_root(repo_path) / session_id


def session_state_dir(repo_path: Path) -> Path:
    """Path to .git/entire-sessions/ (shared session bookkeeping)."""
    return repo_path / ".git" / "entire-sessions"


def is_safe_session_id(session_id: str) -> bool:
    """Refuse path traversal in session IDs.

    Session IDs are UUIDs in production, but we never trust on-disk data.
    A malicious or corrupt ID like `../../etc` must not become a read path.
    """
    if not session_id:
        return False
    if session_id in {".", ".."}:
        return False
    if "/" in session_id or "\\" in session_id:
        return False
    if session_id.startswith("."):
        return False
    return True
