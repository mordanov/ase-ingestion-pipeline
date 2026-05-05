"""Compact accumulated small part-files in Delta Lake tables
with proper Delta log retention control.

Usage:
    python scripts/compact_delta.py \
        [--base-dir ./data/delta] \
        [--recommendations-dir ./data/recommendations] \
        [--log-retention-hours 24] \
        [--dry-run]
"""

import argparse
import sys
from pathlib import Path

from deltalake import DeltaTable
from deltalake.exceptions import TableNotFoundError


def _print_retention_info(dt: DeltaTable, label: str):
    metadata = dt.metadata()
    config = metadata.configuration or {}

    log_retention = config.get("delta.logRetentionDuration")
    deleted_retention = config.get("delta.deletedFileRetentionDuration")

    print(f"[{label}] Table properties:")
    print(f"[{label}]   delta.logRetentionDuration        = {log_retention}")
    print(f"[{label}]   delta.deletedFileRetentionDuration = {deleted_retention}")

    if not log_retention:
        print(
            f"[{label}] WARNING: log retention is NOT set. "
            f"cleanup_metadata() may keep logs much longer than expected.",
            file=sys.stderr,
        )


def compact_table(path: Path, label: str, dry_run: bool, log_retention_hours: int) -> bool:
    if not path.exists():
        print(f"[{label}] Directory not found: {path}", file=sys.stderr)
        return False

    try:
        dt = DeltaTable(str(path))
    except TableNotFoundError:
        print(f"[{label}] No Delta table found at {path}. Skipping.", file=sys.stderr)
        return False

    version_before = dt.version()
    files_before = len(dt.file_uris())

    print(f"[{label}] Delta table version : {version_before}")
    print(f"[{label}] Part-files          : {files_before}")
    print(f"[{label}] Partitions          : {', '.join(dt.metadata().partition_columns)}")

    _print_retention_info(dt, label)

    if dry_run:
        print(f"[{label}] [dry-run] No changes applied.")
        return True

    # --- COMPACT ---
    print(f"[{label}] Compacting {files_before} part-file(s)…")
    metrics = dt.optimize.compact()
    print(f"[{label}]   files removed : {metrics.get('numFilesRemoved', '?')}")
    print(f"[{label}]   files added   : {metrics.get('numFilesAdded', '?')}")

    # --- VACUUM (data files only) ---
    print(f"[{label}] Vacuuming data files (retention = {log_retention_hours} h)…")
    removed = dt.vacuum(
        retention_hours=log_retention_hours,
        enforce_retention_duration=False,
        dry_run=False,
    )
    print(f"[{label}]   removed data files : {len(removed)}")

    # --- CHECKPOINT ---
    print(f"[{label}] Writing checkpoint…")
    dt.create_checkpoint()

    # --- CLEANUP LOG ---
    print(f"[{label}] Cleaning old Delta log entries…")
    dt.cleanup_metadata()

    print(f"[{label}] Done. Version={dt.version()}, files={len(dt.file_uris())}")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact Delta Lake tables")
    parser.add_argument("--base-dir", default="./data/delta")
    parser.add_argument("--recommendations-dir", default="./data/recommendations")
    parser.add_argument("--log-retention-hours", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    ok_events = compact_table(Path(args.base_dir), "events", args.dry_run, args.log_retention_hours)
    ok_recs = compact_table(
        Path(args.recommendations_dir), "recommendations", args.dry_run, args.log_retention_hours
    )

    if not ok_events and not ok_recs:
        sys.exit(1)


if __name__ == "__main__":
    main()
