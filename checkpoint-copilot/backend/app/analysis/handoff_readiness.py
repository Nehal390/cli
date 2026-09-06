"""Handoff readiness assessment.

Determines whether a session's work is ready to be handed off (merged,
deployed, or picked up by another developer). Considers:
- Whether there are obvious blockers (errors, TODOs, unfinished work)
- Whether the implementation matches the intent
- Whether the session has been formally ended
"""
from dataclasses import dataclass

from app.adapter.models import Session
from app.analysis.intent_vs_impl import compare_intent_vs_impl
from app.analysis.unfinished_work import detect_unfinished_work


@dataclass
class HandoffReadiness:
    """Handoff readiness assessment."""

    ready: bool
    confidence: float  # 0.0–1.0: how confident in the assessment
    blockers: list[str]  # Things that must be resolved
    suggestions: list[str]  # Things to improve before handoff
    summary: str


def assess_handoff_readiness(session: Session) -> HandoffReadiness:
    """Assess whether a session is ready to be handed off."""
    blockers: list[str] = []
    suggestions: list[str] = []

    # Check 1: Session must be ended (not still active)
    if session.status == "active":
        blockers.append("Session is still active")
    elif session.status == "unknown":
        suggestions.append("Session end time not recorded — verify completion")

    # Check 2: Intent vs implementation alignment
    intent_result = compare_intent_vs_impl(session)
    if intent_result.alignment_score < 0.2:
        blockers.append(
            f"Low intent alignment ({intent_result.alignment_score:.0%}) — "
            f"implementation may not match user request"
        )
    elif intent_result.alignment_score < 0.4:
        suggestions.append(
            f"Weak intent alignment ({intent_result.alignment_score:.0%}) — "
            f"consider verifying with the user"
        )

    if intent_result.gaps:
        blockers.extend([f"Gap: {g}" for g in intent_result.gaps])

    # Check 3: Unfinished work
    unfinished = detect_unfinished_work(session)
    if unfinished.todos:
        blockers.append(f"{len(unfinished.todos)} TODO/FIXME comments remain")
    if unfinished.retries:
        suggestions.append(
            f"Retry loops detected: {', '.join(unfinished.retries[:3])}"
        )
    if unfinished.abandoned:
        suggestions.append(
            f"{len(unfinished.abandoned)} files started but not committed"
        )
    if unfinished.partial:
        blockers.append(
            f"Partial implementations: {', '.join(unfinished.partial)}"
        )

    # Check 4: At least one checkpoint (some evidence of progress)
    if session.total_checkpoints == 0:
        suggestions.append("No checkpoints on record — verify work actually happened")

    # Check 5: Has the session been formally ended?
    if not session.end_time and session.status != "active":
        suggestions.append("Session has no end time recorded")

    # Compute confidence based on data quality
    confidence = 0.5
    if session.transcript:
        confidence += 0.2
    if session.checkpoints:
        confidence += 0.2
    if session.start_time:
        confidence += 0.05
    if session.end_time:
        confidence += 0.05

    confidence = min(1.0, confidence)

    # Ready if no blockers
    ready = len(blockers) == 0

    # Build summary
    if ready:
        if not suggestions:
            summary = "Ready for handoff. All clear."
        else:
            summary = f"Ready, with {len(suggestions)} suggestion(s) for improvement."
    else:
        summary = f"Not ready: {len(blockers)} blocker(s) need attention."

    return HandoffReadiness(
        ready=ready,
        confidence=confidence,
        blockers=blockers,
        suggestions=suggestions,
        summary=summary,
    )
