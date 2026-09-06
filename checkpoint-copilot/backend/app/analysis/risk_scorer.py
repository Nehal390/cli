"""Risk scoring for checkpoints and sessions.

Produces a 0.0–1.0 risk score with breakdown of contributing factors.
"""
from dataclasses import dataclass, field
from enum import Enum

from app.adapter.models import Session


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskFactor:
    name: str
    score: float  # Contribution to overall risk (0.0–1.0)
    description: str


@dataclass
class RiskScore:
    """A risk score with breakdown and level."""

    overall: float  # 0.0 (safe) – 1.0 (risky)
    level: RiskLevel
    factors: list[RiskFactor] = field(default_factory=list)
    recommendation: str = ""


def compute_risk_score(session: Session) -> RiskScore:
    """Compute a risk score for a session."""
    factors: list[RiskFactor] = []
    total = 0.0

    # Factor 1: Active session (may be unfinished)
    if session.status == "active":
        factors.append(RiskFactor(
            name="session_active",
            score=0.15,
            description="Session is still active — work may not be complete",
        ))
        total += 0.15

    # Factor 2: Large number of files changed
    file_count = len(session.all_files_changed)
    if file_count > 20:
        factors.append(RiskFactor(
            name="large_diff",
            score=0.25,
            description=f"Large change set: {file_count} files modified",
        ))
        total += 0.25
    elif file_count > 10:
        factors.append(RiskFactor(
            name="medium_diff",
            score=0.1,
            description=f"Moderate change set: {file_count} files",
        ))
        total += 0.1

    # Factor 3: Many checkpoints suggest the agent struggled
    checkpoint_count = len(session.checkpoints)
    if checkpoint_count > 10:
        factors.append(RiskFactor(
            name="many_checkpoints",
            score=0.2,
            description=f"Many checkpoints ({checkpoint_count}) — possible struggle",
        ))
        total += 0.2
    elif checkpoint_count == 0 and session.total_checkpoints == 0:
        factors.append(RiskFactor(
            name="no_checkpoints",
            score=0.1,
            description="No checkpoints on record",
        ))
        total += 0.1

    # Factor 4: Check for error patterns in transcript
    error_count = 0
    for entry in session.transcript:
        content = ""
        if isinstance(entry.content, str):
            content = entry.content
        elif entry.raw:
            content = str(entry.raw)

        if any(kw in content.lower() for kw in ["error", "failed", "exception", "traceback"]):
            error_count += 1

    if error_count >= 5:
        factors.append(RiskFactor(
            name="many_errors",
            score=0.3,
            description=f"Many error mentions ({error_count}) in transcript",
        ))
        total += 0.3
    elif error_count >= 2:
        factors.append(RiskFactor(
            name="some_errors",
            score=0.15,
            description=f"Some error mentions ({error_count}) in transcript",
        ))
        total += 0.15

    # Factor 5: Short session (quick work is usually risky)
    if session.start_time and session.end_time:
        duration = (session.end_time - session.start_time).total_seconds()
        if duration < 60:  # Less than 1 minute
            factors.append(RiskFactor(
                name="very_short_session",
                score=0.2,
                description=f"Very short session ({int(duration)}s) — possible mistake",
            ))
            total += 0.2

    # Cap at 1.0
    overall = min(1.0, total)

    # Determine level
    if overall >= 0.7:
        level = RiskLevel.CRITICAL
        recommendation = "High risk: review carefully before merging"
    elif overall >= 0.5:
        level = RiskLevel.HIGH
        recommendation = "Elevated risk: test thoroughly before merging"
    elif overall >= 0.3:
        level = RiskLevel.MEDIUM
        recommendation = "Moderate risk: standard review recommended"
    else:
        level = RiskLevel.LOW
        recommendation = "Low risk: standard review"

    return RiskScore(
        overall=overall,
        level=level,
        factors=factors,
        recommendation=recommendation,
    )
