"""Generate handoff summaries and resume prompts from session data."""
from __future__ import annotations

from dataclasses import dataclass

from app.adapter.models import Session
from app.analysis.handoff_readiness import assess_handoff_readiness
from app.analysis.intent_vs_impl import compare_intent_vs_impl
from app.analysis.risk_scorer import compute_risk_score
from app.analysis.unfinished_work import detect_unfinished_work


@dataclass
class GeneratedHandoff:
    """Ready-to-display handoff content for a session."""

    session_id: str
    handoff_summary: str
    resume_prompt: str


def generate_handoff(session: Session) -> GeneratedHandoff:
    """Create a formatted handoff summary and fresh-agent resume prompt."""
    intent = compare_intent_vs_impl(session)
    risk = compute_risk_score(session)
    handoff = assess_handoff_readiness(session)
    unfinished = detect_unfinished_work(session)

    done = _done_lines(session)
    pending = _pending_lines(intent.gaps, handoff.blockers, handoff.suggestions, unfinished.partial)
    risks = _risk_lines(risk)

    summary = "\n".join(
        [
            "# Handoff Summary",
            "",
            f"Session: {session.id}",
            f"Status: {session.status}",
            f"Agent: {session.agent_type or 'unknown'}",
            "",
            "## Intent",
            intent.intent or session.first_user_prompt or session.description or "No explicit intent captured.",
            "",
            "## What's Done",
            *_bullet_lines(done),
            "",
            "## What's Pending",
            *_bullet_lines(pending),
            "",
            "## Key Risks",
            *_bullet_lines(risks),
        ]
    )

    resume_prompt = "\n".join(
        [
            "Continue this work from the following handoff context.",
            "",
            f"Session ID: {session.id}",
            f"Session status: {session.status}",
            f"Previous agent: {session.agent_type or 'unknown'}",
            "",
            "Original intent:",
            intent.intent or session.first_user_prompt or session.description or "No explicit intent captured.",
            "",
            "What has been done:",
            *_bullet_lines(done),
            "",
            "Pending work and cautions:",
            *_bullet_lines(pending),
            "",
            "Risk context:",
            *_bullet_lines(risks),
            "",
            "Use the existing repository state and checkpoint history as source of truth. Do not rebuild working pieces unless new evidence shows they are broken.",
        ]
    )

    return GeneratedHandoff(
        session_id=session.id,
        handoff_summary=summary,
        resume_prompt=resume_prompt,
    )


def _done_lines(session: Session) -> list[str]:
    lines: list[str] = []
    if session.checkpoints:
        seen: set[str] = set()
        for checkpoint in session.checkpoints:
            timestamp = checkpoint.timestamp.isoformat() if checkpoint.timestamp else "unknown time"
            message = checkpoint.message or "No checkpoint message"
            key = f"{message}:{timestamp}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"{message} ({timestamp})")
            if len(lines) >= 8:
                break
    else:
        lines.append("No checkpoints are recorded for this session.")

    files = sorted(session.all_files_changed)
    if files:
        lines.append(f"Files touched: {', '.join(files[:20])}")
        if len(files) > 20:
            lines.append(f"{len(files) - 20} additional file(s) omitted from this summary.")
    else:
        lines.append("No file list is available from checkpoint list data.")

    return lines


def _pending_lines(
    gaps: list[str],
    blockers: list[str],
    suggestions: list[str],
    partial: list[str],
) -> list[str]:
    lines: list[str] = []
    lines.extend(blockers)
    lines.extend(f"Gap: {gap}" for gap in gaps if f"Gap: {gap}" not in lines)
    lines.extend(f"Partial implementation: {item}" for item in partial)
    lines.extend(suggestions)
    return lines or ["No pending items detected by the current analysis."]


def _risk_lines(risk) -> list[str]:
    lines = [
        f"{risk.level.value.upper()} risk ({risk.overall:.0%}): {risk.recommendation}",
    ]
    lines.extend(f"{factor.description}" for factor in risk.factors)
    return lines


def _bullet_lines(lines: list[str]) -> list[str]:
    return [f"- {line}" for line in lines]
