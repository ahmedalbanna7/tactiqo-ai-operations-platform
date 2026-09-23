"""Bounded aggregate metrics for remote tool gateway calls."""

import math
from threading import Lock

_SERVER_FAMILIES = frozenset({"slack", "jira", "confluence", "demo"})
_OUTCOMES = frozenset({"success", "failure"})
_HISTOGRAM_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class ToolCallMetrics:
    """Store process-local tool outcomes with fixed server-family labels only."""

    def __init__(self) -> None:
        """Initialize an empty bounded registry."""
        self._lock = Lock()
        self._series: dict[tuple[str, str], tuple[int, float, tuple[int, ...]]] = {}

    def observe(self, server_family: str, outcome: str, duration_ms: float) -> None:
        """Record one call using only allowlisted family and outcome labels."""
        family = (
            server_family
            if isinstance(server_family, str) and server_family in _SERVER_FAMILIES
            else "other"
        )
        safe_outcome = outcome if isinstance(outcome, str) and outcome in _OUTCOMES else "failure"
        try:
            duration_seconds = float(duration_ms) / 1000
        except (OverflowError, TypeError, ValueError):
            duration_seconds = 0.0
        if not math.isfinite(duration_seconds):
            duration_seconds = 0.0
        duration_seconds = max(duration_seconds, 0.0)
        key = (family, safe_outcome)
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
        """Render stable, low-cardinality call counters and latency histograms."""
        lines = [
            "# TYPE tactiqo_tool_calls_total counter",
            "# TYPE tactiqo_tool_call_duration_seconds histogram",
        ]
        with self._lock:
            snapshot = tuple(sorted(self._series.items()))
        for (family, outcome), (count, total, buckets) in snapshot:
            labels = self._labels(family, outcome)
            lines.append(f"tactiqo_tool_calls_total{{{labels}}} {count}")
            for bucket_count, upper_bound in zip(
                buckets, _HISTOGRAM_BUCKETS, strict=True
            ):
                bucket_labels = self._labels(family, outcome, le=f"{upper_bound:g}")
                lines.append(
                    "tactiqo_tool_call_duration_seconds_bucket"
                    f"{{{bucket_labels}}} {bucket_count}"
                )
            infinity_labels = self._labels(family, outcome, le="+Inf")
            lines.extend(
                (
                    "tactiqo_tool_call_duration_seconds_bucket"
                    f"{{{infinity_labels}}} {count}",
                    f"tactiqo_tool_call_duration_seconds_sum{{{labels}}} {total:.9g}",
                    f"tactiqo_tool_call_duration_seconds_count{{{labels}}} {count}",
                )
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _labels(server_family: str, outcome: str, *, le: str | None = None) -> str:
        """Build labels only from allowlisted family/outcome values."""
        labels = [f'server_family="{server_family}"', f'outcome="{outcome}"']
        if le is not None:
            labels.append(f'le="{le}"')
        return ",".join(labels)
