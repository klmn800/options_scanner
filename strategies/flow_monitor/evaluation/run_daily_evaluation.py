#!/usr/bin/env python3
"""
Daily Alert Evaluation Runner (run_daily_evaluation.py)
-----------------------------------------------------
Automated scheduler script for nightly alert evaluation.
Designed for Windows Task Scheduler integration.

Features:
- Runs AlertEvaluator with comprehensive error handling
- Prevents multiple instances from running simultaneously
- Proper logging with timestamps and file output
- Exit codes for scheduler monitoring

Author: Ben (with assistance from Claude)
Date: 2025-07-07
"""

import os
import sys
import logging
import time
from pathlib import Path
from datetime import datetime

# Force UTF-8 encoding for Windows compatibility
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# Clean imports - no path hacking needed!
try:
    from strategies.flow_monitor.evaluation.fm_evaluator import AlertEvaluator
    from tools.timezone_utils import eastern_isoformat
except ImportError as e:
    print("❌ Import Error: {}".format(e))
    print("❌ Make sure you're running from the project root directory")
    print("❌ Ensure all required modules are available")
    sys.exit(1)

def setup_logging():
    """Set up logging to both file and console"""
    # Create logs directory if it doesn't exist
    script_dir = Path(__file__).parent
    logs_dir = script_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"daily_evaluation_{timestamp}.log"

    # Configure logging - match system format (no milliseconds)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return str(log_file)

def check_already_running():
    """Check if another evaluation is already running"""
    try:
        import psutil
    except ImportError:
        print("⚠️  psutil not available - skipping duplicate instance check")
        return None
    
    current_pid = os.getpid()
    script_name = "run_daily_evaluation.py"
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] != current_pid:
                    cmdline = proc.info['cmdline']
                    if cmdline and any(script_name in arg for arg in cmdline):
                        return proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        print("⚠️  Could not check for running instances: {}".format(e))
    
    return None

def validate_system():
    """Validate system dependencies and configuration"""
    validation_passed = True

    # Check for required modules (only report failures — successes are noise)
    try:
        import sqlite3
    except ImportError:
        print("❌ SQLite3 not available")
        validation_passed = False

    try:
        import psutil
    except ImportError:
        print("⚠️  psutil not available (duplicate instance checking disabled)")

    try:
        from tools.timezone_utils import now_eastern
    except ImportError:
        print("❌ Timezone utilities not available")
        validation_passed = False

    try:
        from strategies.flow_monitor.evaluation.fm_evaluator import AlertEvaluator
    except ImportError as e:
        print("❌ AlertEvaluator import failed: {}".format(e))
        validation_passed = False

    return validation_passed

def wait_for_enter():
    """Wait for user input (for manual runs)"""
    try:
        input("\nPress Enter to continue...")
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(130)

def main():
    """Main execution function"""
    print("\n" + "="*70)
    print("FLOW MONITOR DAILY EVALUATION RUNNER")
    print("="*70)
    print("Automated nightly alert performance evaluation")
    print("Current time: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S EST")))
    print("="*70)
    
    # Set up logging first
    log_file = setup_logging()
    logging.info("Daily evaluation run starting")
    logging.info("Log file: {}".format(log_file))
    
    try:
        # Validate system first
        if not validate_system():
            print("\n❌ System validation failed - cannot proceed")
            print("❌ Please check the error messages above and fix any issues")
            return 2  # System validation failure
        
        # Check for already running instance
        print("\nChecking for running instances...")
        existing_pid = check_already_running()
        if existing_pid:
            error_msg = "Another evaluation is already running (PID: {})".format(existing_pid)
            logging.error(error_msg)
            print("❌ {}".format(error_msg))
            return 3  # Exit code 3: Already running
        else:
            print("✓ No conflicting instances found")
        
        # Import and initialize evaluator
        print("\nInitializing AlertEvaluator...")
        logging.info("Initializing AlertEvaluator...")             
     
        evaluator = AlertEvaluator()
        print("✓ AlertEvaluator initialized successfully")
        logging.info("AlertEvaluator initialized successfully")
        
        # Run the evaluation
        logging.debug("Starting alert evaluation run...")
        logging.info("Starting alert evaluation run...")
        start_time = time.time()
        
        success = evaluator.run_evaluation()
        
        elapsed_time = time.time() - start_time
        logging.debug("Evaluation completed in {:.1f} seconds".format(elapsed_time))
        
        # Check results and exit with appropriate code
        if success:
            logging.debug("Evaluation completed successfully in {:.1f}s".format(elapsed_time))
            logging.debug("Log file: {}".format(log_file))
            return 0  # Success
        else:
            logging.error("Daily evaluation failed")
            logging.debug("Check log file for details: {}".format(log_file))
            return 1  # Evaluation failure
            
    except ImportError as e:
        error_msg = "Failed to import AlertEvaluator: {}".format(e)
        logging.error(error_msg)
        print("❌ {}".format(error_msg))
        print("❌ Ensure evaluation system is properly installed.")
        print("="*70)
        return 2  # Import/setup failure
        
    except KeyboardInterrupt:
        logging.warning("Evaluation cancelled by user")
        print("\n⚠️  Evaluation cancelled by user")
        print("="*70)
        return 130  # Ctrl+C
        
    except Exception as e:
        error_msg = "Unexpected error during evaluation: {}".format(e)
        logging.error(error_msg)
        logging.exception("Full traceback:")
        print("❌ {}".format(error_msg))
        print("❌ Check log file for full details: {}".format(log_file))
        print("="*70)
        return 1  # General failure

if __name__ == "__main__":
    exit_code = main()
    
    # If running interactively (not from scheduler), wait for user
    if len(sys.argv) == 1:  # No command line arguments = likely manual run
        wait_for_enter()
    
    sys.exit(exit_code)