"""Sessions endpoints."""
from fastapi import APIRouter, HTTPException, Request

from app.adapter import CheckpointReader
from app.analysis.insights import DashboardSummary, SessionInsights, generate_insights

router = APIRouter(prefix="/api", tags=["sessions"])


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
