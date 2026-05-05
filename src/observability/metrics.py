from prometheus_client import Counter, Gauge, Histogram

INGEST_EVENTS_TOTAL = Counter(
    "ingest_events_total",
    "Total number of telemetry events processed",
    ["protocol", "status"],
)

INGEST_QUARANTINE_TOTAL = Counter(
    "ingest_quarantine_total",
    "Total number of events quarantined",
)

RECOMMENDATION_REQUESTS_TOTAL = Counter(
    "recommendation_requests_total",
    "Total recommendation requests",
    ["provider_count"],
)

RECOMMENDATION_ERRORS_TOTAL = Counter(
    "recommendation_errors_total",
    "Total failed recommendation requests",
    ["reason"],
)

RECOMMENDATION_DURATION_SECONDS = Histogram(
    "recommendation_duration_seconds",
    "Recommendation aggregation latency in seconds",
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
)

ACTIVE_DEVICES_TOTAL = Gauge(
    "active_devices_total",
    "Number of registered devices",
)

DEVICE_CREDIT_BALANCE = Gauge(
    "device_credit_balance",
    "Current credit balance per device",
    ["device_id"],
)

DEVICE_CREDITS_EARNED = Counter(
    "device_credits_earned_total",
    "Cumulative credits earned per device",
    ["device_id", "action_type"],
)

DEVICE_CREDITS_SPENT = Counter(
    "device_credits_spent_total",
    "Cumulative credits spent per device",
    ["device_id"],
)

DEVICE_STREAK_DAYS = Gauge(
    "device_streak_days",
    "Current streak days per device",
    ["device_id"],
)

CREDIT_TIER_TOTAL = Gauge(
    "credit_tier_total",
    "Number of devices per reward tier",
    ["tier"],
)

# ── ML Monitoring Metrics (FR-018) ────────────────────────────────────────────

ML_RERANKER_NDCG_AT_10 = Gauge(
    "ml_reranker_ndcg_at_10",
    "Re-ranker NDCG@10 from the most recent training evaluation",
)

ML_ANOMALY_F1_SCORE = Gauge(
    "ml_anomaly_detector_f1_score",
    "Anomaly detector F1 score from the most recent training evaluation",
)

ML_INFERENCE_P99_LATENCY_MS = Gauge(
    "ml_inference_p99_latency_ms",
    "P99 ML inference latency in milliseconds (300-second rolling window)",
)

ML_MODEL_STALENESS_SECONDS = Gauge(
    "ml_model_staleness_seconds",
    "Seconds elapsed since the last successful model training run",
)

ML_INFERENCE_OUTCOME_TOTAL = Counter(
    "ml_inference_outcome_total",
    "ML inference outcomes for recommendation requests",
    ["outcome"],  # scored | cold_start | fallback
)

ML_ANOMALY_SUPPRESSED_ITEMS_TOTAL = Counter(
    "ml_anomaly_suppressed_items_total",
    "Total recommendation items suppressed due to anomaly detection",
)

ML_ANOMALY_REQUESTS_EVALUATED_TOTAL = Counter(
    "ml_anomaly_requests_evaluated_total",
    "Total recommendation requests where anomaly detection was evaluated with a baseline",
)
