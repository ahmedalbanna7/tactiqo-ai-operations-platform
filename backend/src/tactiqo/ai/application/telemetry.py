"""Bounded process-local telemetry for AI provider calls."""

import math
from threading import Lock

_PROVIDERS = frozenset({"lm_studio", "openai", "claude"})
_OPERATIONS = frozenset({"llm_plan", "llm_answer", "embedding"})
_OUTCOMES = frozenset({"success", "failure"})
_HISTOGRAM_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class ProviderCallMetrics:
    """Aggregate provider outcomes without tenant, profile, model, or prompt labels."""

    def __init__(self) -> None:
        """Create a bounded in-memory registry."""
        self._lock = Lock()
        self._series: dict[tuple[str, str, str], tuple[int, float, tuple[int, ...]]] = {}

    def observe(
        self, provider: str, operation: str, outcome: str, duration_ms: float
    ) -> None:
        """Record one routed provider attempt with labels from fixed allowlists."""
        safe_provider = (
            provider if isinstance(provider, str) and provider in _PROVIDERS else "other"
        )
        safe_operation = (
            operation if isinstance(operation, str) and operation in _OPERATIONS else "other"
        )
        safe_outcome = outcome if isinstance(outcome, str) and outcome in _OUTCOMES else "failure"
        try:
            duration_seconds = float(duration_ms) / 1000
        except (OverflowError, TypeError, ValueError):
            duration_seconds = 0.0
        if not math.isfinite(duration_seconds):
            duration_seconds = 0.0
        duration_seconds = max(duration_seconds, 0.0)
        key = (safe_provider, safe_operation, safe_outcome)
        with self._lock:
            count, total, buckets = self._series.get(
                key, (0, 0.0, (0,) * len(_HISTOGRAM_BUCKETS))
            )
            observed_buckets = tuple(
                bucket_count + int(duration_seconds <= upper_bound)
                for bucket_count, upper_bound in zip(
                    buckets, _HISTOGRAM_BUCKETS, strict=True
                )
            )
            self._series[key] = (count + 1, total + duration_seconds, observed_buckets)

    def render_prometheus(self) -> str:
        """Render stable, low-cardinality Prometheus counters and latency histograms."""
        lines = [
            "# TYPE tactiqo_ai_provider_calls_total counter",
            "# TYPE tactiqo_ai_provider_call_duration_seconds histogram",
        ]
        with self._lock:
            snapshot = tuple(sorted(self._series.items()))
        for (provider, operation, outcome), (count, total, buckets) in snapshot:
            labels = self._labels(provider, operation, outcome)
            lines.append(f"tactiqo_ai_provider_calls_total{{{labels}}} {count}")
            for bucket_count, upper_bound in zip(
                buckets, _HISTOGRAM_BUCKETS, strict=True
            ):
                bucket_labels = self._labels(
                    provider, operation, outcome, le=f"{upper_bound:g}"
                )
                lines.append(
                    "tactiqo_ai_provider_call_duration_seconds_bucket"
                    f"{{{bucket_labels}}} {bucket_count}"
                )
            infinity_labels = self._labels(provider, operation, outcome, le="+Inf")
            lines.extend(
                (
                    "tactiqo_ai_provider_call_duration_seconds_bucket"
                    f"{{{infinity_labels}}} {count}",
                    f"tactiqo_ai_provider_call_duration_seconds_sum{{{labels}}} {total:.9g}",
                    f"tactiqo_ai_provider_call_duration_seconds_count{{{labels}}} {count}",
                )
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _labels(
        provider: str,
        operation: str,
        outcome: str,
        *,
        le: str | None = None,
    ) -> str:
        """Build labels exclusively from internally allowlisted values."""
        labels = [
            f'provider="{provider}"',
            f'operation="{operation}"',
            f'outcome="{outcome}"',
        ]
        if le is not None:
            labels.append(f'le="{le}"')
        return ",".join(labels)
