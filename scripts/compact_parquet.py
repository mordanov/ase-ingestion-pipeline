"""Compact many small per-request Parquet files into one file per partition.

Walks every Hive leaf directory under <base_dir> (those that contain .parquet
files), reads them all, writes a single events_compacted.parquet, and deletes
the originals.  Already-compacted directories (single file named
events_compacted.parquet) are skipped.

Usage:
    python scripts/compact_parquet.py [--base-dir ./data/parquet] [--dry-run]
"""

import argparse
import os
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def find_leaf_dirs(base: Path) -> list[Path]:
    """Return all directories that contain at least one .parquet file."""
    leaves = []
    for root, _dirs, files in os.walk(base):
        parquet_files = [f for f in files if f.endswith(".parquet")]
        if parquet_files:
            leaves.append(Path(root))
    return sorted(leaves)


def compact_dir(leaf: Path, dry_run: bool) -> tuple[int, int, int]:
    """Compact all .parquet files in *leaf* into events_compacted.parquet.

    Returns (files_merged, rows_written, bytes_saved).
    """
    files = sorted(leaf.glob("*.parquet"))

    already_compacted = files == [leaf / "events_compacted.parquet"]
    if already_compacted:
        return 0, 0, 0

    tables = [pq.read_table(f) for f in files]
    merged = pa.concat_tables(tables)
    rows = len(merged)

    size_before = sum(f.stat().st_size for f in files)

    out = leaf / "events_compacted.parquet"
    if not dry_run:
        pq.write_table(merged, out, compression="snappy")
        for f in files:
            if f != out:
                f.unlink()

    size_after = out.stat().st_size if (not dry_run and out.exists()) else size_before
    return len(files), rows, size_before - size_after


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact Parquet partitions")
    parser.add_argument("--base-dir", default="./data/parquet", help="Root of the Parquet archive")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be done without writing")
    args = parser.parse_args()

    base = Path(args.base_dir)
    if not base.exists():
        print(f"Directory not found: {base}", file=sys.stderr)
        sys.exit(1)

    leaves = find_leaf_dirs(base)
    if not leaves:
        print("No Parquet files found.")
        return

    total_files = total_rows = total_saved = 0
    for leaf in leaves:
        files_merged, rows, saved = compact_dir(leaf, args.dry_run)
        if files_merged == 0:
            continue
        rel = leaf.relative_to(base)
        tag = "[dry-run] " if args.dry_run else ""
        print(f"{tag}{rel}: merged {files_merged} files → {rows:,} rows, saved {saved / 1024:.1f} KB")
        total_files += files_merged
        total_rows += rows
        total_saved += saved

    if total_files == 0:
        print("Nothing to compact — all partitions already have a single file.")
    else:
        tag = "[dry-run] " if args.dry_run else ""
        print(f"\n{tag}Done: {total_files} files → {total_rows:,} rows, {total_saved / 1024:.1f} KB reclaimed")


if __name__ == "__main__":
    main()
