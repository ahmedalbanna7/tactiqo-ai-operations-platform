"""Provider-neutral retrieval quality metrics used by release gates."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalCase:
    """Expected relevant documents for one bilingual test query."""

    query: str
    relevant_document_ids: frozenset[str]
    retrieved_document_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """Aggregate deterministic retrieval scores."""

    recall_at_k: float
    mean_reciprocal_rank: float


def evaluate(cases: tuple[RetrievalCase, ...], k: int = 5) -> RetrievalMetrics:
    """Compute macro Recall@k and MRR for a golden set."""
    if not cases:
        message = "At least one retrieval case is required."
        raise ValueError(message)
    if k < 1:
        message = "k must be positive."
        raise ValueError(message)
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    for case in cases:
        if not case.relevant_document_ids:
            message = "Every case must declare relevant documents."
            raise ValueError(message)
        top_k = case.retrieved_document_ids[:k]
        hits = case.relevant_document_ids.intersection(top_k)
        recalls.append(len(hits) / len(case.relevant_document_ids))
        reciprocal_ranks.append(
            next(
                (1.0 / rank for rank, item in enumerate(case.retrieved_document_ids, 1)
                 if item in case.relevant_document_ids),
                0.0,
            )
        )
    size = len(cases)
    return RetrievalMetrics(sum(recalls) / size, sum(reciprocal_ranks) / size)
