"""Sessions endpoints."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.adapter import CheckpointReader
from app.analysis.handoff_generator import generate_handoff
from app.analysis.insights import DashboardSummary, SessionInsights, generate_insights

router = APIRouter(prefix="/api", tags=["sessions"])


class HandoffResponse(BaseModel):
    """Generated handoff content for a session."""

    handoff_summary: str
    resume_prompt: str
    context_complete: bool
    context_status: str
    context_warnings: list[str]


def get_reader(request: Request) -> CheckpointReader:
    """Get the checkpoint reader from app state (set in main.py lifespan)."""
    return request.app.state.reader


@router.get("/sessions", response_model=list[SessionInsights])
def list_sessions(request: Request) -> list[SessionInsights]:
    """List all sessions with analysis insights."""
    reader = get_reader(request)
    sessions = reader.list_sessions()
    insights = generate_insights(sessions)
    return insights.sessions


@router.get("/sessions/{session_id}", response_model=SessionInsights)
def get_session(session_id: str, request: Request) -> SessionInsights:
    """Get detailed analysis for one session."""
    reader = get_reader(request)
    session = reader.read_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    insights = generate_insights([session])
    if not insights.sessions:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return insights.sessions[0]


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(request: Request) -> DashboardSummary:
    """Get dashboard overview with all sessions analyzed."""
    reader = get_reader(request)
    sessions = reader.list_sessions()
    return generate_insights(sessions)


@router.post("/handoff/{session_id}", response_model=HandoffResponse)
def create_handoff(session_id: str, request: Request) -> HandoffResponse:
    """Generate a handoff summary and resume prompt for one session."""
    reader = get_reader(request)
    session = reader.read_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    handoff = generate_handoff(session)
    return HandoffResponse(
        handoff_summary=handoff.handoff_summary,
        resume_prompt=handoff.resume_prompt,
        context_complete=handoff.context_complete,
        context_status=handoff.context_status,
        context_warnings=handoff.context_warnings,
    )
