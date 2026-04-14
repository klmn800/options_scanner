#!/usr/bin/env python3
"""
FM Health Reporter (fm_health_reporter.py)
------------------------------------------
Comprehensive health reporting and operational analytics for Flow Monitor pipeline.

This module handles all health report generation, performance metrics, and 
operational analytics that were previously embedded in fm_main.py global state.

Features:
- Comprehensive daily health reports for all three pipelines
- Real-time JSON health status for monitoring
- Detailed performance metrics and memory usage analysis
- Beautiful formatting with structured layout
- File-based reporting similar to OID pattern

Author: Ben (with assistance from Claude)
Date: 2025-08-25
Version: 1.0 - Extracted from fm_main.py global state
"""

import os
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from collections import deque
from tools.timezone_utils import eastern_isoformat, now_eastern
from tools.base_health_reporter import BaseHealthReporter

class FMHealthReporter(BaseHealthReporter):
    """Comprehensive health reporting for Flow Monitor operations"""

    def __init__(self, log_file_path=''):
        """Initialize health reporter

        Args:
            log_file_path: Path to detailed log file for referencing
        """
        # Initialize base class
        super().__init__('flow_monitor', None, log_file_path)

        # FM-specific performance tracking
        self.task_durations = {}
        self.task_averages = {}
        
        self.performance_metrics = {
            'current_cycle': {
                'collection_times': [],
                'storage_times': [],
                'analysis_times': [],
                'alert_times': [],
                'cycle_times': []
            },
            'session_stats': {
                'total_cycles': 0,
                'successful_cycles': 0,
                'failed_cycles': 0,
                'average_cycle_time': 0,
                'slowest_cycle': 0,
                'fastest_cycle': float('inf')
            }
        }
    
    def update_health_status(self, task_name=None, status='running', error=False, 
                           task_duration=None, performance_data=None):
        """Update health monitoring with current status and performance metrics
        
        Args:
            task_name: Name of current/completed task
            status: 'running', 'success', 'failed', 'timeout', 'skipped'
            error: True if this represents an error condition
            task_duration: Duration in seconds if task completed
            performance_data: Dict with performance metrics for the cycle
        """
        try:
            # Update error counters using base class
            if error:
                self.track_error()
            
            # Update task duration tracking
            if task_name and task_duration:
                if task_name not in self.task_durations:
                    self.task_durations[task_name] = []
                
                self.task_durations[task_name].append(task_duration)
                
                # Keep only last 10 runs for rolling average
                if len(self.task_durations[task_name]) > 10:
                    self.task_durations[task_name] = self.task_durations[task_name][-10:]
                
                # Calculate rolling average
                self.task_averages[task_name] = sum(self.task_durations[task_name]) / len(self.task_durations[task_name])
            
            # Update performance metrics
            self._update_performance_metrics(performance_data, status)

            # Update memory tracking using base class
            self.track_memory()

            # Generate JSON health status file
            self._write_json_health_status(task_name, status)
            
        except Exception as e:
            logging.error("Failed to update health status: {}".format(e))
    
    def generate_daily_health_report(self, trade_date, pipeline_results):
        """Generate comprehensive daily health report combining all pipeline results
        
        Args:
            trade_date: Trade date string (YYYY-MM-DD)
            pipeline_results: Dict containing results from all three pipelines
            
        Returns:
            str: Path to generated health report file
        """
        try:
            # Create health report filename in centralized logs directory
            logs_dir = self.get_centralized_logs_dir()
            report_filename = 'flow_monitor_health_{}.txt'.format(trade_date)
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
                        "Flow Monitor Pipeline",
                        datetime.now().strftime('%H:%M:%S')
                    ))
                    f.write("=" * 80 + "\n\n")
                
                self._write_health_report_header(f, trade_date)
                self._write_executive_summary(f, pipeline_results)
                self._write_pipeline_performance_section(f, pipeline_results)
                self._write_performance_metrics_section(f)
                self.write_memory_analysis_section(f)
                self._write_error_analysis_section(f)
                self._write_timing_coordination_section(f, pipeline_results)
                self._write_file_references_section(f, report_filename)
            
            if report_exists:
                logging.info("📋 FM health report updated: {} (Run #{})".format(report_filename, run_number))
            else:
                logging.info("📋 FM health report generated: {}".format(report_filename))
            
            return str(report_path)
            
        except Exception as e:
            logging.error("Failed to generate FM health report: {}".format(e))
            return None
    
    def generate_session_summary(self):
        """Generate session summary for immediate reporting"""
        try:
            session_duration = (time.time() - self.session_start_time) / 3600

            summary = {
                'session_start': datetime.fromtimestamp(self.session_start_time).strftime('%Y-%m-%d %H:%M:%S'),
                'session_duration_hours': round(session_duration, 2),
                'current_memory_mb': self.get_current_memory(),
                'high_water_mark_mb': self.high_water_mark,
                'errors_session': self.errors_session,
                'errors_today': self.errors_today,
                'performance_summary': self._get_performance_summary(),
                'health_status': self.determine_health_status()
            }
            
            return summary
            
        except Exception as e:
            logging.error("Error generating session summary: {}".format(e))
            return {'error': str(e)}
    
    def _update_performance_metrics(self, performance_data, status):
        """Update performance metrics from cycle data"""
        if not performance_data:
            return
        
        metrics = self.performance_metrics['current_cycle']
        
        if 'collection_time' in performance_data:
            metrics['collection_times'].append(performance_data['collection_time'])
            if len(metrics['collection_times']) > 100:
                metrics['collection_times'] = metrics['collection_times'][-100:]

        if 'storage_time' in performance_data and performance_data['storage_time'] > 0:
            metrics['storage_times'].append(performance_data['storage_time'])
            if len(metrics['storage_times']) > 100:
                metrics['storage_times'] = metrics['storage_times'][-100:]

        if 'analysis_time' in performance_data:
            metrics['analysis_times'].append(performance_data['analysis_time'])
            if len(metrics['analysis_times']) > 100:
                metrics['analysis_times'] = metrics['analysis_times'][-100:]
        
        if 'alert_time' in performance_data:
            metrics['alert_times'].append(performance_data['alert_time'])
            if len(metrics['alert_times']) > 100:
                metrics['alert_times'] = metrics['alert_times'][-100:]
        
        if 'cycle_time' in performance_data:
            cycle_time = performance_data['cycle_time']
            metrics['cycle_times'].append(cycle_time)
            if len(metrics['cycle_times']) > 100:
                metrics['cycle_times'] = metrics['cycle_times'][-100:]
            
            # Update session stats
            stats = self.performance_metrics['session_stats']
            stats['total_cycles'] += 1
            if status == 'success':
                stats['successful_cycles'] += 1
            else:
                stats['failed_cycles'] += 1
            
            if len(metrics['cycle_times']) > 0:
                stats['average_cycle_time'] = sum(metrics['cycle_times']) / len(metrics['cycle_times'])
                stats['slowest_cycle'] = max(stats['slowest_cycle'], cycle_time)
                stats['fastest_cycle'] = min(stats['fastest_cycle'], cycle_time)
    
    def _write_json_health_status(self, task_name, status):
        """Write JSON health status file for real-time monitoring"""
        try:
            metrics = self.performance_metrics['current_cycle']

            # Build FM-specific data to add to base health status
            fm_specific_data = {
                'phase': self._get_current_phase(),
                'last_task': task_name or 'monitor_cycle',
                'last_status': status,
                'monitor_active': True,
                'startup_time': datetime.fromtimestamp(self.session_start_time).strftime('%Y-%m-%d %H:%M:%S'),
                'task_averages': self.task_averages.copy(),
                'performance_metrics': {
                    'last_10_cycles': {
                        'avg_collection_time': sum(metrics['collection_times'][-10:]) / len(metrics['collection_times'][-10:]) if metrics['collection_times'] else 0,
                        'avg_storage_time': sum(metrics['storage_times'][-10:]) / len(metrics['storage_times'][-10:]) if metrics['storage_times'] else 0,
                        'avg_analysis_time': sum(metrics['analysis_times'][-10:]) / len(metrics['analysis_times'][-10:]) if metrics['analysis_times'] else 0,
                        'avg_alert_time': sum(metrics['alert_times'][-10:]) / len(metrics['alert_times'][-10:]) if metrics['alert_times'] else 0,
                        'avg_cycle_time': sum(metrics['cycle_times'][-10:]) / len(metrics['cycle_times'][-10:]) if metrics['cycle_times'] else 0
                    },
                    'session_totals': self.performance_metrics['session_stats']
                }
            }

            # Use base class method to write JSON with FM-specific data
            self.write_json_health_status(extra_data=fm_specific_data)

        except Exception as e:
            logging.error("Failed to write JSON health status: {}".format(e))
    
    def _get_current_phase(self):
        """Get current operational phase"""
        now = now_eastern()
        hour = now.hour
        minute = now.minute
        
        if 8 <= hour < 9 or (hour == 9 and minute < 25):
            return "PRE-MARKET"
        elif 9 <= hour < 16:
            return "MARKET HOURS"
        elif hour >= 16:
            return "POST-MARKET"
        else:
            return "AFTER HOURS"
    
    def _get_performance_summary(self):
        """Get performance summary for reporting"""
        try:
            metrics = self.performance_metrics['current_cycle']
            stats = self.performance_metrics['session_stats']
            
            return {
                'total_cycles': stats['total_cycles'],
                'success_rate': (stats['successful_cycles'] / stats['total_cycles'] * 100) if stats['total_cycles'] > 0 else 0,
                'average_cycle_time': stats['average_cycle_time'],
                'recent_cycles': len(metrics['cycle_times']),
                'memory_growth': self.calculate_memory_growth()
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _write_health_report_header(self, f, trade_date):
        """Write header section of health report"""
        f.write("=" * 80 + "\n")
        f.write("FLOW MONITOR DAILY HEALTH REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write("Trade Date: {}\n".format(trade_date))
        f.write("Report Generated: {} at {}\n".format(
            datetime.now().strftime('%Y-%m-%d'), 
            datetime.now().strftime('%H:%M:%S')))
        f.write("Pipeline Type: Three-Phase (Pre-Market + Market Hours + Post-Market)\n")
        f.write("Report Version: 2.0 Enhanced Flow Monitor\n\n")
    
    def _write_executive_summary(self, f, pipeline_results):
        """Write executive summary section"""
        f.write("EXECUTIVE SUMMARY\n")
        f.write("-" * 40 + "\n")

        health_status = self.determine_health_status()
        session_summary = self.generate_session_summary()
        
        f.write("Overall Health Status: {}\n".format(health_status))
        f.write("Session Duration: {:.2f} hours\n".format(session_summary.get('session_duration_hours', 0)))
        f.write("Memory Usage: {:.1f} MB (High: {:.1f} MB)\n".format(
            session_summary.get('current_memory_mb', 0),
            session_summary.get('high_water_mark_mb', 0)))
        f.write("Errors Today: {}\n".format(self.errors_today))
        f.write("Session Errors: {}\n".format(self.errors_session))
        
        # Pipeline completion status
        pre_market_completed = pipeline_results.get('pre_market', {}).get('completed', False)
        market_hours_completed = pipeline_results.get('market_hours', {}).get('completed', False)
        post_market_completed = pipeline_results.get('post_market', {}).get('completed', False)
        
        f.write("Pre-Market Pipeline: {}\n".format("COMPLETED" if pre_market_completed else "PENDING/FAILED"))
        f.write("Market Hours Pipeline: {}\n".format("COMPLETED" if market_hours_completed else "PENDING/FAILED"))
        f.write("Post-Market Pipeline: {}\n".format("COMPLETED" if post_market_completed else "PENDING/FAILED"))
        f.write("\n")
    
    def _write_pipeline_performance_section(self, f, pipeline_results):
        """Write pipeline performance analysis"""
        f.write("PIPELINE PERFORMANCE ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        for pipeline_name in ['pre_market', 'market_hours', 'post_market']:
            pipeline_data = pipeline_results.get(pipeline_name, {})
            
            f.write("{} Pipeline:\n".format(pipeline_name.replace('_', '-').title()))
            f.write("  Status: {}\n".format("COMPLETED" if pipeline_data.get('completed') else "INCOMPLETE"))
            f.write("  Duration: {:.1f} seconds\n".format(pipeline_data.get('duration_seconds', 0)))
            f.write("  Tasks Completed: {}/{}\n".format(
                pipeline_data.get('tasks_completed', 0),
                pipeline_data.get('total_tasks', 0)))
            
            if 'error' in pipeline_data:
                f.write("  Error: {}\n".format(pipeline_data['error']))
            
            f.write("\n")
    
    def _write_performance_metrics_section(self, f):
        """Write detailed performance metrics"""
        f.write("PERFORMANCE METRICS\n")
        f.write("-" * 40 + "\n")
        
        metrics = self.performance_metrics['current_cycle']
        stats = self.performance_metrics['session_stats']
        
        f.write("Market Hours Cycle Performance:\n")
        f.write("  Total Cycles: {}\n".format(stats['total_cycles']))
        f.write("  Successful Cycles: {}\n".format(stats['successful_cycles']))
        f.write("  Success Rate: {:.1f}%\n".format(
            (stats['successful_cycles'] / stats['total_cycles'] * 100) if stats['total_cycles'] > 0 else 0))
        f.write("  Average Cycle Time: {:.2f} seconds\n".format(stats['average_cycle_time']))
        f.write("  Slowest Cycle: {:.2f} seconds\n".format(stats['slowest_cycle']))
        f.write("  Fastest Cycle: {:.2f} seconds\n".format(
            stats['fastest_cycle'] if stats['fastest_cycle'] != float('inf') else 0))
        
        if len(metrics['collection_times']) > 0:
            f.write("\nDetailed Timing Breakdown:\n")
            f.write("  Avg Collection Time: {:.2f} seconds\n".format(
                sum(metrics['collection_times']) / len(metrics['collection_times'])))
            f.write("  Avg Analysis Time: {:.2f} seconds\n".format(
                sum(metrics['analysis_times']) / len(metrics['analysis_times']) if metrics['analysis_times'] else 0))
            f.write("  Avg Alert Time: {:.2f} seconds\n".format(
                sum(metrics['alert_times']) / len(metrics['alert_times']) if metrics['alert_times'] else 0))
        
        f.write("\n")
    
    def _write_error_analysis_section(self, f):
        """Write error analysis section with FM-specific task tracking"""
        # Use base class for standard error analysis
        self.write_error_analysis_section(f)

        # Add FM-specific task performance tracking
        if self.task_durations:
            f.write("Task Performance Summary:\n")
            for task_name, durations in self.task_durations.items():
                avg_duration = self.task_averages.get(task_name, 0)
                f.write("  {}: {:.1f}s avg ({} runs)\n".format(task_name, avg_duration, len(durations)))
            f.write("\n")
    
    def _write_timing_coordination_section(self, f, pipeline_results):
        """Write timing and coordination analysis"""
        f.write("TIMING & COORDINATION ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        f.write("Session Timeline:\n")
        f.write("  Session Start: {}\n".format(
            datetime.fromtimestamp(self.session_start_time).strftime('%Y-%m-%d %H:%M:%S')))
        f.write("  Current Time: {}\n".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        f.write("  Total Runtime: {:.2f} hours\n".format((time.time() - self.session_start_time) / 3600))
        
        # Pipeline timing coordination
        f.write("\nPipeline Coordination:\n")
        for pipeline_name in ['pre_market', 'market_hours', 'post_market']:
            pipeline_data = pipeline_results.get(pipeline_name, {})
            start_time = pipeline_data.get('start_time')
            end_time = pipeline_data.get('end_time')
            
            f.write("  {} Pipeline:\n".format(pipeline_name.replace('_', '-').title()))
            f.write("    Start: {}\n".format(start_time if start_time else 'not_started'))
            f.write("    End: {}\n".format(end_time if end_time else 'not_completed'))
        
        f.write("\n")
    
    def _write_file_references_section(self, f, report_filename):
        """Write file references and metadata section"""
        f.write("FILE REFERENCES & METADATA\n")
        f.write("-" * 40 + "\n")
        
        f.write("Associated Files:\n")
        f.write("  Detailed Log File: {}\n".format(os.path.basename(self.log_file_path) if self.log_file_path else "flow_monitor_YYYY-MM-DD.log"))
        f.write("  Health Report File: {}\n".format(report_filename))
        f.write("  JSON Status File: flow_monitor_health.json (real-time monitoring)\n")
        
        f.write("\nReport Metadata:\n")
        f.write("  Report Format Version: 2.0 Flow Monitor Enhanced\n")
        f.write("  Generated By: FM Health Reporter v1.0\n")
        f.write("  Report Generation Time: {:.2f} seconds\n".format(
            time.time() - self._report_start_time))
        f.write("  Character Encoding: UTF-8\n")
        
        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("END OF COMPREHENSIVE HEALTH REPORT\n")
        f.write("=" * 80 + "\n")
    
    def _determine_run_number(self, report_path):
        """Determine the run number for multiple runs per day"""
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
    exit(main())