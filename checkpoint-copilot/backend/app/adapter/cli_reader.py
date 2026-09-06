"""CLI-based Checkpoint reader.

Uses the `entire` CLI commands to fetch checkpoint data:
- `entire checkpoint list --json`        → list committed checkpoints
- `entire sessions list --json`          → list sessions with metadata
- `entire checkpoint list --pending --json` → pending checkpoints (uncommitted)

This is the ONLY data source — we do not read .entire/metadata/ directly and we
do not import from the entire CLI repository. We just shell out and parse JSON.

Run with ENTIRE_BIN env var or default to "entire" on $PATH.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.adapter.models import (
    Checkpoint,
    Session,
    SessionCheckpoint,
    TranscriptEntry,
)


class CliCheckpointReader:
    """Reads checkpoint data by shelling out to the `entire` CLI.

    Cleaner than parsing the on-disk .entire/ directory directly, and works
    with whichever version of Entire is installed.
    """

    def __init__(self, repo_path: str | Path, entire_bin: str | None = None) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.entire_bin = entire_bin or os.environ.get("ENTIRE_BIN", "entire")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[Session]:
        """List all sessions with their checkpoints, via `entire sessions list`."""
        raw_sessions = self._run_entire_json(["sessions", "list", "--json"])
        sessions: list[Session] = []
        for raw in raw_sessions:
            session = self._parse_session_from_sessions_list(raw)
            if session:
                # Enrich with checkpoints
                session.checkpoints = self._get_checkpoints_for_session(session.id)
                sessions.append(session)
        return sessions

    def list_committed_checkpoints(self) -> list[Checkpoint]:
        """List all committed checkpoints via `entire checkpoint list --json`."""
        raw = self._run_entire_json(["checkpoint", "list", "--json"])
        return [self._parse_committed_checkpoint(cp) for cp in raw]

    def list_pending_checkpoints(self) -> list[Checkpoint]:
        """List pending (uncommitted) checkpoints."""
        raw = self._run_entire_json(["checkpoint", "list", "--pending", "--json"])
        return [self._parse_pending_checkpoint(cp) for cp in raw]

    def read_session(self, session_id: str) -> Session | None:
        """Get one session by ID, including its checkpoints."""
        all_sessions = self.list_sessions()
        for s in all_sessions:
            if s.id == session_id:
                return s
        return None

    def read_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Get one committed checkpoint by ID, with enriched session context."""
        checkpoints = self.list_committed_checkpoints()
        for cp in checkpoints:
            if cp.id.startswith(checkpoint_id) or checkpoint_id.startswith(cp.id):
                # Find the session for this checkpoint
                if cp.session_id:
                    session = self.read_session(cp.session_id)
                    cp.session = session
                return cp
        return None

    # ------------------------------------------------------------------
    # Internal: subprocess wrapper
    # ------------------------------------------------------------------

    def _run_entire_json(self, args: list[str]) -> list[dict[str, Any]] | dict[str, Any]:
        """Run `entire <args> --json` and parse the output.

        Returns the parsed JSON. The shape depends on the command:
        - list commands: list of objects
        - single-item commands: object

        Empty list on any error.
        """
        cmd = [self.entire_bin, *args]
        if "--json" not in args:
            cmd.append("--json")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return []

        if result.returncode != 0:
            return []

        # The CLI may print warnings to stderr — ignore them. Output may
        # contain a leading warning line before the JSON. Find the first '['
        # or '{' and parse from there.
        output = result.stdout.strip()
        if not output:
            return []

        # Find where JSON starts
        json_start = -1
        for i, ch in enumerate(output):
            if ch in "[{":
                json_start = i
                break
        if json_start < 0:
            return []
        json_text = output[json_start:]

        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            return []

    # ------------------------------------------------------------------
    # Internal: parsing
    # ------------------------------------------------------------------

    def _parse_session_from_sessions_list(self, raw: dict[str, Any]) -> Session | None:
        """Build a Session from `entire sessions list --json` output."""
        session_id = raw.get("session_id", "")
        if not session_id:
            return None

        started = self._parse_timestamp(raw.get("started_at"))
        last_active = self._parse_timestamp(raw.get("last_active"))
        status = raw.get("status", "unknown")
        if status in ("idle", "stopped"):
            status = "ended"
        elif status not in ("active", "ended"):
            status = "unknown"

        return Session(
            id=session_id,
            description=raw.get("last_prompt", ""),
            start_time=started,
            end_time=last_active if status == "ended" else None,
            agent_type=raw.get("agent", ""),
            status=status,
            metadata_dir=f".entire/metadata/{session_id}",
        )

    def _get_checkpoints_for_session(self, session_id: str) -> list[SessionCheckpoint]:
        """Get all checkpoints that belong to a specific session."""
        checkpoints: list[SessionCheckpoint] = []

        # From committed list
        for cp in self.list_committed_checkpoints():
            if cp.session_id == session_id:
                checkpoints.append(
                    SessionCheckpoint(
                        id=cp.id,
                        session_id=session_id,
                        timestamp=cp.timestamp,
                        message=cp.message,
                        commit_hash=cp.commit_hash,
                        files_changed=cp.files_changed,
                        files_added=[],
                        files_deleted=[],
                    )
                )

        # From pending list
        for cp in self.list_pending_checkpoints():
            if cp.session_id == session_id:
                # Don't duplicate if already present
                if not any(c.id == cp.id for c in checkpoints):
                    checkpoints.append(
                        SessionCheckpoint(
                            id=cp.id,
                            session_id=session_id,
                            timestamp=cp.timestamp,
                            message=cp.message,
                            commit_hash=cp.commit_hash,
                            files_changed=cp.files_changed,
                        )
                    )

        return checkpoints

    def _parse_committed_checkpoint(self, raw: dict[str, Any]) -> Checkpoint:
        """Build a Checkpoint from `entire checkpoint list --json` output."""
        return Checkpoint(
            id=raw.get("checkpoint_id", ""),
            session_id=raw.get("session_id", ""),
            timestamp=self._parse_timestamp(raw.get("date")),
            message=raw.get("message", ""),
            commit_hash=raw.get("checkpoint_id", ""),
            files_changed=[],  # Not in list output; would need explain for details
        )

    def _parse_pending_checkpoint(self, raw: dict[str, Any]) -> Checkpoint:
        """Build a Checkpoint from `entire checkpoint list --pending --json` output."""
        return Checkpoint(
            id=raw.get("id", ""),
            session_id=raw.get("session_id", ""),
            timestamp=self._parse_timestamp(raw.get("date")),
            message=raw.get("message", ""),
            commit_hash=raw.get("id", "") if not raw.get("is_logs_only") else None,
            files_changed=[],
        )

    def _parse_timestamp(self, value: Any) -> datetime | None:
        """Parse a timestamp from CLI output (ISO 8601 string or epoch)."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (ValueError, OSError):
                return None
        if isinstance(value, str):
            # Try ISO 8601
            try:
                # Handle the +05:30 format
                if "+" in value[10:] or value.endswith("Z"):
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                return datetime.fromisoformat(value)
            except (ValueError, AttributeError):
                # Try as Unix timestamp
                try:
                    return datetime.fromtimestamp(float(value), tz=timezone.utc)
                except (ValueError, OSError):
                    return None
        return None
