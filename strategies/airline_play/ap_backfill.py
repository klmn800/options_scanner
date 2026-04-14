#!/usr/bin/env python3
"""
Airline Play - Historical Backfill
Backfill historical data for airline tracking tables from 2025-08-08 through yesterday.

Purpose: Load historical data by calling ap_symbol_tracking.py and ap_options_tracking.py
for each date in the backfill range.

Usage:
    python ap_backfill.py                              # Default: 2025-08-08 to yesterday
    python ap_backfill.py --start-date 2025-09-01      # Custom start date
    python ap_backfill.py --end-date 2025-09-15        # Custom end date
    python ap_backfill.py --dry-run                    # Preview what would be backfilled

Author: Ben & Claude
Date: 2025-10-01
"""

import logging
import argparse
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.timezone_utils import now_eastern
from tools.autofix import queue_error

# Import the tracking modules
from strategies.airline_play import ap_symbol_tracking
from strategies.airline_play import ap_options_tracking

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def generate_date_range(start_date: str, end_date: str) -> List[str]:
    """
    Generate list of dates between start_date and end_date (inclusive).

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of date strings in YYYY-MM-DD format
    """
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return dates


def process_date(trade_date: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Process a single date: run symbol tracking and options tracking.

    Args:
        trade_date: Date to process (YYYY-MM-DD)
        dry_run: If True, skip actual processing and just log

    Returns:
        Dict with results from both tracking phases
    """
    logger.info(f"  Processing {trade_date}...")

    if dry_run:
        logger.info(f"    [DRY RUN] Would process symbol tracking and options tracking")
        return {
            'trade_date': trade_date,
            'dry_run': True,
            'symbol_tracking': None,
            'options_tracking': None
        }

    try:
        # Run symbol tracking
        symbol_result = ap_symbol_tracking.run_symbol_tracking(trade_date=trade_date)

        # Run options tracking
        options_result = ap_options_tracking.run_options_tracking(trade_date=trade_date)

        logger.info(f"    ✓ {trade_date}: "
                   f"{symbol_result['symbols_processed']} symbols, "
                   f"{options_result['total_contracts_tracked']} contracts")

        return {
            'trade_date': trade_date,
            'dry_run': False,
            'symbol_tracking': symbol_result,
            'options_tracking': options_result,
            'success': True,
            'error': None
        }

    except Exception as e:
        logger.error(f"Airline backfill failed for date {trade_date}: {e}")
        queue_error(
            error_type='airline_backfill_failed',
            context={
                'trade_date': trade_date,
                'error': str(e),
                'exception_type': type(e).__name__
            },
            severity='ERROR'
        )
        return {
            'trade_date': trade_date,
            'dry_run': False,
            'symbol_tracking': None,
            'options_tracking': None,
            'success': False,
            'error': str(e)
        }


def detect_gaps(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect gaps in data (dates where no symbols or contracts were tracked).

    Returns list of gap entries with details.
    """
    gaps = []

    for result in results:
        if result['dry_run']:
            continue

        if not result['success']:
            gaps.append({
                'trade_date': result['trade_date'],
                'gap_type': 'processing_error',
                'details': result['error']
            })
            continue

        symbol_tracking = result.get('symbol_tracking', {})
        options_tracking = result.get('options_tracking', {})

        symbols_processed = symbol_tracking.get('symbols_processed', 0)
        contracts_tracked = options_tracking.get('total_contracts_tracked', 0)

        if symbols_processed == 0:
            gaps.append({
                'trade_date': result['trade_date'],
                'gap_type': 'no_symbol_data',
                'details': 'No symbols tracked (missing source data)'
            })

        if contracts_tracked == 0:
            gaps.append({
                'trade_date': result['trade_date'],
                'gap_type': 'no_options_data',
                'details': 'No contracts tracked (missing option_contracts data)'
            })

    return gaps


def print_summary(results: List[Dict[str, Any]], elapsed_seconds: float):
    """
    Print comprehensive summary statistics.
    """
    logger.info("=" * 80)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 80)

    # Overall stats
    total_dates = len(results)
    successful_dates = sum(1 for r in results if not r['dry_run'] and r['success'])
    failed_dates = sum(1 for r in results if not r['dry_run'] and not r['success'])

    logger.info(f"Dates Processed: {total_dates}")
    logger.info(f"  Successful: {successful_dates}")
    logger.info(f"  Failed: {failed_dates}")

    if results and not results[0]['dry_run']:
        # Aggregate symbol and contract counts
        total_symbols = 0
        total_contracts = 0

        for result in results:
            if result['success']:
                symbol_tracking = result.get('symbol_tracking', {})
                options_tracking = result.get('options_tracking', {})

                total_symbols += symbol_tracking.get('symbols_processed', 0)
                total_contracts += options_tracking.get('total_contracts_tracked', 0)

        logger.info(f"\nData Tracked:")
        logger.info(f"  Total Symbol Records: {total_symbols}")
        logger.info(f"  Total Option Contracts: {total_contracts}")

        # Gap detection
        gaps = detect_gaps(results)
        if gaps:
            logger.info(f"\nGaps Detected: {len(gaps)}")
            for gap in gaps[:10]:  # Show first 10 gaps
                logger.info(f"  {gap['trade_date']}: {gap['gap_type']} - {gap['details']}")
            if len(gaps) > 10:
                logger.info(f"  ... and {len(gaps) - 10} more gaps")
        else:
            logger.info(f"\nGaps Detected: 0 (complete data coverage)")

    logger.info(f"\nElapsed Time: {elapsed_seconds:.1f}s")
    logger.info("=" * 80)


def run_backfill(start_date: Optional[str] = None,
                 end_date: Optional[str] = None,
                 dry_run: bool = False) -> Dict[str, Any]:
    """
    Main backfill function.

    Args:
        start_date: Start date (YYYY-MM-DD). Defaults to 2025-08-08.
        end_date: End date (YYYY-MM-DD). Defaults to yesterday.
        dry_run: If True, preview without actually processing

    Returns:
        Dict with summary statistics
    """
    # Default start date: 2025-08-08 (earliest complete option_contracts data)
    if start_date is None:
        start_date = '2025-08-08'

    # Default end date: yesterday
    if end_date is None:
        yesterday = now_eastern().date() - timedelta(days=1)
        end_date = yesterday.strftime('%Y-%m-%d')

    # Generate date range
    dates = generate_date_range(start_date, end_date)

    logger.info("=" * 80)
    logger.info("AIRLINE PLAY - HISTORICAL BACKFILL")
    logger.info("=" * 80)
    logger.info(f"Date Range: {start_date} to {end_date}")
    logger.info(f"Total Dates: {len(dates)}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("=" * 80)

    if dry_run:
        logger.info("\n[DRY RUN MODE] Preview of dates to process:")
        for i, date_str in enumerate(dates[:10], 1):
            logger.info(f"  {i}. {date_str}")
        if len(dates) > 10:
            logger.info(f"  ... and {len(dates) - 10} more dates")
        logger.info("")

    # Process each date
    start_time = datetime.now()
    results = []

    for i, trade_date in enumerate(dates, 1):
        logger.info(f"[{i}/{len(dates)}] {trade_date}")
        result = process_date(trade_date, dry_run=dry_run)
        results.append(result)

    elapsed = (datetime.now() - start_time).total_seconds()

    # Print summary
    print_summary(results, elapsed)

    return {
        'start_date': start_date,
        'end_date': end_date,
        'total_dates': len(dates),
        'successful_dates': sum(1 for r in results if not r['dry_run'] and r['success']),
        'failed_dates': sum(1 for r in results if not r['dry_run'] and not r['success']),
        'elapsed_seconds': elapsed,
        'results': results
    }


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(
        description='Airline Play - Historical Backfill',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default backfill (2025-08-08 to yesterday)
  python ap_backfill.py

  # Custom date range
  python ap_backfill.py --start-date 2025-09-01 --end-date 2025-09-15

  # Dry run preview
  python ap_backfill.py --dry-run

  # Single month backfill
  python ap_backfill.py --start-date 2025-09-01 --end-date 2025-09-30
        """
    )

    parser.add_argument('--start-date', type=str,
                       help='Start date (YYYY-MM-DD). Defaults to 2025-08-08.')
    parser.add_argument('--end-date', type=str,
                       help='End date (YYYY-MM-DD). Defaults to yesterday.')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview what would be backfilled without actually processing')

    args = parser.parse_args()

    # Validate dates if provided
    if args.start_date:
        try:
            datetime.strptime(args.start_date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid start-date format: {args.start_date}. Use YYYY-MM-DD.")
            sys.exit(1)

    if args.end_date:
        try:
            datetime.strptime(args.end_date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid end-date format: {args.end_date}. Use YYYY-MM-DD.")
            sys.exit(1)

    # Run backfill
    result = run_backfill(
        start_date=args.start_date,
        end_date=args.end_date,
        dry_run=args.dry_run
    )

    # Exit with appropriate code
    if result['failed_dates'] > 0:
        sys.exit(1)  # Indicate some failures occurred
    else:
        sys.exit(0)  # All successful


if __name__ == '__main__':
    main()
