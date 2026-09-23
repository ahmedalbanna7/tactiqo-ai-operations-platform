"""F5 lifecycle and retry policy tests."""

from datetime import timedelta

import pytest

from tactiqo.jobs.application.policy import (
    InvalidJobTransitionError,
    RetryPolicy,
    require_transition,
)
from tactiqo.jobs.domain.models import JobStatus


def test_terminal_job_cannot_restart_automatically() -> None:
    """Completed work is never duplicated by an automatic worker retry."""
    with pytest.raises(InvalidJobTransitionError):
        require_transition(JobStatus.COMPLETED, JobStatus.RUNNING)


def test_retry_requires_explicit_retry_state() -> None:
    """A running attempt schedules retry before returning to a queue."""
    require_transition(JobStatus.RUNNING, JobStatus.RETRY_SCHEDULED)
    require_transition(JobStatus.RETRY_SCHEDULED, JobStatus.QUEUED)


def test_retry_backoff_is_bounded_and_reproducible() -> None:
    """Poison work cannot create an unbounded hot retry loop."""
    policy = RetryPolicy(base_seconds=2, maximum_seconds=30, jitter_ratio=0.2)

    assert policy.delay(1, seed=7) == policy.delay(1, seed=7)
    assert policy.delay(100, seed=7) <= timedelta(seconds=30)
