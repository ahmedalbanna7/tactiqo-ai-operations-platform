"""Tests for multilingual RAG quality and security release gates."""

import pytest

from tactiqo.knowledge.application.retrieval_quality import (
    RetrievalCase,
    RetrievalThresholds,
    SecurityCase,
    activation_decision,
    evaluate,
    evaluate_security,
)

MINIMUM_EXPECTED_NDCG = 0.85
EXPECTED_P95_MS = 610


def test_computes_multilingual_ranking_citation_and_latency_metrics() -> None:
    """Measure Arabic, English, and mixed queries without language exceptions."""
    metrics = evaluate(
        (
            RetrievalCase(
                "ما هي ميزانية المشروع؟",
                frozenset({"budget"}),
                ("plan", "budget"),
                (("budget", 3),),
                frozenset({"budget"}),
                answer_grounded=True,
                latency_ms=420,
                language="ar",
            ),
            RetrievalCase(
                "When is the project deadline?",
                frozenset({"plan"}),
                ("plan", "risk"),
                (("plan", 3),),
                frozenset({"plan"}),
                answer_grounded=True,
                latency_ms=510,
                language="en",
            ),
            RetrievalCase(
                "اعرض risk mitigation plan",
                frozenset({"risk"}),
                ("risk", "plan"),
                (("risk", 2),),
                frozenset({"risk"}),
                answer_grounded=True,
                latency_ms=EXPECTED_P95_MS,
                language="mixed",
            ),
        )
    )
    assert metrics.recall_at_k == 1.0
    assert metrics.mean_reciprocal_rank == pytest.approx(5 / 6)
    assert metrics.ndcg_at_k > MINIMUM_EXPECTED_NDCG
    assert metrics.citation_correctness == 1.0
    assert metrics.answer_grounding == 1.0
    assert metrics.latency_p95_ms == EXPECTED_P95_MS


def test_security_metrics_count_hidden_results_and_injection_misses() -> None:
    """Treat one hidden document or undetected injection as a measurable failure."""
    metrics = evaluate_security(
        (
            SecurityCase(frozenset({"allowed"}), ("allowed", "hidden")),
            SecurityCase(
                frozenset({"safe"}),
                ("safe",),
                injection_present=True,
                injection_detected=False,
            ),
        )
    )
    assert metrics.unauthorized_results == 1
    assert metrics.injection_detection_rate == 0.0


def test_activation_gate_fails_closed_with_exact_reasons() -> None:
    """Block a new embedding space when isolation and citation gates fail."""
    quality = evaluate(
        (
            RetrievalCase(
                "query",
                frozenset({"expected"}),
                ("wrong",),
                cited_document_ids=frozenset({"wrong"}),
            ),
        )
    )
    security = evaluate_security(
        (
            SecurityCase(
                frozenset(),
                ("hidden",),
                injection_present=True,
                injection_detected=False,
            ),
        )
    )
    decision = activation_decision(quality, security, RetrievalThresholds())
    assert decision.passed is False
    assert "citation_correctness" in decision.failures
    assert "unauthorized_results" in decision.failures
    assert "injection_detection_rate" in decision.failures


def test_rejects_empty_golden_and_security_sets() -> None:
    """Reject evaluation runs that could report misleading empty scores."""
    with pytest.raises(ValueError, match="At least one"):
        evaluate(())
    with pytest.raises(ValueError, match="At least one"):
        evaluate_security(())
