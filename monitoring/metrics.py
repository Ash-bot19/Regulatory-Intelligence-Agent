"""
Prometheus metrics for the Regulatory Intelligence Agent.

Tracked signals (per CLAUDE.md Phase 5 requirements):
  - query_count: total queries received (labelled by outcome: answered / gate_fired / error)
  - gate_fire_rate: proportion of queries where gate fired (derived from query_count labels)
  - confidence_score: histogram of top retrieved chunk similarity scores

Exposed at GET /metrics via prometheus_client.make_asgi_app().
"""

from prometheus_client import Counter, Histogram, make_asgi_app

# Total query counter — label outcome: "answered" | "gate_fired" | "error"
query_counter = Counter(
    "ria_queries_total",
    "Total number of queries received by the Regulatory Intelligence Agent",
    ["outcome"],
)

# Confidence score distribution — allows p50/p95/p99 and avg in Grafana
confidence_histogram = Histogram(
    "ria_confidence_score",
    "Distribution of top retrieved chunk similarity scores",
    buckets=[0.0, 0.3, 0.5, 0.6, 0.65, 0.70, 0.72, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0],
)

# LLM response latency
llm_latency_histogram = Histogram(
    "ria_llm_latency_seconds",
    "LLM call latency in seconds",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0],
)


def metrics_app():
    """Return the ASGI app that serves Prometheus metrics at /metrics."""
    return make_asgi_app()
