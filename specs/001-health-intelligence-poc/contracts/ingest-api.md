# Contract: Ingest API

**Port**: 9000 (matches Device Simulator default `DEFAULT_HTTP_ENDPOINTS`)
**Base path**: `/ingest`
**Auth**: None (internal network; mTLS enforced at IoT Core for MQTT path)

---

## POST /ingest — Accept Simulator Telemetry

Accepts both single-event and batch payloads from the Device Simulator. The endpoint auto-detects
the format by inspecting the presence of a top-level `events` array.

### Request — Single Event

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "smartwatch-a3f9b2c1",
  "device_type": "smartwatch",
  "user_id": "user-4f8e2a",
  "timestamp": "2026-05-04T10:15:30.123456+00:00",
  "scenario": "workout",
  "is_anomaly": false,
  "protocol": "http",
  "firmware_version": "2.2.3",
  "battery_pct": 82,
  "heart_rate": { "bpm": 148, "hrv_ms": 32.5 },
  "spo2": { "percentage": 98.2 },
  "steps": { "count": 412, "distance_m": 313.94, "calories_kcal": 22.66 },
  "temperature": { "celsius": 37.3 },
  "blood_pressure": { "systolic_mmhg": 142, "diastolic_mmhg": 88 },
  "gps": { "latitude": 52.374560, "longitude": 4.895120, "altitude_m": 12.5 },
  "stress": { "score": 54 },
  "hydration": { "level_percent": 63.8 }
}
```

### Request — Batch

```json
{
  "batch_id": "660e8400-e29b-41d4-a716-446655440111",
  "sent_at": "2026-05-04T10:15:30.000000+00:00",
  "event_count": 10,
  "events": [ /* array of single-event objects above */ ]
}
```

### Response — 202 Accepted

```json
{
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "accepted": 10,
  "quarantined": 0,
  "batch_id": "660e8400-e29b-41d4-a716-446655440111"
}
```

| Field | Description |
|-------|-------------|
| `trace_id` | OpenTelemetry trace ID for this request — use for log correlation |
| `accepted` | Number of events passed validation and queued to Kinesis |
| `quarantined` | Number of events that failed validation and were quarantined |
| `batch_id` | Echo of batch ID (null for single events) |

### Response — 422 Unprocessable Entity (all events fail validation)

```json
{
  "trace_id": "...",
  "accepted": 0,
  "quarantined": 1,
  "errors": [
    { "event_id": "...", "field": "device_id", "code": "MISSING", "message": "device_id is required" }
  ]
}
```

### Validation rules

| Rule | Code | HTTP result |
|------|------|-------------|
| `device_id` present and non-empty | `MISSING` | Quarantine event; continue batch |
| `event_id` present (idempotency key) | `MISSING` | Quarantine event |
| `timestamp` parseable as ISO-8601 | `INVALID_TIMESTAMP` | Quarantine event |
| `timestamp` not > 24 h before `received_at` (stale) | — | Accept + set `is_stale=true` |
| `is_anomaly=true` | — | Accept + propagate anomaly flag; metric incremented |
| Unknown `device_id` (not in DB) | `UNKNOWN_DEVICE` | Quarantine event |
| Duplicate `event_id` | `DUPLICATE` | Return 202 with `accepted=0`; not quarantined |
