#!/usr/bin/env python3
"""Seed script: registers N devices via the platform API.

Usage:
    API_ENDPOINT=http://localhost:8000 python scripts/seed_devices.py
    API_ENDPOINT=http://localhost:8000 SEED_DEVICE_COUNT=5 python scripts/seed_devices.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid

import httpx

API_ENDPOINT = os.getenv("API_ENDPOINT", "http://localhost:8100").rstrip("/")
API_KEY = os.getenv("API_KEY", "dev-key")
SEED_DEVICE_COUNT = int(os.getenv("SEED_DEVICE_COUNT", "10"))
DEVICE_TYPES = ["smartwatch", "fitness_tracker", "smartphone", "laptop"]

MODELS = {
    "smartwatch": "HealthWatch Pro 3",
    "fitness_tracker": "FitBand Ultra",
    "smartphone": "HealthPhone X",
    "laptop": "MedBook Pro",
}


def _make_device_payload(index: int) -> dict:
    device_type = DEVICE_TYPES[index % len(DEVICE_TYPES)]
    return {
        "device_id": f"{device_type}-seed-{uuid.uuid4().hex[:8]}",
        "device_type": device_type,
        "model": MODELS[device_type],
        "firmware_version": "1.0.0",
        "os": "FreeRTOS",
        "user_id": f"seed-user-{index + 1:03d}",
        "height_cm": round(random.uniform(155.0, 195.0), 1),
        "weight_kg": round(random.uniform(50.0, 110.0), 1),
    }


async def seed(count: int) -> None:
    succeeded = 0
    failed = 0

    headers = {"X-API-Key": API_KEY}
    async with httpx.AsyncClient(base_url=API_ENDPOINT, headers=headers, timeout=15.0) as client:
        # Verify connectivity
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach {API_ENDPOINT}/health — {exc}", file=sys.stderr)
            sys.exit(1)

        for i in range(count):
            payload = _make_device_payload(i)
            try:
                resp = await client.post("/api/v1/devices", json=payload)
                if resp.status_code in (200, 201):
                    body = resp.json()
                    print(
                        f"  ✓ [{i + 1}/{count}] device_id={body.get('device_id')} credits={body.get('credit_balance')}"
                    )
                    succeeded += 1
                else:
                    print(
                        f"  ✗ [{i + 1}/{count}] HTTP {resp.status_code}: {resp.text[:120]}",
                        file=sys.stderr,
                    )
                    failed += 1
            except Exception as exc:
                print(f"  ✗ [{i + 1}/{count}] Error: {exc}", file=sys.stderr)
                failed += 1

    print(f"\nSeed complete: {succeeded} succeeded, {failed} failed out of {count} devices.")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    print(f"Seeding {SEED_DEVICE_COUNT} device(s) against {API_ENDPOINT}...")
    asyncio.run(seed(SEED_DEVICE_COUNT))
