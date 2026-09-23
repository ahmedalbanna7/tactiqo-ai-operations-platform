"""Deterministic multilingual retrieval and security release gates."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalCase:
    """Expected ranking, citation, grounding, and latency for one query."""

    query: str
    relevant_document_ids: frozenset[str]
    retrieved_document_ids: tuple[str, ...]
    relevance_grades: tuple[tuple[str, int], ...] = ()
    cited_document_ids: frozenset[str] = frozenset()
    answer_grounded: bool | None = None
    latency_ms: int = 0
    language: str = "und"


@dataclass(frozen=True, slots=True)
class SecurityCase:
    """Authorized retrieval output and expected injection detection."""

    authorized_document_ids: frozenset[str]
    retrieved_document_ids: tuple[str, ...]
    injection_present: bool = False
    injection_detected: bool = False


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """Aggregate quality, citation, grounding, latency, and isolation scores."""

    recall_at_k: float
    mean_reciprocal_rank: float
    precision_at_k: float
    ndcg_at_k: float
    citation_correctness: float
    answer_grounding: float
    latency_p95_ms: int


@dataclass(frozen=True, slots=True)
class SecurityMetrics:
    """Fail-closed retrieval isolation and injection-detection scores."""

    unauthorized_results: int
    injection_detection_rate: float


@dataclass(frozen=True, slots=True)
class RetrievalThresholds:
    """Minimum accepted scores for embedding-space activation."""

    recall_at_k: float = 0.80
    mean_reciprocal_rank: float = 0.75
    precision_at_k: float = 0.60
    ndcg_at_k: float = 0.75
    citation_correctness: float = 1.0
    answer_grounding: float = 0.90
    maximum_latency_p95_ms: int = 2_500
    maximum_unauthorized_results: int = 0
    injection_detection_rate: float = 1.0


@dataclass(frozen=True, slots=True)
class EvaluationDecision:
    """Machine-readable activation decision with exact failed gates."""

    passed: bool
    failures: tuple[str, ...]


def evaluate(cases: tuple[RetrievalCase, ...], k: int = 5) -> RetrievalMetrics:
    """Compute macro retrieval, citation, grounding, and p95 latency metrics."""
    if not cases:
        message = "At least one retrieval case is required."
        raise ValueError(message)
    if k < 1:
        message = "k must be positive."
        raise ValueError(message)
    recalls: list[float] = []
    precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    citation_scores: list[float] = []
    grounding_scores: list[float] = []
    latencies: list[int] = []
    for case in cases:
        if not case.relevant_document_ids:
            message = "Every case must declare relevant documents."
            raise ValueError(message)
        top_k = case.retrieved_document_ids[:k]
        hits = case.relevant_document_ids.intersection(top_k)
        recalls.append(len(hits) / len(case.relevant_document_ids))
        precisions.append(len(hits) / max(1, min(k, len(top_k))))
        reciprocal_ranks.append(_reciprocal_rank(case))
        ndcgs.append(_ndcg(case, k))
        if case.cited_document_ids:
            citation_scores.append(
                len(case.cited_document_ids.intersection(case.relevant_document_ids))
                / len(case.cited_document_ids)
            )
        if case.answer_grounded is not None:
            grounding_scores.append(float(case.answer_grounded))
        latencies.append(max(0, case.latency_ms))
    size = len(cases)
    return RetrievalMetrics(
        recall_at_k=sum(recalls) / size,
        mean_reciprocal_rank=sum(reciprocal_ranks) / size,
        precision_at_k=sum(precisions) / size,
        ndcg_at_k=sum(ndcgs) / size,
        citation_correctness=sum(citation_scores) / len(citation_scores)
        if citation_scores
        else 0.0,
        answer_grounding=sum(grounding_scores) / len(grounding_scores) if grounding_scores else 0.0,
        latency_p95_ms=_percentile_95(latencies),
    )


def evaluate_security(cases: tuple[SecurityCase, ...]) -> SecurityMetrics:
    """Count every unauthorized result and measure required injection detection."""
    if not cases:
        message = "At least one security case is required."
        raise ValueError(message)
    unauthorized = sum(
        len(set(case.retrieved_document_ids) - case.authorized_document_ids) for case in cases
    )
    injection_cases = [case for case in cases if case.injection_present]
    detection_rate = (
        sum(case.injection_detected for case in injection_cases) / len(injection_cases)
        if injection_cases
        else 1.0
    )
    return SecurityMetrics(unauthorized, detection_rate)


def activation_decision(
    quality: RetrievalMetrics,
    security: SecurityMetrics,
    thresholds: RetrievalThresholds | None = None,
) -> EvaluationDecision:
    """Fail closed when any required quality or security threshold is missed."""
    thresholds = thresholds or RetrievalThresholds()
    checks = {
        "recall_at_k": quality.recall_at_k >= thresholds.recall_at_k,
        "mean_reciprocal_rank": quality.mean_reciprocal_rank >= thresholds.mean_reciprocal_rank,
        "precision_at_k": quality.precision_at_k >= thresholds.precision_at_k,
        "ndcg_at_k": quality.ndcg_at_k >= thresholds.ndcg_at_k,
        "citation_correctness": quality.citation_correctness >= thresholds.citation_correctness,
        "answer_grounding": quality.answer_grounding >= thresholds.answer_grounding,
        "latency_p95_ms": quality.latency_p95_ms <= thresholds.maximum_latency_p95_ms,
        "unauthorized_results": security.unauthorized_results
        <= thresholds.maximum_unauthorized_results,
        "injection_detection_rate": security.injection_detection_rate
        >= thresholds.injection_detection_rate,
    }
    failures = tuple(name for name, passed in checks.items() if not passed)
    return EvaluationDecision(not failures, failures)


def _reciprocal_rank(case: RetrievalCase) -> float:
    return next(
        (
            1.0 / rank
            for rank, item in enumerate(case.retrieved_document_ids, 1)
            if item in case.relevant_document_ids
        ),
        0.0,
    )


def _ndcg(case: RetrievalCase, k: int) -> float:
    grades: dict[str, int] = dict(case.relevance_grades) or dict.fromkeys(
        case.relevant_document_ids, 1
    )
    gains = [grades.get(document_id, 0) for document_id in case.retrieved_document_ids[:k]]
    ideal = sorted(grades.values(), reverse=True)[:k]

    def discounted(values: list[int]) -> float:
        return float(
            sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(values, 1))
        )

    ideal_score = discounted(ideal)
    return discounted(gains) / ideal_score if ideal_score else 0.0


def _percentile_95(values: list[int]) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]
