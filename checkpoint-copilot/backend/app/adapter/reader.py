"""Checkpoint reader: reads Entire checkpoint data from disk.

This is the ONLY module in the adapter that reads from the filesystem.
Everything else works on the parsed Pydantic models returned from here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.adapter.models import (
    Checkpoint,
    Session,
    SessionCheckpoint,
    TranscriptEntry,
)
from app.adapter.paths import (
    CHECKPOINTS_REF,
    FULL_TRANSCRIPT_FILENAME,
    entire_root,
    is_safe_session_id,
    session_metadata_dir,
    session_state_dir,
)


class CheckpointReader:
    """Reads checkpoint data from an Entire-enabled git repository.

    Does NOT import or call any code from the main CLI repository.
    All data is read by parsing on-disk files and git refs directly.

    Usage:
        reader = CheckpointReader("/path/to/repo")
        sessions = reader.list_sessions()
    """

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        self._git_available: bool | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[Session]:
        """Return all sessions found in the repo."""
        sessions: list[Session] = []
        for session_id in self._list_session_dirs():
            if session := self.read_session(session_id):
                sessions.append(session)
        return sessions

    def read_session(self, session_id: str) -> Session | None:
        """Read one session by ID, including its checkpoints and transcript."""
        if not is_safe_session_id(session_id):
            return None

        meta_dir = session_metadata_dir(self.repo_path, session_id)
        if not meta_dir.is_dir():
            return None

        metadata_json = self._read_json(meta_dir / "metadata.json")
        if metadata_json is None:
            return None

        session = self._parse_session(session_id, metadata_json, meta_dir)

        # Load checkpoints from state dir
        state_dir = session_state_dir(self.repo_path)
        state_json = self._read_json(state_dir / f"{session_id}.json")
        if state_json:
            session.checkpoints = self._parse_checkpoints(state_json, session_id)

        # Load transcript
        transcript_path = meta_dir / FULL_TRANSCRIPT_FILENAME
        if transcript_path.is_file():
            session.transcript = self._read_transcript(transcript_path)

        return session

    def list_committed_checkpoints(self) -> list[Checkpoint]:
        """List all committed checkpoints from the entire/checkpoints/v1 ref.

        Falls back gracefully when git is unavailable.
        """
        if not self._is_git_available():
            return []

        try:
            import git
        except ImportError:
            return []

        try:
            repo = git.Repo(str(self.repo_path))
            ref_name = CHECKPOINTS_REF
            if ref_name not in repo.refs:
                return []

            ref = repo.refs[ref_name]
            checkpoints: list[Checkpoint] = []

            # Walk commits on the ref, newest first
            for commit in repo.iterate_commits(ref, max_count=50):
                session_id = self._trailer(commit, "Entire-Session", "")
                cp_id = self._trailer(commit, "Entire-Checkpoint", "")
                message = commit.message.strip().split("\n")[0] if commit.message else ""
                files = self._extract_files_from_commit(commit)

                cp = Checkpoint(
                    id=cp_id or commit.hexsha[:12],
                    session_id=session_id or "",
                    timestamp=datetime.fromtimestamp(commit.committed_date, tz=timezone.utc),
                    message=message,
                    commit_hash=commit.hexsha,
                    files_changed=files,
                )
                checkpoints.append(cp)

            return checkpoints
        except Exception:
            # Silently degrade: no checkpoints, not an error
            return []

    # ------------------------------------------------------------------
    # Internal: filesystem reads
    # ------------------------------------------------------------------

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """Read and parse one JSON file. Returns None on any error."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _read_transcript(self, path: Path) -> list[TranscriptEntry]:
        """Read a full.jsonl file, one JSON object per line."""
        entries: list[TranscriptEntry] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        entry = TranscriptEntry(
                            type=obj.get("type", ""),
                            role=obj.get("role", ""),
                            content=obj.get("content", ""),
                            timestamp=self._parse_timestamp(obj.get("timestamp")),
                            tool_name=obj.get("tool_use", {}).get("name") if obj.get("tool_use") else None,
                            tool_input=obj.get("tool_use", {}).get("input"),
                            is_tool_use=obj.get("type") == "input",
                            is_tool_result=obj.get("type") == "result",
                            raw=obj,
                        )
                        entries.append(entry)
                    except Exception:
                        # Skip malformed lines
                        continue
        except Exception:
            pass
        return entries

    def _read_state_file(self, session_id: str) -> dict[str, Any] | None:
        """Read the session state JSON from .git/entire-sessions/."""
        state_path = session_state_dir(self.repo_path) / f"{session_id}.json"
        return self._read_json(state_path)

    # ------------------------------------------------------------------
    # Internal: parsing helpers
    # ------------------------------------------------------------------

    def _list_session_dirs(self) -> list[str]:
        """List session IDs from .entire/metadata/."""
        root = entire_root(self.repo_path) / "metadata"
        if not root.is_dir():
            return []

        session_ids: list[str] = []
        try:
            for entry in root.iterdir():
                if entry.is_dir() and is_safe_session_id(entry.name):
                    session_ids.append(entry.name)
        except Exception:
            pass

        return session_ids

    def _parse_session(
        self, session_id: str, metadata_json: dict[str, Any], meta_dir: Path
    ) -> Session:
        """Build a Session from a metadata.json dict."""
        # Extract sessions list (may be a list or a single session object)
        sessions_data = metadata_json.get("sessions", [])
        if isinstance(sessions_data, list) and sessions_data:
            sdata = sessions_data[0]
        elif isinstance(sessions_data, dict):
            sdata = sessions_data
        else:
            sdata = metadata_json

        description = sdata.get("description", "")
        if not description:
            description = sdata.get("prompt", "")

        start_time = self._parse_timestamp(sdata.get("start_time"))
        end_time = self._parse_timestamp(sdata.get("end_time"))

        agent_type = metadata_json.get("agent", metadata_json.get("agent_type", ""))

        status = "unknown"
        if sdata.get("status") == "active":
            status = "active"
        elif end_time is not None:
            status = "ended"

        return Session(
            id=session_id,
            description=description,
            start_time=start_time,
            end_time=end_time,
            agent_type=agent_type,
            status=status,
            metadata_dir=str(meta_dir),
        )

    def _parse_checkpoints(
        self, state_json: dict[str, Any], session_id: str
    ) -> list[SessionCheckpoint]:
        """Parse checkpoint list from a session state file."""
        checkpoints: list[SessionCheckpoint] = []

        checkpoints_data = state_json.get("checkpoints", [])
        if not isinstance(checkpoints_data, list):
            checkpoints_data = []

        for i, cp_data in enumerate(checkpoints_data):
            if isinstance(cp_data, dict):
                cp = SessionCheckpoint(
                    id=cp_data.get("id", f"{session_id}-{i}"),
                    session_id=session_id,
                    timestamp=self._parse_timestamp(cp_data.get("timestamp")),
                    message=cp_data.get("message", ""),
                    commit_hash=cp_data.get("commit_hash"),
                    files_changed=cp_data.get("files_changed", []),
                    files_added=cp_data.get("files_added", []),
                    files_deleted=cp_data.get("files_deleted", []),
                    is_task_checkpoint=cp_data.get("is_task_checkpoint", False),
                    metadata_dir=cp_data.get("metadata_dir", ""),
                )
                checkpoints.append(cp)

        return checkpoints

    def _parse_timestamp(self, value: Any) -> datetime | None:
        """Parse a timestamp from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except Exception:
                return None
        if isinstance(value, str):
            # Try ISO format
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            # Try parsing as Unix timestamp
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (ValueError, OSError):
                return None
        return None

    def _trailer(self, commit: Any, name: str, default: str = "") -> str:
        """Extract a git trailer from a commit (e.g. Entire-Session)."""
        try:
            for trailer in commit.message.strip().split("\n"):
                if trailer.startswith(f"{name}: "):
                    return trailer[len(name) + 2 :].strip()
        except Exception:
            pass
        return default

    def _extract_files_from_commit(self, commit: Any) -> list[str]:
        """Extract file paths changed in a commit."""
        files: list[str] = []
        try:
            for parent in commit.parents:
                diff = parent.diff(commit)
                for d in diff:
                    if d.a_path:
                        files.append(d.a_path)
                    if d.b_path and d.b_path != d.a_path:
                        files.append(d.b_path)
        except Exception:
            pass
        return list(dict.fromkeys(files))  # Dedupe

    def _is_git_available(self) -> bool:
        """Check if gitpython is available and the repo is valid."""
        if self._git_available is not None:
            return self._git_available
        try:
            import git  # noqa: F401
            import git.exc

            git.Repo(str(self.repo_path))
            self._git_available = True
        except Exception:
            self._git_available = False
        return self._git_available
