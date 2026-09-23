"""AI provider metrics use fixed labels and cannot expose customer identifiers."""

from tactiqo.ai.application.telemetry import ProviderCallMetrics


def test_provider_metrics_collapse_unknown_labels_and_record_latency() -> None:
    """Profile, model and tenant strings cannot create unbounded metric series."""
    metrics = ProviderCallMetrics()
    metrics.observe("openai", "llm_answer", "success", 120)
    metrics.observe("tenant-profile-secret", "model-name-secret", "unexpected", 250)

    rendered = metrics.render_prometheus()

    assert (
        'tactiqo_ai_provider_calls_total{provider="openai",operation="llm_answer",'
        'outcome="success"} 1'
    ) in rendered
    assert (
        'tactiqo_ai_provider_calls_total{provider="other",operation="other",'
        'outcome="failure"} 1'
    ) in rendered
    assert 'le="0.25"' in rendered
    assert "tenant-profile-secret" not in rendered
    assert "model-name-secret" not in rendered
    assert "org-a" not in rendered
