"""Add (symbol, trade_date) composite index to flow_symbol_summary.

Targets production datalake.db AND all 20 sector archive DBs.
Idempotent — safe to re-run. P028 Step 10.

Production motivation: flow_symbol_summary's existing indexes are single-column
(idx_symbol, idx_date). The composite improves WHERE symbol=? AND trade_date BETWEEN ?
patterns that show up in research queries against the 300d-retention table.

Archive motivation: P025 covered option_contracts and flow_options_scans archive
indexes but missed flow_symbol_summary. Its PK is (trade_date, symbol), so
symbol-pivoted lookups full-scan without this composite.

Usage:
    python tools/maintenance/add_flow_symbol_summary_index.py
    python tools/maintenance/add_flow_symbol_summary_index.py --dry-run
    python tools/maintenance/add_flow_symbol_summary_index.py --production-only
    python tools/maintenance/add_flow_symbol_summary_index.py --archives-only
    python tools/maintenance/add_flow_symbol_summary_index.py --sector semiconductors
"""
import argparse
import sqlite3
import time
from pathlib import Path

PROD_DB = Path("data/datalake.db")
ARCHIVE_DIR = Path("data/sector_archive")
INDEX_NAME = "idx_flow_symbol_summary_symbol_date"
INDEX_DDL = f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON flow_symbol_summary(symbol, trade_date)"


def existing_index_names(conn):
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}


def table_row_count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return None


def process_db(db_path: Path, dry_run: bool) -> dict:
    size_before_gb = db_path.stat().st_size / 1e9
    if size_before_gb < 0.001:
        return {"db": db_path.name, "skipped": "empty", "size_before_gb": size_before_gb}

    conn = sqlite3.connect(str(db_path))
    existing = existing_index_names(conn)

    rows = table_row_count(conn, "flow_symbol_summary")
    if rows is None:
        conn.close()
        return {"db": db_path.name, "skipped": "no flow_symbol_summary table"}

    if INDEX_NAME in existing:
        conn.close()
        return {"db": db_path.name, "action": "already_exists", "rows": rows,
                "size_before_gb": round(size_before_gb, 3)}

    if dry_run:
        conn.close()
        return {"db": db_path.name, "action": "would_create", "rows": rows,
                "size_before_gb": round(size_before_gb, 3)}

    t0 = time.perf_counter()
    conn.execute(INDEX_DDL)
    conn.commit()
    elapsed = time.perf_counter() - t0
    conn.close()

    size_after_gb = db_path.stat().st_size / 1e9
    return {"db": db_path.name, "action": "created", "rows": rows,
            "seconds": round(elapsed, 2),
            "size_before_gb": round(size_before_gb, 3),
            "size_after_gb": round(size_after_gb, 3),
            "delta_gb": round(size_after_gb - size_before_gb, 3)}


def print_result(result: dict, dry_run: bool):
    print(f"==> {result['db']}")
    if "skipped" in result:
        print(f"   skipped: {result['skipped']}")
        return
    action = result["action"]
    rows = result["rows"]
    if action == "already_exists":
        print(f"   already exists | rows={rows:,}")
    elif action == "would_create":
        print(f"   would create | rows={rows:,}")
    elif action == "created":
        print(f"   created in {result['seconds']}s | rows={rows:,} | "
              f"{result['size_before_gb']} GB -> {result['size_after_gb']} GB "
              f"(+{result['delta_gb']} GB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be created; make no changes")
    parser.add_argument("--production-only", action="store_true",
                        help="only operate on data/datalake.db")
    parser.add_argument("--archives-only", action="store_true",
                        help="only operate on sector archive DBs")
    parser.add_argument("--sector", help="run on a single sector (basename without .db)")
    args = parser.parse_args()

    if args.production_only and args.archives_only:
        raise SystemExit("--production-only and --archives-only are mutually exclusive")

    targets: list[Path] = []

    if not args.archives_only:
        if not PROD_DB.exists():
            raise SystemExit(f"Production DB not found: {PROD_DB}")
        targets.append(PROD_DB)

    if not args.production_only:
        if not ARCHIVE_DIR.exists():
            raise SystemExit(f"Archive dir not found: {ARCHIVE_DIR}")
        if args.sector:
            sector_path = ARCHIVE_DIR / f"{args.sector}.db"
            if not sector_path.exists():
                raise SystemExit(f"Sector DB not found: {sector_path}")
            targets.append(sector_path)
        else:
            targets.extend(sorted(ARCHIVE_DIR.glob("*.db")))

    print(f"Targets: {len(targets)} DB(s) ({'DRY-RUN' if args.dry_run else 'LIVE'})")
    print(f"Index: {INDEX_NAME}")
    print()

    overall_start = time.perf_counter()
    created = 0
    skipped = 0
    total_delta = 0.0

    for db_path in targets:
        result = process_db(db_path, args.dry_run)
        print_result(result, args.dry_run)
        if result.get("action") == "created":
            created += 1
            total_delta += result.get("delta_gb", 0.0)
        elif "skipped" in result or result.get("action") == "already_exists":
            skipped += 1

    elapsed = time.perf_counter() - overall_start
    print()
    print(f"Done in {elapsed:.1f}s | created={created} | skipped={skipped}"
          + (f" | total disk delta +{total_delta:.3f} GB" if not args.dry_run else ""))


if __name__ == "__main__":
    main()
