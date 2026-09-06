"""Health check endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    repo_path: str
    repo_exists: bool
    entire_dir_exists: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Check service health and configured repo path."""
    from app.config import get_repo_path

    repo_path = get_repo_path()
    from pathlib import Path

    repo_p = Path(repo_path)
    entire_p = repo_p / ".entire"

    return HealthResponse(
        status="ok",
        repo_path=repo_path,
        repo_exists=repo_p.is_dir(),
        entire_dir_exists=entire_p.is_dir(),
    )
