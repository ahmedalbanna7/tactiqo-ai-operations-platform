"""Deterministic lifecycle and retry policies."""

import random
from dataclasses import dataclass
from datetime import timedelta

from tactiqo.jobs.domain.models import JobStatus


class InvalidJobTransitionError(ValueError):
    """Requested lifecycle transition is not permitted."""


_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.WAITING_APPROVAL,
            JobStatus.RETRY_SCHEDULED,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTER,
        }
    ),
    JobStatus.WAITING_APPROVAL: frozenset(
        {JobStatus.QUEUED, JobStatus.CANCELLED, JobStatus.FAILED}
    ),
    JobStatus.RETRY_SCHEDULED: frozenset(
        {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.DEAD_LETTER}
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.DEAD_LETTER: frozenset({JobStatus.QUEUED}),
}


def require_transition(current: JobStatus, target: JobStatus) -> None:
    """Reject non-deterministic or terminal-state transitions."""
    if target not in _TRANSITIONS[current]:
        message = f"job_transition_denied:{current.value}:{target.value}"
        raise InvalidJobTransitionError(message)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential retry with bounded jitter for idempotent work only."""

    base_seconds: float = 2.0
    maximum_seconds: float = 300.0
    jitter_ratio: float = 0.2

    def delay(self, attempt_number: int, *, seed: int | None = None) -> timedelta:
        """Return a bounded reproducible delay when seeded in tests."""
        exponential = min(
            self.maximum_seconds,
            self.base_seconds * (2 ** max(0, attempt_number - 1)),
        )
        jitter = exponential * self.jitter_ratio * random.Random(seed).random()  # noqa: S311
        return timedelta(seconds=min(self.maximum_seconds, exponential + jitter))
