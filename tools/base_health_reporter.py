#!/usr/bin/env python3
"""
Base Health Reporter (base_health_reporter.py)
----------------------------------------------
Shared health tracking and reporting for all pipeline strategies.

This module provides standardized health monitoring functionality that both
Flow Monitor and Option Pipeline inherit from, ensuring consistent tracking
and reporting across all processes.

Features:
- Memory usage tracking and trend analysis
- Error tracking with daily/session counters
- Failed symbols tracking with error details
- API efficiency and rate limiting metrics
- JSON health status for real-time monitoring
- Standard report sections for consistent formatting

Author: Ben (with assistance from Claude)
Date: 2025-11-19
Version: 1.0 - Extracted shared functionality
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from collections import deque
from tools.timezone_utils import eastern_isoformat, now_eastern


class BaseHealthReporter:
    """Base health reporting class with shared tracking for all pipelines"""

    def __init__(self, process_name, trade_date=None, log_file_path=''):
        """Initialize base health reporter

        Args:
            process_name: Process identifier ('flow_monitor' or 'option_pipeline')
            trade_date: Trade date string (YYYY-MM-DD) or None for FM
            log_file_path: Path to detailed log file for referencing
        """
        self.process_name = process_name
        self.trade_date = trade_date
        self.log_file_path = log_file_path
        self._report_start_time = time.time()

        # Memory tracking
        self.memory_readings = deque(maxlen=100)
        self.high_water_mark = 0

        # Error tracking
        self.errors_today = 0
        self.errors_session = 0
        self._last_date = None

        # Failed symbols tracking
        self.failed_symbols = {}  # symbol -> {'error': str, 'attempts': int, 'timestamp': str}

        # API efficiency tracking
        self.api_stats = {
            'total_calls': 0,
            'start_time': time.time(),
            'last_call_time': None
        }

        # Session tracking
        self.session_start_time = time.time()

    def track_memory(self):
        """Update memory usage tracking"""
        try:
            import psutil
            current_memory = psutil.Process().memory_info().rss / 1024 / 1024

            self.memory_readings.append({
                'timestamp': time.time(),
                'memory_mb': current_memory
            })

            # Track high water mark
            if current_memory > self.high_water_mark:
                self.high_water_mark = current_memory

        except ImportError:
            pass  # psutil not available
        except Exception as e:
            logging.warning("Memory tracking error: {}".format(e))

    def get_current_memory(self):
        """Get current memory usage in MB"""
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1024 / 1024
        except:
            return 0

    def track_error(self):
        """Track an error occurrence with daily reset"""
        self.errors_session += 1

        # Reset daily counter at midnight
        now = now_eastern()
        if self._last_date is None:
            self._last_date = now.strftime('%Y-%m-%d')

        current_date = now.strftime('%Y-%m-%d')
        if current_date != self._last_date:
            self.errors_today = 0
            self._last_date = current_date

        self.errors_today += 1

    def track_failed_symbol(self, symbol, error_reason, attempts=1):
        """Track a failed symbol with error details

        Args:
            symbol: Symbol that failed
            error_reason: Reason for failure
            attempts: Number of attempts made
        """
        self.failed_symbols[symbol] = {
            'error': error_reason,
            'attempts': attempts,
            'timestamp': eastern_isoformat()
        }

    def track_api_call(self):
        """Track an API call for efficiency metrics"""
        self.api_stats['total_calls'] += 1
        self.api_stats['last_call_time'] = time.time()

    def get_api_efficiency_metrics(self):
        """Calculate API efficiency metrics

        Returns:
            dict: API rate metrics including calls/minute and efficiency %
        """
        elapsed = time.time() - self.api_stats['start_time']
        total_calls = self.api_stats['total_calls']

        if elapsed > 0 and total_calls > 0:
            calls_per_minute = total_calls / (elapsed / 60)
            # Tradier limit is 120/minute
            efficiency_pct = (calls_per_minute / 120) * 100

            # Determine performance rating
            if calls_per_minute > 100:
                rating = 'EXCELLENT'
            elif calls_per_minute > 80:
                rating = 'GOOD'
            elif calls_per_minute > 60:
                rating = 'ACCEPTABLE'
            else:
                rating = 'POOR'

            return {
                'total_calls': total_calls,
                'elapsed_minutes': elapsed / 60,
                'calls_per_minute': calls_per_minute,
                'efficiency_pct': efficiency_pct,
                'rating': rating
            }

        return {
            'total_calls': 0,
            'elapsed_minutes': 0,
            'calls_per_minute': 0,
            'efficiency_pct': 0,
            'rating': 'N/A'
        }

    def calculate_memory_growth(self):
        """Calculate memory growth trend from first to last reading"""
        if len(self.memory_readings) < 2:
            return 0

        try:
            first_reading = self.memory_readings[0]['memory_mb']
            last_reading = self.memory_readings[-1]['memory_mb']
            return round(last_reading - first_reading, 1)
        except:
            return 0

    def determine_health_status(self):
        """Determine overall health status based on errors

        Returns:
            str: OPTIMAL, GOOD, DEGRADED, or POOR
        """
        if self.errors_today == 0 and self.errors_session == 0:
            return 'OPTIMAL'
        elif self.errors_today < 5:
            return 'GOOD'
        elif self.errors_today < 15:
            return 'DEGRADED'
        else:
            return 'POOR'

    def write_json_health_status(self, extra_data=None):
        """Write JSON health status file for real-time monitoring

        Args:
            extra_data: Optional dict of process-specific data to include
        """
        try:
            current_memory = self.get_current_memory()
            api_metrics = self.get_api_efficiency_metrics()

            # Build standard health data
            health_data = {
                'version': '2.0',
                'process': self.process_name,
                'timestamp': eastern_isoformat(),
                'trade_date': self.trade_date,
                'health_status': self.determine_health_status(),
                'errors_today': self.errors_today,
                'errors_session': self.errors_session,
                'session_duration_hours': (time.time() - self.session_start_time) / 3600,
                'memory': {
                    'current_mb': current_memory,
                    'high_water_mark_mb': self.high_water_mark,
                    'growth_mb': self.calculate_memory_growth(),
                    'readings_count': len(self.memory_readings)
                },
                'failed_symbols': {
                    'count': len(self.failed_symbols),
                    'symbols': list(self.failed_symbols.keys())[:10]  # First 10
                },
                'api_efficiency': api_metrics
            }

            # Add process-specific data
            if extra_data:
                health_data.update(extra_data)

            # Write atomically to centralized logs directory
            logs_dir = Path(__file__).parent.parent / 'logs'
            logs_dir.mkdir(exist_ok=True)
            health_file = logs_dir / '{}_health.json'.format(self.process_name)
            temp_file = logs_dir / '{}_health.json.tmp'.format(self.process_name)

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(health_data, f, indent=2)

            # Atomic rename
            temp_file.replace(health_file)

        except Exception as e:
            logging.error("Failed to write JSON health status: {}".format(e))

    def write_memory_analysis_section(self, f):
        """Write standardized memory analysis section

        Args:
            f: File handle to write to
        """
        f.write("MEMORY ANALYSIS\n")
        f.write("-" * 40 + "\n")

        current_memory = self.get_current_memory()
        memory_growth = self.calculate_memory_growth()

        f.write("Current Memory Usage: {:.1f} MB\n".format(current_memory))
        f.write("High Water Mark: {:.1f} MB\n".format(self.high_water_mark))
        f.write("Memory Growth: {:.1f} MB\n".format(memory_growth))
        f.write("Memory Readings Collected: {}\n".format(len(self.memory_readings)))

        # Memory trend analysis
        if memory_growth > 100:
            f.write("Memory Trend: CONCERNING - High growth detected\n")
        elif memory_growth > 50:
            f.write("Memory Trend: MODERATE - Some growth detected\n")
        elif memory_growth > 0:
            f.write("Memory Trend: STABLE - Minor growth\n")
        else:
            f.write("Memory Trend: EXCELLENT - No growth or reduction\n")

        f.write("\n")

    def write_error_analysis_section(self, f):
        """Write standardized error analysis section

        Args:
            f: File handle to write to
        """
        f.write("ERROR ANALYSIS\n")
        f.write("-" * 40 + "\n")

        f.write("Errors Today: {}\n".format(self.errors_today))
        f.write("Session Errors: {}\n".format(self.errors_session))

        health_status = self.determine_health_status()
        if health_status == 'OPTIMAL':
            f.write("Error Status: PERFECT - No errors detected\n")
        elif health_status == 'GOOD':
            f.write("Error Status: GOOD - Minimal errors\n")
        elif health_status == 'DEGRADED':
            f.write("Error Status: ACCEPTABLE - Some errors detected\n")
        else:
            f.write("Error Status: CONCERNING - High error count\n")

        f.write("\n")

    def write_failed_symbols_section(self, f):
        """Write standardized failed symbols section

        Args:
            f: File handle to write to
        """
        f.write("FAILED SYMBOLS ANALYSIS\n")
        f.write("-" * 40 + "\n")

        if self.failed_symbols:
            f.write("Failed Symbols ({} total):\n".format(len(self.failed_symbols)))
            f.write("Symbol    | Attempts | Error\n")
            f.write("----------|----------|------------------\n")

            # Show first 20 failed symbols
            for symbol, details in list(self.failed_symbols.items())[:20]:
                f.write("{:<9} | {:<8} | {}\n".format(
                    symbol[:9],
                    details.get('attempts', 1),
                    details.get('error', 'unknown')[:20]
                ))

            if len(self.failed_symbols) > 20:
                f.write("... and {} more\n".format(len(self.failed_symbols) - 20))

            f.write("\n")
        else:
            f.write("No failed symbols - All collections successful!\n\n")

    def write_api_efficiency_section(self, f):
        """Write standardized API efficiency section

        Args:
            f: File handle to write to
        """
        f.write("API EFFICIENCY & RATE LIMITING\n")
        f.write("-" * 40 + "\n")

        metrics = self.get_api_efficiency_metrics()

        if metrics['total_calls'] > 0:
            f.write("API Performance Metrics:\n")
            f.write("  Total API Calls Made: {:,}\n".format(metrics['total_calls']))
            f.write("  Total Execution Time: {:.1f} minutes\n".format(metrics['elapsed_minutes']))
            f.write("  API Rate Achieved: {:.1f} calls/minute\n".format(metrics['calls_per_minute']))
            f.write("  Rate Limit Efficiency: {:.1f}%\n".format(metrics['efficiency_pct']))
            f.write("  Performance Rating: {}\n".format(metrics['rating']))
        else:
            f.write("API Performance Metrics: No API calls tracked\n")

        f.write("\n")

    def get_centralized_logs_dir(self):
        """Get centralized logs directory path

        Returns:
            Path: Centralized logs directory
        """
        logs_dir = Path(__file__).parent.parent / 'logs'
        logs_dir.mkdir(exist_ok=True)
        return logs_dir


if __name__ == '__main__':
    # Simple test
    reporter = BaseHealthReporter('test_process', '2025-11-19')
    reporter.track_memory()
    reporter.track_error()
    reporter.track_failed_symbol('TEST', 'test_error')
    reporter.track_api_call()

    print("Health Status:", reporter.determine_health_status())
    print("API Metrics:", reporter.get_api_efficiency_metrics())
    print("Base health reporter initialized successfully!")
