"""Analysis layer: pure logic on parsed checkpoint data.

No filesystem access here — only the Pydantic models from the adapter.
"""
from app.analysis.insights import generate_insights
from app.analysis.risk_scorer import compute_risk_score
from app.analysis.unfinished_work import detect_unfinished_work
from app.analysis.handoff_readiness import assess_handoff_readiness
from app.analysis.intent_vs_impl import compare_intent_vs_impl

__all__ = [
    "generate_insights",
    "compute_risk_score",
    "detect_unfinished_work",
    "assess_handoff_readiness",
    "compare_intent_vs_impl",
]
