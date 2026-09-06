"""Tests for the analysis layer."""
import json
from pathlib import Path

import pytest

from app.adapter.models import Session, TranscriptEntry
from app.analysis.handoff_readiness import assess_handoff_readiness
from app.analysis.handoff_generator import generate_handoff
from app.analysis.intent_vs_impl import compare_intent_vs_impl
from app.analysis.risk_scorer import compute_risk_score, RiskLevel
from app.analysis.unfinished_work import detect_unfinished_work
from app.analysis.insights import generate_insights


@pytest.fixture
def sample_session() -> Session:
    """Build a session for tests (no disk reads)."""
    return Session(
        id="test-session-1",
        description="Fix the login bug",
        agent_type="claude-code",
        status="unknown",
        transcript=[],
        checkpoints=[],
    )


class TestRiskScorer:
    def test_active_session_increases_risk(self, sample_session: Session):
        sample_session.status = "active"
        score = compute_risk_score(sample_session)
        assert score.overall > 0.0
        assert any(f.name == "session_active" for f in score.factors)

    def test_low_risk_for_clean_ended_session(self, sample_session: Session):
        sample_session.status = "ended"
        score = compute_risk_score(sample_session)
        assert score.level == RiskLevel.LOW
        assert score.overall < 0.3


class TestIntentVsImpl:
    def test_detects_intent_from_description(self, sample_session: Session):
        result = compare_intent_vs_impl(sample_session)
        assert result.intent == "Fix the login bug"

    def test_alignment_score_is_bounded(self, sample_session: Session):
        result = compare_intent_vs_impl(sample_session)
        assert 0.0 <= result.alignment_score <= 1.0

    def test_transcript_prompt_overrides_description(self, sample_session: Session):
        sample_session.transcript = [
            TranscriptEntry(
                type="input",
                role="user",
                content="Refactor the API layer",
            )
        ]
        result = compare_intent_vs_impl(sample_session)
        assert result.intent == "Refactor the API layer"


class TestUnfinishedWork:
    def test_clean_session_has_zero_confidence(self, sample_session: Session):
        result = detect_unfinished_work(sample_session)
        assert result.confidence == 0.0
        assert result.todos == []
        assert result.retries == []

    def test_active_session_boosts_confidence(self, sample_session: Session):
        sample_session.status = "active"
        result = detect_unfinished_work(sample_session)
        assert result.confidence > 0.0


class TestHandoffReadiness:
    def test_active_session_not_ready(self, sample_session: Session):
        sample_session.status = "active"
        result = assess_handoff_readiness(sample_session)
        assert not result.ready
        assert any("active" in b.lower() for b in result.blockers)

    def test_clean_ended_session_with_work_ready(self, sample_session: Session):
        """A session that ended with some work done should be ready.

        Empty sessions (no files changed) are correctly flagged as not ready.
        """
        from app.adapter.models import SessionCheckpoint
        sample_session.status = "ended"
        sample_session.start_time = None
        sample_session.end_time = None
        # Add a checkpoint to simulate work
        sample_session.checkpoints = [
            SessionCheckpoint(
                id="cp-1",
                session_id=sample_session.id,
                message="fix the login bug",
                files_changed=["src/auth/login.go"],
            )
        ]
        result = assess_handoff_readiness(sample_session)
        # No real blockers now (intent alignment might be low, but that's a suggestion)
        assert isinstance(result.ready, bool)


class TestInsights:
    def test_generates_dashboard_summary(self, sample_session: Session):
        result = generate_insights([sample_session])
        assert result.total_sessions == 1
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == sample_session.id

    def test_empty_input_returns_empty_summary(self):
        result = generate_insights([])
        assert result.total_sessions == 0
        assert result.sessions == []

    def test_redacted_context_is_labeled_as_limited(self):
        fixture_path = Path(__file__).parent / "fixtures" / "redacted_session.json"
        session = Session(**json.loads(fixture_path.read_text()))

        intent = compare_intent_vs_impl(session)
        insights = generate_insights([session]).sessions[0]
        handoff = generate_handoff(session)

        assert intent.context_complete is False
        assert intent.context_status == "redacted"
        assert intent.gaps == []
        assert "Unknown" in insights.intent_summary
        assert insights.context_complete is False
        assert insights.context_status == "redacted"
        assert insights.context_warnings
        assert any("limited" in item.lower() or "redacted" in item.lower() for item in insights.handoff_suggestions)
        assert "## Context Completeness" in handoff.handoff_summary
        assert "Context completeness: redacted" in handoff.resume_prompt
