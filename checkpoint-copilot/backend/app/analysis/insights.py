"""Insights generator: combines all analysis into dashboard-ready data.

This is the top-level analysis entry point — it runs all the analyzers and
produces the data structures the API layer returns.
"""
from dataclasses import dataclass, field
from typing import Literal

from app.adapter.models import Session
from app.analysis.handoff_readiness import assess_handoff_readiness
from app.analysis.intent_vs_impl import compare_intent_vs_impl
from app.analysis.risk_scorer import RiskLevel, compute_risk_score
from app.analysis.unfinished_work import detect_unfinished_work


@dataclass
class SessionInsights:
    """All analysis results for one session, ready for the dashboard."""

    session_id: str
    description: str
    status: str
    start_time: str | None  # ISO string for JSON serialization
    agent_type: str

    # Analysis results
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: float  # 0.0–1.0
    risk_recommendation: str

    intent_alignment: float  # 0.0–1.0
    intent_summary: str
    intent_gaps: list[str]
    intent_surprises: list[str]

    unfinished_work: list[str]  # Summary lines
    todos_count: int
    retry_loops: list[str]
    abandoned_files: list[str]

    handoff_ready: bool
    handoff_blockers: list[str]
    handoff_suggestions: list[str]
    handoff_summary: str

    files_changed: list[str]
    checkpoint_count: int
    context_complete: bool
    context_status: str
    context_warnings: list[str]

    # Raw data for drill-down (kept small)
    first_prompt: str  # Truncated
    key_tool_calls: list[str]  # Tool names used


@dataclass
class DashboardSummary:
    """High-level summary for the dashboard overview."""

    total_sessions: int
    active_sessions: int
    ended_sessions: int
    sessions_by_risk: dict[str, int]  # "low" → count
    ready_for_handoff: int
    needs_review: int
    sessions: list[SessionInsights] = field(default_factory=list)


def generate_insights(sessions: list[Session]) -> DashboardSummary:
    """Run all analysis on all sessions and produce dashboard-ready data."""
    insights_list: list[SessionInsights] = []
    active = 0
    ended = 0
    ready_count = 0
    risk_counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for session in sessions:
        insight = _analyze_session(session)
        insights_list.append(insight)

        if session.status == "active":
            active += 1
        else:
            ended += 1

        risk_counts[insight.risk_level] = risk_counts.get(insight.risk_level, 0) + 1

        if insight.handoff_ready:
            ready_count += 1

    return DashboardSummary(
        total_sessions=len(sessions),
        active_sessions=active,
        ended_sessions=ended,
        sessions_by_risk=risk_counts,
        ready_for_handoff=ready_count,
        needs_review=len(sessions) - ready_count,
        sessions=insights_list,
    )


def _analyze_session(session: Session) -> SessionInsights:
    """Run all analyzers on one session."""
    risk = compute_risk_score(session)
    intent = compare_intent_vs_impl(session)
    unfinished = detect_unfinished_work(session)
    handoff = assess_handoff_readiness(session)

    # Collect key tool calls
    tool_names: list[str] = []
    seen: set[str] = set()
    for entry in session.transcript:
        if entry.is_tool_use and entry.tool_name and entry.tool_name not in seen:
            tool_names.append(entry.tool_name)
            seen.add(entry.tool_name)
            if len(tool_names) >= 20:
                break

    return SessionInsights(
        session_id=session.id,
        description=session.description[:200] if session.description else "",
        status=session.status,
        start_time=session.start_time.isoformat() if session.start_time else None,
        agent_type=session.agent_type,
        risk_level=risk.level.value,
        risk_score=risk.overall,
        risk_recommendation=risk.recommendation,
        intent_alignment=intent.alignment_score,
        intent_summary=intent.intent[:300],
        intent_gaps=intent.gaps,
        intent_surprises=intent.surprises,
        unfinished_work=_summarize_unfinished(unfinished),
        todos_count=len(unfinished.todos),
        retry_loops=unfinished.retries[:5],
        abandoned_files=unfinished.abandoned[:10],
        handoff_ready=handoff.ready,
        handoff_blockers=handoff.blockers,
        handoff_suggestions=handoff.suggestions,
        handoff_summary=handoff.summary,
        files_changed=list(session.all_files_changed)[:50],
        checkpoint_count=session.total_checkpoints,
        context_complete=session.context_complete,
        context_status=session.context_status,
        context_warnings=list(dict.fromkeys(session.context_warnings)),
        first_prompt=session.first_user_prompt[:500],
        key_tool_calls=tool_names,
    )


def _summarize_unfinished(unfinished) -> list[str]:
    """Flatten unfinished work detection into one-line summaries."""
    lines: list[str] = []
    if unfinished.todos:
        lines.append(f"{len(unfinished.todos)} TODO/FIXME comment(s)")
    if unfinished.retries:
        lines.append(f"Retry loops: {', '.join(unfinished.retries[:2])}")
    if unfinished.abandoned:
        lines.append(f"{len(unfinished.abandoned)} file(s) started but not committed")
    if unfinished.partial:
        lines.append(f"Partial implementations: {', '.join(unfinished.partial[:2])}")
    if not unfinished.context_complete:
        lines.append("Unknown transcript-only signals may exist because context is limited.")
    return lines
