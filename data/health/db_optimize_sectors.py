#!/usr/bin/env python3
"""
Sector Archive Database Optimizer (db_optimize_sectors.py)
----------------------------------------------------------
Runs ANALYZE on all sector archive databases to maintain query performance.

VACUUM is intentionally skipped because:
- Sector archives are append-only (rarely delete data)
- VACUUM on large archives is time-consuming with minimal benefit
- ANALYZE is sufficient to keep query planner statistics current

Usage:
  python data/health/db_optimize_sectors.py              # Optimize all sectors
  python data/health/db_optimize_sectors.py --sector airlines  # Specific sector only
  python data/health/db_optimize_sectors.py --list       # List available sectors

Author: Ben (with assistance from Claude)
"""

import os
import sys
import sqlite3
import argparse
import time
import logging
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging():
    """Set up logging to centralized logs directory with both file and console output"""
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    date_str = now_eastern().strftime('%Y-%m-%d')
    log_file = os.path.join(logs_dir, f'db_optimize_{date_str}.log')

    # Configure logging
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [DB_OPTIMIZE] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear existing handlers and add ours
    logger.handlers = []
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_sector_archive_path(sector):
    """Get path to sector archive database.

    Args:
        sector (str): Sector name (e.g., 'airlines', 'technology')

    Returns:
        str: Path to sector archive database file
    """
    return os.path.join(project_root, 'data', 'sector_archive', f'{sector}.db')


def get_all_sector_archives():
    """Get list of all sector archive databases.

    Returns:
        list: List of sector names that have archive databases
    """
    archive_dir = os.path.join(project_root, 'data', 'sector_archive')

    if not os.path.exists(archive_dir):
        return []

    sectors = []
    for filename in os.listdir(archive_dir):
        if filename.endswith('.db'):
            sector_name = filename[:-3]  # Remove .db extension
            sectors.append(sector_name)

    return sorted(sectors)


def optimize_sector_archive(sector):
    """Run ANALYZE on a sector archive database.

    Args:
        sector (str): Sector name to optimize

    Returns:
        dict: Results with timing and size info
    """
    archive_path = get_sector_archive_path(sector)

    if not os.path.exists(archive_path):
        return {
            'success': False,
            'error': 'Archive file not found'
        }

    try:
        with sqlite3.connect(archive_path) as conn:
            cursor = conn.cursor()

            # Get database size
            cursor.execute("PRAGMA page_count")
            pages = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            size_mb = (pages * page_size) / (1024 * 1024)

            # Get table count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]

            # Run ANALYZE
            start_time = time.time()
            cursor.execute("ANALYZE")
            analyze_time = time.time() - start_time

            return {
                'success': True,
                'size_mb': size_mb,
                'table_count': table_count,
                'analyze_time': analyze_time
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Optimize sector archive databases')
    parser.add_argument('--sector', type=str,
                       help='Optimize specific sector only (e.g., airlines)')
    parser.add_argument('--list', action='store_true',
                       help='List available sector archives and exit')
    args = parser.parse_args()

    # Setup logging (both file and console)
    logger = setup_logging()

    print("=" * 70)
    print("SECTOR ARCHIVE OPTIMIZER")
    print("=" * 70)
    print(f"Timestamp: {now_eastern().strftime('%Y-%m-%d %H:%M:%S EST')}")
    print("=" * 70)

    logging.info("=" * 70)
    logging.info("SECTOR ARCHIVE OPTIMIZER - STARTING")
    logging.info("=" * 70)

    # Get available sectors
    sectors = get_all_sector_archives()

    if not sectors:
        print("\n⚠️ No sector archives found in data/sector_archive/")
        print("Run sector archiving first to create archives.")
        return 1

    # List mode
    if args.list:
        print(f"\nAvailable sector archives ({len(sectors)} total):")
        for sector in sectors:
            archive_path = get_sector_archive_path(sector)
            if os.path.exists(archive_path):
                size_bytes = os.path.getsize(archive_path)
                size_mb = size_bytes / (1024 * 1024)
                print(f"  • {sector:<20} ({size_mb:,.1f} MB)")
        return 0

    # Determine which sectors to optimize
    if args.sector:
        if args.sector not in sectors:
            print(f"\n❌ ERROR: Sector '{args.sector}' not found")
            print(f"Available sectors: {', '.join(sectors)}")
            return 1
        sectors_to_optimize = [args.sector]
    else:
        sectors_to_optimize = sectors

    print(f"\nOptimizing {len(sectors_to_optimize)} sector archive(s)...")
    print()

    # Optimize each sector
    total_time = 0
    success_count = 0

    for sector in sectors_to_optimize:
        print(f"Processing {sector}...")
        result = optimize_sector_archive(sector)

        if result['success']:
            print(f"  ✓ ANALYZE completed in {result['analyze_time']:.1f}s")
            print(f"    Database: {result['size_mb']:.1f} MB, {result['table_count']} tables")
            total_time += result['analyze_time']
            success_count += 1
        else:
            print(f"  ❌ ERROR: {result['error']}")
        print()

    # Summary
    print("=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print(f"Sectors optimized: {success_count} / {len(sectors_to_optimize)}")
    print(f"Total time: {total_time:.1f} seconds")
    print("=" * 70)

    logging.info("=" * 70)
    logging.info("OPTIMIZATION COMPLETE")
    logging.info(f"Sectors optimized: {success_count}/{len(sectors_to_optimize)}, Total time: {total_time:.1f}s")
    logging.info("=" * 70)

    return 0 if success_count == len(sectors_to_optimize) else 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
