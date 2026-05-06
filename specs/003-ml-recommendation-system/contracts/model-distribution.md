# Contract: Model Distribution

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)  
**Implemented by**: `src/ml/distributor.py` + existing device sync protocol (A-004)

---

## Overview

This contract defines the structure of the `OnDeviceModelPackage` — the artifact produced by the `Distributor` component and pushed to devices via the existing sync protocol (A-004). It does **not** define the transport mechanism (that is handled by the existing sync infrastructure).

The package is pushed up to 10 times per day (FR-011). Devices use the `manifest.json` inside the package to verify compatibility before loading the new models (FR-012 scenario 4).

---

## Package Structure

The distribution artifact is a ZIP archive named:

```
ml_package_v{reranker_version}_{anomaly_version}_{timestamp}.zip
```

Example: `ml_package_v7_7_20260505T151000Z.zip`

### ZIP Contents

```
ml_package_v7_7_20260505T151000Z.zip
├── reranker.tflite              # Re-ranker model (two-tower scoring)
├── anomaly_detector.tflite      # Anomaly detector model
└── manifest.json                # Version and compatibility metadata
```

---

## manifest.json Schema

```json
{
  "schema_version": 1,
  "created_at": "2026-05-05T15:10:00Z",
  "reranker": {
    "version": 7,
    "input_dim": 64,
    "output_dim": 1,
    "filename": "reranker.tflite"
  },
  "anomaly_detector": {
    "version": 7,
    "input_dim": 16,
    "output_dim": 1,
    "filename": "anomaly_detector.tflite"
  },
  "compatibility": {
    "min_tflite_runtime_version": "2.13.0",
    "supported_platforms": ["android", "ios", "linux-arm64"]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| schema_version | int | Monotonically increasing; allows future format changes |
| created_at | ISO-8601 | UTC; used by the device to determine freshness |
| reranker.version | int | Matches TrainedModel.version |
| reranker.input_dim | int | Number of floats in the user embedding vector |
| reranker.output_dim | int | Always 1 (relevance score) |
| anomaly_detector.version | int | Matches TrainedModel.version |
| anomaly_detector.input_dim | int | Number of telemetry feature floats |
| anomaly_detector.output_dim | int | Always 1 (anomaly score in [0, 1]) |
| compatibility.min_tflite_runtime_version | semver string | Devices below this version MUST NOT load this package |
| compatibility.supported_platforms | string[] | Informational; device SDK validates against its own identifier |

---

## Device Behaviour on Receipt

1. **Unzip** the archive to a temporary staging directory.
2. **Parse `manifest.json`** — if `schema_version` is unknown, discard the package and log the incompatibility.
3. **Check `min_tflite_runtime_version`** against the device's installed TFLite runtime version.
   - If incompatible: retain the previous package, log `"ml_package_incompatible"` with version details (FR-012 scenario 4). Do not replace the active models.
4. **Replace active models** by atomically swapping the staging directory for the active model directory.
5. **Log** `"ml_package_applied"` with `reranker.version`, `anomaly_detector.version`, `created_at`.

---

## GET /admin/ml/model-package/latest

Returns metadata about the most recently built `OnDeviceModelPackage`. Used by device sync infrastructure to determine whether a new package is available and to fetch the download URL.

**Auth**: API key required (`X-API-Key` header).

### Response — 200 OK (package available)

```json
{
  "package_id": "a3b5c7d9-...",
  "reranker_version": 7,
  "anomaly_detector_version": 7,
  "created_at": "2026-05-05T15:10:00Z",
  "download_url": "/admin/ml/model-package/a3b5c7d9-.../download",
  "size_bytes": 4823041
}
```

### Response — 404 Not Found (no package built yet)

```json
{ "detail": "No model package has been built yet" }
```

---

## GET /admin/ml/model-package/{package_id}/download

Returns the ZIP archive for download (binary response, `Content-Type: application/zip`).

### Response — 200 OK

Binary ZIP stream. `Content-Disposition: attachment; filename="ml_package_v7_7_20260505T151000Z.zip"`.

### Response — 404 Not Found

```json
{ "detail": "Package not found" }
```

---

## Acceptance Criteria (from spec)

- A device with a previously distributed model and local telemetry buffer returns a ranked list within 1 second without internet (US3 scenario 1, FR-010).
- A device that has never received a model falls back to raw unranked list without error (US3 scenario 2, FR-012).
- A device with an incompatible runtime retains its previous model and logs the failure (US3 scenario 4).
- The package is available for distribution within the device sync schedule — up to 10 distributions per day (FR-011).
