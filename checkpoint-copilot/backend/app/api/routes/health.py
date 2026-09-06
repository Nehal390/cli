"""Health check endpoint."""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.adapter import CliCheckpointReader

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    repo_path: str
    repo_exists: bool
    entire_dir_exists: bool


class RepoPathRequest(BaseModel):
    repo_path: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Check service health and configured repo path."""
    reader = getattr(request.app.state, "reader", None)
    repo_path = str(reader.repo_path) if reader else getattr(request.app.state, "repo_path", "")

    repo_p = Path(repo_path)
    entire_p = repo_p / ".entire"

    return HealthResponse(
        status="ok",
        repo_path=repo_path,
        repo_exists=repo_p.is_dir(),
        entire_dir_exists=entire_p.is_dir(),
    )


@router.post("/repo", response_model=HealthResponse)
def connect_repo(payload: RepoPathRequest, request: Request) -> HealthResponse:
    """Switch the active Entire repo path for subsequent adapter reads."""
    repo_p = Path(payload.repo_path).expanduser().resolve()
    if not repo_p.is_dir():
        raise HTTPException(status_code=400, detail=f"Repo path does not exist: {repo_p}")
    if not (repo_p / ".entire").is_dir():
        raise HTTPException(status_code=400, detail=f"Not an Entire-enabled repo: {repo_p}")

    os.environ["ENTIRE_REPO_PATH"] = str(repo_p)
    request.app.state.reader = CliCheckpointReader(repo_p)
    request.app.state.repo_path = str(repo_p)

    return HealthResponse(
        status="ok",
        repo_path=str(repo_p),
        repo_exists=True,
        entire_dir_exists=True,
    )
