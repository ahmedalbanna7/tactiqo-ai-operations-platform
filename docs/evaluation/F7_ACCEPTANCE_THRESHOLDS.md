# F7 RAG acceptance thresholds

An embedding space must not be activated when any required gate fails.

| Gate | Minimum/maximum |
|---|---:|
| Recall@5 | >= 0.80 |
| MRR | >= 0.75 |
| Precision@5 | >= 0.60 |
| nDCG@5 | >= 0.75 |
| Citation correctness | 1.00 |
| Answer grounding | >= 0.90 |
| Retrieval latency p95 | <= 2500 ms |
| Unauthorized results | 0 |
| Required injection detection | 1.00 |

These initial engineering thresholds are versioned and conservative. Production activation needs a
representative customer-owned golden set and explicit approval; synthetic fixtures alone cannot
certify production quality.
