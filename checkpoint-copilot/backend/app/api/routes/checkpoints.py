"""Checkpoints endpoints (raw and enriched)."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.adapter import CheckpointReader

router = APIRouter(prefix="/api", tags=["checkpoints"])


class CheckpointSummary(BaseModel):
    """Summary of one committed checkpoint."""

    id: str
    session_id: str
    timestamp: str | None
    message: str
    commit_hash: str | None
    files_changed: list[str]
    context_complete: bool
    context_status: str
    context_warnings: list[str]


@router.get("/checkpoints", response_model=list[CheckpointSummary])
def list_committed_checkpoints(request: Request) -> list[CheckpointSummary]:
    """List all committed checkpoints from entire/checkpoints/v1 ref."""
    from app.api.routes.sessions import get_reader

    reader = get_reader(request)
    checkpoints = reader.list_committed_checkpoints()

    return [
        CheckpointSummary(
            id=cp.id,
            session_id=cp.session_id,
            timestamp=cp.timestamp.isoformat() if cp.timestamp else None,
            message=cp.message,
            commit_hash=cp.commit_hash,
            files_changed=cp.files_changed,
            context_complete=cp.context_complete,
            context_status=cp.context_status,
            context_warnings=cp.context_warnings,
        )
        for cp in checkpoints
    ]
