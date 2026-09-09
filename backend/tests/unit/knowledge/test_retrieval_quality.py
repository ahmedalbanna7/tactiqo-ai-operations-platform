"""Tests for bilingual retrieval release-gate metrics."""

import pytest

from tactiqo.knowledge.application.retrieval_quality import RetrievalCase, evaluate


def test_computes_recall_and_mrr_for_bilingual_cases() -> None:
    """Calculate deterministic metrics over Arabic and English queries."""
    metrics = evaluate((
        RetrievalCase("ما هي ميزانية المشروع؟", frozenset({"budget"}), ("plan", "budget")),
        RetrievalCase("When is the project deadline?", frozenset({"plan"}), ("plan", "risk")),
    ))
    assert metrics.recall_at_k == 1.0
    assert metrics.mean_reciprocal_rank == pytest.approx(0.75)


def test_rejects_empty_golden_set() -> None:
    """Reject an evaluation that could report a misleading empty score."""
    with pytest.raises(ValueError, match="At least one"):
        evaluate(())
