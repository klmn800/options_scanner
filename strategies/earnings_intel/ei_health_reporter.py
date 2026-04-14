#!/usr/bin/env python3
"""
Earnings Intel Health Reporter (ei_health_reporter.py)
------------------------------------------------------
Comprehensive health reporting and operational analytics for Earnings Intelligence pipeline.

This module handles health report generation and performance metrics for all three
operational modes: weekly refresh, daily pipeline, and morning scan.

Features:
- Mode-specific health reports for all 3 operational modes
- Task-level performance tracking and success/failure analysis
- JSON health status for real-time monitoring
- Standardized metrics tracking (memory, errors, API calls)
- Beautiful formatting with structured layout

Author: Ben (with assistance from Claude)
Date: 2025-11-19
Version: 1.0 - Created with base class inheritance
"""

import os
import time
import logging
from datetime import datetime
from pathlib import Path
from tools.timezone_utils import eastern_isoformat, now_eastern
from tools.log_utils import beautiful_log
from tools.base_health_reporter import BaseHealthReporter


class EIHealthReporter(BaseHealthReporter):
    """Comprehensive health reporting for Earnings Intelligence operations"""

    def __init__(self, mode, trade_date=None, log_file_path=''):
        """Initialize health reporter

        Args:
            mode: Operational mode ('weekly-refresh', 'daily-pipeline', 'morning-scan')
            trade_date: Trade date string (YYYY-MM-DD) or None for auto-detect
            log_file_path: Path to detailed log file for referencing
        """
        # Auto-detect trade date if not provided
        if trade_date is None:
            trade_date = now_eastern().strftime('%Y-%m-%d')

        # Initialize base class
        super().__init__('earnings_intel', trade_date, log_file_path)

        # EI-specific tracking
        self.mode = mode
        self.task_results = {}  # Task name -> results dict
        self.mode_start_time = time.time()

    def track_task_result(self, task_name, success, **metrics):
        """Track a task result with metrics

        Args:
            task_name: Name of the task
            success: True if task succeeded, False otherwise
            **metrics: Additional metrics to track (symbols_processed, snapshots_created, etc.)
        """
        self.task_results[task_name] = {
            'success': success,
            'timestamp': eastern_isoformat(),
            'metrics': metrics
        }

        if not success:
            self.track_error()

    def generate_health_report(self, overall_success):
        """Generate comprehensive health report for current mode

        Args:
            overall_success: Overall success status of the mode run

        Returns:
            str: Path to generated health report file
        """
        try:
            # Create health report filename in centralized logs directory
            logs_dir = self.get_centralized_logs_dir()
            report_filename = 'earnings_intel_health_{}_{}.txt'.format(self.mode, self.trade_date)
            report_path = logs_dir / report_filename

            # Check if report already exists (multiple runs per day)
            report_exists = report_path.exists()
            run_number = self._determine_run_number(report_path) if report_exists else 1

            # Write mode: 'a' for append if exists, 'w' for new file
            write_mode = 'a' if report_exists else 'w'

            with open(report_path, write_mode, encoding='utf-8', errors='replace') as f:
                if report_exists:
                    # Add separator and run header for additional runs
                    f.write("\n\n" + "=" * 80 + "\n")
                    f.write("ADDITIONAL RUN #{} - {} at {}\n".format(
                        run_number,
                        self._get_mode_display_name(),
                        datetime.now().strftime('%H:%M:%S')
                    ))
                    f.write("=" * 80 + "\n\n")

                self._write_health_report_header(f)
                self._write_executive_summary(f, overall_success)
                self._write_task_performance_section(f)
                self.write_memory_analysis_section(f)
                self.write_error_analysis_section(f)
                self.write_failed_symbols_section(f)
                self.write_api_efficiency_section(f)
                self._write_file_references_section(f, report_filename)

            if report_exists:
                beautiful_log("EI health report updated (Run #{})".format(run_number), level='success')
            else:
                beautiful_log("EI health report generated", level='success')
            logging.info("   └─ Report: {}".format(report_path))

            return str(report_path)

        except Exception as e:
            logging.error("Failed to generate EI health report: {}".format(e))
            return None

    def _get_mode_display_name(self):
        """Get display name for current mode"""
        mode_names = {
            'weekly-refresh': 'Weekly Refresh',
            'daily-pipeline': 'Daily Pipeline',
            'morning-scan': 'Morning Scan'
        }
        return mode_names.get(self.mode, self.mode)

    def _write_health_report_header(self, f):
        """Write header section of health report"""
        f.write("=" * 80 + "\n")
        f.write("EARNINGS INTEL HEALTH REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write("Mode: {}\n".format(self._get_mode_display_name()))
        f.write("Trade Date: {}\n".format(self.trade_date))
        f.write("Report Generated: {} at {}\n".format(
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M:%S')))
        f.write("Report Version: 1.0 Earnings Intelligence\n\n")

    def _write_executive_summary(self, f, overall_success):
        """Write executive summary section"""
        f.write("EXECUTIVE SUMMARY\n")
        f.write("-" * 40 + "\n")

        mode_duration = time.time() - self.mode_start_time
        health_status = self.determine_health_status()

        f.write("Overall Status: {}\n".format("SUCCESS" if overall_success else "FAILED"))
        f.write("Health Status: {}\n".format(health_status))
        f.write("Execution Time: {:.1f} seconds ({:.2f} minutes)\n".format(
            mode_duration, mode_duration / 60))
        f.write("Memory Usage: {:.1f} MB (High: {:.1f} MB)\n".format(
            self.get_current_memory(), self.high_water_mark))
        f.write("Errors: {}\n".format(self.errors_session))

        # Task completion summary
        total_tasks = len(self.task_results)
        successful_tasks = sum(1 for task in self.task_results.values() if task['success'])
        f.write("Tasks Completed: {}/{}\n".format(successful_tasks, total_tasks))

        f.write("\n")

    def _write_task_performance_section(self, f):
        """Write task performance analysis"""
        f.write("TASK PERFORMANCE ANALYSIS\n")
        f.write("-" * 40 + "\n")

        if not self.task_results:
            f.write("No tasks tracked\n\n")
            return

        for task_name, result in self.task_results.items():
            f.write("{} Task:\n".format(task_name))
            f.write("  Status: {}\n".format("SUCCESS" if result['success'] else "FAILED"))
            f.write("  Timestamp: {}\n".format(result['timestamp']))

            # Write task-specific metrics
            metrics = result.get('metrics', {})
            if metrics:
                f.write("  Metrics:\n")
                for metric_name, metric_value in metrics.items():
                    # Format metric name nicely
                    display_name = metric_name.replace('_', ' ').title()
                    f.write("    {}: {}\n".format(display_name, metric_value))

            f.write("\n")

    def _write_file_references_section(self, f, report_filename):
        """Write file references and metadata section"""
        f.write("FILE REFERENCES & METADATA\n")
        f.write("-" * 40 + "\n")

        f.write("Associated Files:\n")
        f.write("  Detailed Log File: {}\n".format(
            os.path.basename(self.log_file_path) if self.log_file_path else "earnings_intel_{}_{}.log".format(self.mode, self.trade_date)))
        f.write("  Health Report File: {}\n".format(report_filename))
        f.write("  JSON Status File: earnings_intel_health.json (real-time monitoring)\n")
        f.write("  Diagnostic Log: diagnostic/earnings_intel_{}_{}.log\n".format(self.mode, self.trade_date))

        f.write("\nReport Metadata:\n")
        f.write("  Report Format Version: 1.0 Earnings Intelligence\n")
        f.write("  Generated By: EI Health Reporter v1.0\n")
        f.write("  Mode: {}\n".format(self.mode))
        f.write("  Report Generation Time: {:.2f} seconds\n".format(
            time.time() - self._report_start_time))
        f.write("  Character Encoding: UTF-8\n")

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("END OF HEALTH REPORT\n")
        f.write("=" * 80 + "\n")

    def _determine_run_number(self, report_path):
        """Determine the run number for multiple runs per day

        Args:
            report_path: Path to existing health report file

        Returns:
            int: Next run number (2, 3, 4, etc.)
        """
        try:
            if not report_path.exists():
                return 1

            with open(report_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Count existing "ADDITIONAL RUN" headers
            run_count = content.count('ADDITIONAL RUN #')

            # Return next run number (first run is 1, so additional runs start at 2)
            return run_count + 2

        except Exception as e:
            logging.warning("Error determining run number: {}. Defaulting to 2.".format(e))
            return 2


if __name__ == '__main__':
    # Simple test
    reporter = EIHealthReporter('daily-pipeline', '2025-11-19')
    reporter.track_memory()
    reporter.track_task_result('snapshot_collection', True, snapshots_created=87, symbols_processed=95)
    reporter.track_task_result('post_calc', True, moves_calculated=12, events_analyzed=18)
    reporter.track_api_call()

    print("Mode:", reporter.mode)
    print("Health Status:", reporter.determine_health_status())
    print("Task Results:", len(reporter.task_results))
    print("EI health reporter initialized successfully!")
