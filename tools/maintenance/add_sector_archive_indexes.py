"""Add (symbol, *) indexes to sector archive DBs.

Idempotent. Mirrors the indexes already on datalake_query.db.

Usage:
    python tools/maintenance/add_sector_archive_indexes.py
    python tools/maintenance/add_sector_archive_indexes.py --sector semiconductors
    python tools/maintenance/add_sector_archive_indexes.py --dry-run
"""
import argparse
import sqlite3
import time
from pathlib import Path

ARCHIVE_DIR = Path("data/sector_archive")
INDEXES = [
    ("option_contracts",
     "idx_option_contracts_symbol_trade_date",
     "ON option_contracts(symbol, trade_date)"),
    ("flow_options_scans",
     "idx_flow_options_scans_symbol_scan",
     "ON flow_options_scans(symbol, scan_timestamp)"),
    ("flow_options_scans",
     "idx_flow_options_scans_date_scan",
     "ON flow_options_scans(trade_date, scan_timestamp)"),
]


def existing_index_names(conn):
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}


def table_row_count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return None


def process_archive(db_path: Path, dry_run: bool) -> dict:
    size_before_gb = db_path.stat().st_size / 1e9
    if size_before_gb < 0.001:
        return {"db": db_path.name, "skipped": "empty", "size_before_gb": size_before_gb}

    conn = sqlite3.connect(str(db_path))
    existing = existing_index_names(conn)

    actions = []
    for table, idx_name, idx_def in INDEXES:
        rows = table_row_count(conn, table)
        if rows is None:
            actions.append({"index": idx_name, "skipped": f"no {table} table"})
            continue
        if idx_name in existing:
            actions.append({"index": idx_name, "skipped": "already exists", "rows": rows})
            continue
        if dry_run:
            actions.append({"index": idx_name, "would_create": True, "rows": rows})
            continue
        t0 = time.perf_counter()
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} {idx_def}")
        conn.commit()
        elapsed = time.perf_counter() - t0
        actions.append({"index": idx_name, "created": True,
                        "rows": rows, "seconds": round(elapsed, 1)})

    conn.close()

    size_after_gb = db_path.stat().st_size / 1e9
    return {"db": db_path.name, "size_before_gb": round(size_before_gb, 2),
            "size_after_gb": round(size_after_gb, 2),
            "delta_gb": round(size_after_gb - size_before_gb, 2),
            "actions": actions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sector", help="run on a single sector (basename without .db)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be created; make no changes")
    args = parser.parse_args()

    if not ARCHIVE_DIR.exists():
        raise SystemExit(f"Archive dir not found: {ARCHIVE_DIR}")

    if args.sector:
        targets = [ARCHIVE_DIR / f"{args.sector}.db"]
        if not targets[0].exists():
            raise SystemExit(f"Sector DB not found: {targets[0]}")
    else:
        targets = sorted(ARCHIVE_DIR.glob("*.db"))

    print(f"Targets: {len(targets)} archive(s) ({'DRY-RUN' if args.dry_run else 'LIVE'})")
    print()

    overall_start = time.perf_counter()
    total_delta = 0.0
    for db_path in targets:
        print(f"==> {db_path.name}")
        result = process_archive(db_path, args.dry_run)
        if "skipped" in result:
            print(f"   skipped: {result['skipped']}")
            continue
        for action in result["actions"]:
            print(f"   {action}")
        if not args.dry_run:
            print(f"   size: {result['size_before_gb']} GB -> "
                  f"{result['size_after_gb']} GB (+{result['delta_gb']} GB)")
            total_delta += result["delta_gb"]
        print()

    elapsed_min = (time.perf_counter() - overall_start) / 60
    print(f"Done in {elapsed_min:.1f} min" +
          (f"; total disk delta +{total_delta:.1f} GB" if not args.dry_run else ""))


if __name__ == "__main__":
    main()
