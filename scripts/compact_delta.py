"""Compact accumulated small part-files in Delta Lake tables.

Delta Lake's optimize().compact() rewrites many small files into larger ones
within each partition.  vacuum() then removes the superseded files (retention
is set to 0 h for the PoC; increase it if you need time-travel).

Usage:
    python scripts/compact_delta.py [--base-dir ./data/delta]
                                    [--recommendations-dir ./data/recommendations]
                                    [--dry-run]
"""

import argparse
import sys
from pathlib import Path

from deltalake import DeltaTable
from deltalake.exceptions import TableNotFoundError


def compact_table(path: Path, label: str, dry_run: bool) -> bool:
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

    if dry_run:
        print(f"[{label}] Delta table version : {version_before}")
        print(f"[{label}] Part-files          : {files_before}")
        print(f"[{label}] Partitions          : {', '.join(dt.metadata().partition_columns)}")
        print(f"[{label}] [dry-run] No files written.")
        return True

    print(f"[{label}] Compacting {files_before} part-file(s) (version {version_before})…")
    metrics = dt.optimize.compact()
    print(f"[{label}]   files removed : {metrics.get('numFilesRemoved', '?')}")
    print(f"[{label}]   files added   : {metrics.get('numFilesAdded', '?')}")

    print(f"[{label}] Vacuuming superseded files (retention = 0 h)…")
    removed = dt.vacuum(retention_hours=0, enforce_retention_duration=False, dry_run=False)
    print(f"[{label}]   removed       : {len(removed)} file(s)")

    print(f"[{label}] Done. Table is now at version {dt.version()} with {len(dt.file_uris())} part-file(s).")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact Delta Lake tables")
    parser.add_argument("--base-dir", default="./data/delta", help="Root of the events Delta table")
    parser.add_argument("--recommendations-dir", default="./data/recommendations", help="Root of the recommendations Delta table")
    parser.add_argument("--dry-run", action="store_true", help="Report stats without rewriting files")
    args = parser.parse_args()

    ok_events = compact_table(Path(args.base_dir), "events", args.dry_run)
    ok_recs = compact_table(Path(args.recommendations_dir), "recommendations", args.dry_run)

    if not ok_events and not ok_recs:
        sys.exit(1)


if __name__ == "__main__":
    main()
