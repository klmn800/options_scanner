#!/usr/bin/env python3
"""
Self-Healing Test Script
========================
Deliberately fails to test auto-fix system.

This script will:
1. Run in a loop
2. Fail on purpose (division by zero)
3. Log the error with [LOGANALYZER-ALERT] trigger
4. Wait for auto-fix system to detect and spawn Claude Code

After Claude fixes the bug, this script should run successfully.

Usage:
    python tools/meta/test_self_healing.py
    python tools/meta/test_self_healing.py --fixed  # After Claude fixes it

Author: Ben (with Claude)
Date: 2025-10-16
"""

import sys
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.autofix import queue_error

# Setup logging
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)
log_file = logs_dir / f"test_self_healing_{datetime.now().strftime('%Y-%m-%d')}.log"

# Configure stdout for UTF-8 encoding (emojis)
sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def buggy_calculation(x, y):
    """This function has a deliberate bug for testing

    Bug: Division by zero when y=0
    Fix: Add check for y == 0 before dividing
    """
    # FIXED: Check for y == 0 before dividing
    if y == 0:
        logger.warning(f"  Division by zero prevented! Returning 0 instead.")
        return 0
    result = x / y
    return result


def run_test_loop(fixed=False):
    """Run test loop that will fail on purpose

    Args:
        fixed: If True, use corrected values to test fix
    """
    logger.info("=" * 70)
    logger.info("SELF-HEALING TEST SCRIPT")
    logger.info("=" * 70)
    logger.info(f"Mode: {'FIXED' if fixed else 'BUGGY'}")
    logger.info("")

    iteration = 0
    while iteration < 5:
        iteration += 1
        logger.info(f"Iteration {iteration}/5")

        try:
            # Deliberately pass y=0 on iteration 3 to trigger error
            if not fixed and iteration == 3:
                x, y = 10, 0  # BUG: y=0 will cause division by zero
                logger.info(f"  Calculating {x} / {y}")
            else:
                x, y = 10, 2
                logger.info(f"  Calculating {x} / {y}")

            result = buggy_calculation(x, y)
            logger.info(f"  Result: {result}")
            logger.info("")

            time.sleep(1)

        except ZeroDivisionError as e:
            # Queue error for auto-fix system
            queue_error(
                error_type='test_division_by_zero',
                context={
                    'exception_type': 'ZeroDivisionError',
                    'error_message': str(e),
                    'iteration': iteration,
                    'x': x,
                    'y': y,
                    'function': 'buggy_calculation',
                    'file': __file__
                },
                severity='ERROR'
            )

            logger.error("")
            logger.error("⚠️  ERROR DETECTED - Waiting for auto-fix system...")
            logger.error("   Expected behavior:")
            logger.error("   1. log_analyzer.py detects this error")
            logger.error("   2. Spawns Claude Code with error context")
            logger.error("   3. Claude fixes buggy_calculation()")
            logger.error("   4. Script restarts and completes successfully")
            logger.error("")

            # Exit with error code so system knows it failed
            sys.exit(1)

    # Success!
    logger.info("=" * 70)
    logger.info("✅ TEST COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)
    logger.info("All 5 iterations passed without errors")
    logger.info("Self-healing system test: PASSED")
    logger.info("")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Self-Healing Test Script')
    parser.add_argument('--fixed', action='store_true',
                       help='Run in fixed mode (after Claude fixes the bug)')

    args = parser.parse_args()

    run_test_loop(fixed=args.fixed)


if __name__ == "__main__":
    main()
