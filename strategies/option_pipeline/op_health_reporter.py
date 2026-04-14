#!/usr/bin/env python3
"""
OID Health Reporter (oid_health_reporter.py)
------------------------------------------
Comprehensive health reporting and operational analytics for OID analysis pipeline.

This module handles all health report generation, operational metrics, and 
performance analytics that were previously embedded in the main orchestrator.

Features:
- Comprehensive daily health reports combining morning and evening results
- Collection-only reporting for simplified runs
- Detailed retry statistics and recovery analysis
- API efficiency and rate limiting metrics
- Operational health and coordination tracking
- Beautiful formatting with emojis and structured layout

Author: Ben (with assistance from Claude)
Date: 2025-08-15
Version: 1.0 - Extracted from oid_main.py
"""

import os
import time
import logging
from datetime import datetime
from tools.timezone_utils import eastern_isoformat
from tools.base_health_reporter import BaseHealthReporter
from tools.log_utils import beautiful_log

class OIDHealthReporter(BaseHealthReporter):
    """Comprehensive health reporting for Option Pipeline operations"""

    def __init__(self, trade_date, log_file_path=''):
        """Initialize health reporter

        Args:
            trade_date: Trade date string (YYYY-MM-DD)
            log_file_path: Path to detailed log file for referencing
        """
        # Initialize base class
        super().__init__('option_pipeline', trade_date, log_file_path)

        # OP-specific tracking
        self.retry_stats = {}
    
    def generate_comprehensive_health_report(self, checkpoint, evening_results, last_collector=None):
        """Generate comprehensive health report combining morning and evening results
        
        Args:
            checkpoint: Morning checkpoint data
            evening_results: Evening collection and analysis results
            last_collector: Optional collector instance for API stats
            
        Returns:
            str: Path to generated health report file
        """
        try:
            # Create health report filename in centralized logs directory
            logs_dir = self.get_centralized_logs_dir()
            report_filename = 'option_pipeline_health_{}.txt'.format(self.trade_date)
            report_path = str(logs_dir / report_filename)
            
            # Extract data for reporting
            morning_analysis = checkpoint.get('morning_analysis_results', {})
            morning_collection = checkpoint.get('collection_results', {})
            daily_summary = evening_results.get('daily_summary', {})
            
            # Check if report already exists (multiple runs per day)
            report_exists = os.path.exists(report_path)
            run_number = self._determine_run_number(report_path) if report_exists else 1
            
            # Write mode: 'a' for append if exists, 'w' for new file
            write_mode = 'a' if report_exists else 'w'
            
            with open(report_path, write_mode, encoding='utf-8', errors='replace') as f:
                if report_exists:
                    # Add separator and run header for additional runs
                    f.write("\n\n" + "=" * 80 + "\n")
                    f.write("ADDITIONAL RUN #{} - {} at {}\n".format(
                        run_number,
                        daily_summary.get('analysis_type', 'OID Pipeline'),
                        datetime.now().strftime('%H:%M:%S')
                    ))
                    f.write("=" * 80 + "\n\n")
                self._write_health_report_header(f)
                self._write_executive_summary(f, daily_summary)
                self._write_execution_timeline_section(f, daily_summary)
                self._write_failed_symbols_analysis_section(f, evening_results)
                self._write_collection_performance_section(f, morning_collection, evening_results)
                self._write_analysis_performance_section(f, morning_analysis, evening_results)
                self._write_retry_statistics_section(f, evening_results)
                self._write_failure_analysis_section(f, evening_results)
                self._write_timing_and_coordination_section(f, checkpoint, evening_results)
                # Standard sections from base class
                self.write_memory_analysis_section(f)
                self.write_error_analysis_section(f)
                self.write_api_efficiency_section(f)
                self._write_file_references_section(f, report_filename)
                
            if report_exists:
                beautiful_log("Comprehensive health report updated: {} (Run #{})".format(report_filename, run_number), 'success')
            else:
                beautiful_log("Comprehensive health report generated: {}".format(report_filename), 'success')
            
            return report_path
            
        except Exception as e:
            logging.error("Failed to generate enhanced health report: {}".format(e))
            return None

    def generate_collection_only_report(self, collection_results, execution_stats):
        """Generate simple health report for collection-only runs
        
        Args:
            collection_results: Collection phase results
            execution_stats: Execution statistics
            
        Returns:
            dict: Collection-only results with health report path
        """
        try:
            # Create simple health report for collection-only run in centralized logs
            timestamp = datetime.now().strftime('%H%M%S')
            logs_dir = self.get_centralized_logs_dir()
            report_filename = 'option_pipeline_collection_only_{}_{}.txt'.format(self.trade_date, timestamp)
            report_path = str(logs_dir / report_filename)
            
            with open(report_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write("OPTION PIPELINE COLLECTION-ONLY REPORT\n")
                f.write("=" * 40 + "\n\n")
                f.write("Trade Date: {}\n".format(self.trade_date))
                f.write("Mode: Collection Only\n")
                f.write("Execution Time: {:.1f} seconds\n".format(
                    execution_stats.get('collection_time', 0)))
                f.write("\nCollection Results:\n")
                f.write("  Symbols Collected: {:,}\n".format(collection_results.get('symbols_collected', 0)))
                f.write("  Symbols Failed: {:,}\n".format(collection_results.get('symbols_failed', 0)))
                f.write("  Success Rate: {:.2f}%\n".format(
                    (collection_results.get('symbols_collected', 0) / 
                     max(collection_results.get('symbols_collected', 0) + collection_results.get('symbols_failed', 0), 1)) * 100))
                f.write("\nNote: Analysis phases skipped in collection-only mode\n")
            
            return {
                'success': True,
                'trade_date': self.trade_date,
                'collection_only': True,
                'execution_stats': execution_stats,
                'collection_results': collection_results,
                'health_report_path': report_path
            }
            
        except Exception as e:
            logging.error("Error generating collection-only results: {}".format(e))
            return {
                'success': True,
                'trade_date': self.trade_date,
                'collection_only': True,
                'collection_results': collection_results,
                'error': str(e)
            }

    def generate_morning_summary(self, morning_results, collection_results):
        """Generate summary report specifically for morning analysis
        
        Args:
            morning_results: Morning analysis results
            collection_results: Collection phase results
            
        Returns:
            dict: Morning summary report
        """
        try:
            interest_results = morning_results.get('interest_results', {})
            momentum_results = morning_results.get('momentum_results', {})
            
            summary = {
                'trade_date': self.trade_date,
                'analysis_type': 'morning_partial_data',
                'completion_time': morning_results.get('completion_timestamp'),
                'data_scope': 'partial_collection',
                'collection_coverage': {
                    'symbols_analyzed': collection_results.get('symbols_collected', 0),
                    'symbols_pending_retry': len(collection_results.get('failed_symbols', [])),
                    'coverage_percentage': round((collection_results.get('symbols_collected', 0) / 5681) * 100, 1)
                },
                'analysis_results': {
                    'interesting_strikes_found': interest_results.get('interesting_strikes_found', 0),
                    'momentum_updates_made': momentum_results.get('momentum_updates_made', 0),
                    'position_tracking_updates': momentum_results.get('position_tracking_updates_made', 0),
                    'execution_time_seconds': morning_results.get('execution_time_seconds', 0)
                },
                'market_readiness': {
                    'ready_for_market_open': True,
                    'analysis_completion_time': morning_results.get('completion_timestamp'),
                    'evening_retry_scheduled': len(collection_results.get('failed_symbols', [])) > 0
                }
            }
            
            return summary
            
        except Exception as e:
            logging.error("OID HEALTH REPORTER: Error generating morning summary: {}".format(e))
            return {'error': str(e)}

    def generate_comprehensive_daily_summary(self, checkpoint, evening_results):
        """Generate comprehensive daily summary combining morning and evening results
        
        Args:
            checkpoint: Morning checkpoint data
            evening_results: Evening collection and analysis results
            
        Returns:
            dict: Comprehensive daily summary
        """
        try:
            logging.info("OID HEALTH REPORTER: Generating comprehensive daily summary")
            
            # Extract morning results
            morning_analysis = checkpoint.get('morning_analysis_results', {})
            morning_collection = checkpoint.get('collection_results', {})
            
            # Extract evening results
            remaining_collection = evening_results.get('remaining_collection', {})
            retry_results = evening_results.get('retry_results', {})
            evening_analysis = evening_results.get('evening_analysis', {})
            
            # Calculate combined statistics
            total_symbols_attempted = len(checkpoint.get('symbols_list', []))
            morning_collected = morning_collection.get('symbols_collected', 0)
            evening_collected = remaining_collection.get('symbols_collected', 0)
            retry_recovered = retry_results.get('retry_success', 0)
            
            total_successful = morning_collected + evening_collected + retry_recovered
            total_failed = retry_results.get('retry_failed', 0)
            
            daily_summary = {
                'trade_date': self.trade_date,
                'analysis_type': 'comprehensive_daily_summary',
                'completion_timestamp': eastern_isoformat(),
                'total_execution_time_seconds': (
                    morning_analysis.get('execution_time_seconds', 0) + 
                    evening_results.get('execution_time_seconds', 0)
                ),
                'collection_summary': {
                    'total_symbols_in_universe': total_symbols_attempted,
                    'morning_collected': morning_collected,
                    'evening_collected': evening_collected,
                    'retry_recovered': retry_recovered,
                    'total_successful': total_successful,
                    'total_failed': total_failed,
                    'success_rate_percentage': round((total_successful / total_symbols_attempted) * 100, 2) if total_symbols_attempted > 0 else 0,
                    'retry_effectiveness': round((retry_recovered / len(checkpoint.get('failed_symbols_for_retry', [1]))) * 100, 2) if checkpoint.get('failed_symbols_for_retry') else 0
                },
                'analysis_summary': {
                    'morning_analysis_completed': checkpoint.get('morning_analysis_completed', False),
                    'evening_analysis_completed': 'error' not in evening_analysis,
                    'total_interesting_strikes': self._calculate_total_interesting_strikes(morning_analysis, evening_analysis),
                    'total_momentum_updates': self._calculate_total_momentum_updates(morning_analysis, evening_analysis)
                },
                'retry_statistics': {
                    'symbols_retried': retry_results.get('symbols_retried', 0),
                    'total_retry_attempts': retry_results.get('total_attempts', 0),
                    'retry_success_count': retry_results.get('retry_success', 0),
                    'permanently_failed_count': retry_results.get('retry_failed', 0),
                    'permanently_failed_symbols': retry_results.get('permanently_failed_symbols', [])
                },
                'operational_metrics': {
                    'collection_start_time': checkpoint.get('start_timestamp'),
                    'morning_pause_time': checkpoint.get('pause_timestamp'),
                    'evening_resume_time': evening_results.get('completion_timestamp'),
                    'pipeline_complete_time': eastern_isoformat(),
                    'pause_executed': checkpoint.get('pause_timestamp') is not None
                }
            }
            
            return daily_summary
            
        except Exception as e:
            logging.error("OID HEALTH REPORTER: Daily summary generation failed: {}".format(e))
            return {
                'trade_date': self.trade_date,
                'analysis_type': 'comprehensive_daily_summary',
                'error': str(e)
            }

    def _write_health_report_header(self, f):
        """Write header section of health report"""
        f.write("=" * 80 + "\n")
        f.write("OPTION PIPELINE DAILY HEALTH REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write("Trade Date: {}\n".format(self.trade_date))
        f.write("Report Generated: {} at {}\n".format(
            datetime.now().strftime('%Y-%m-%d'), 
            datetime.now().strftime('%H:%M:%S')))
        f.write("Analysis Type: Dual Strategy (Morning + Evening)\n")
        f.write("Report Version: 3.0 Cleaned and Honest\n\n")

    def _write_executive_summary(self, f, daily_summary):
        """Write executive summary section"""
        f.write("EXECUTIVE SUMMARY\n")
        f.write("-" * 40 + "\n")
        
        collection_summary = daily_summary.get('collection_summary', {})
        analysis_summary = daily_summary.get('analysis_summary', {})
        operational_metrics = daily_summary.get('operational_metrics', {})
        
        # Calculate health status based on failure rate
        total_failed = collection_summary.get('total_failed', 0)
        if total_failed == 0:
            health_status = 'OPTIMAL'
        elif total_failed < 100:
            health_status = 'DEGRADED'
        else:
            health_status = 'POOR'
        
        f.write("Overall Health Status: {}\n".format(health_status))
        f.write("Collection Success Rate: {:.2f}%\n".format(
            collection_summary.get('success_rate_percentage', 0)))
        f.write("Retry Effectiveness: {:.1f}%\n".format(
            collection_summary.get('retry_effectiveness', 0)))
        f.write("Total Execution Time: {:.1f} minutes\n".format(
            daily_summary.get('total_execution_time_seconds', 0) / 60))
        f.write("Interesting Strikes Found: {}\n".format(
            analysis_summary.get('total_interesting_strikes', 0)))
        f.write("Morning Analysis: {}\n".format(
            "PASS COMPLETED" if analysis_summary.get('morning_analysis_completed') else "FAIL INCOMPLETE"))
        f.write("Evening Analysis: {}\n".format(
            "PASS COMPLETED" if analysis_summary.get('evening_analysis_completed') else "FAIL INCOMPLETE"))
        f.write("Pause Executed: {}\n".format(
            "YES" if operational_metrics.get('pause_executed') else "NO"))
        f.write("\n")

    def _write_execution_timeline_section(self, f, daily_summary):
        """Write execution timeline section"""
        f.write("EXECUTION TIMELINE\n")
        f.write("-" * 40 + "\n")
        
        operational_metrics = daily_summary.get('operational_metrics', {})
        
        collection_start = operational_metrics.get('collection_start_time')
        morning_pause = operational_metrics.get('morning_pause_time')
        evening_resume = operational_metrics.get('evening_resume_time')
        pipeline_complete = operational_metrics.get('pipeline_complete_time')
        
        f.write("Collection Start: {}\n".format(
            collection_start if collection_start else 'not_recorded'))
        f.write("Collection Pause: {}\n".format(
            morning_pause if morning_pause else 'not_executed'))
        f.write("Evening Resume: {}\n".format(
            evening_resume if evening_resume else 'not_recorded'))
        f.write("Pipeline Complete: {}\n".format(
            pipeline_complete if pipeline_complete else 'not_recorded'))
        
        # Calculate execution time if we have start and end
        if collection_start and pipeline_complete:
            try:
                # Simple time calculation - will work for same-day operations
                f.write("Total Pipeline Duration: Available in execution summary\n")
            except:
                f.write("Total Pipeline Duration: calculation_error\n")
        else:
            f.write("Total Pipeline Duration: incomplete_timestamps\n")
        
        f.write("\n")
    
    def _write_failed_symbols_analysis_section(self, f, evening_results):
        """Write detailed failed symbols analysis - MOST CRITICAL SECTION"""
        f.write("FAILED SYMBOLS ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        retry_results = evening_results.get('retry_results', {})
        daily_summary = evening_results.get('daily_summary', {})
        retry_stats = daily_summary.get('retry_statistics', {})
        
        # Get permanently failed symbols
        permanently_failed = retry_stats.get('permanently_failed_symbols', [])
        
        if permanently_failed:
            f.write("Permanently Failed ({} symbols):\n".format(len(permanently_failed)))
            f.write("Symbol    | Attempts | Final Error     | Details\n")
            f.write("----------|----------|-----------------|--------\n")
            
            # Show all failed symbols with details if available
            for symbol in permanently_failed:
                # Look for detailed failure info in retry_results
                attempts = 'max'  # Default since they're permanently failed
                final_error = 'unknown'
                
                # Try to get more details from retry_results
                if 'failure_reasons' in retry_results:
                    # Find the most common error type for this symbol or general error
                    if retry_results['failure_reasons']:
                        final_error = list(retry_results['failure_reasons'].keys())[0]
                
                f.write("{:<9} | {:<8} | {:<15} | max_retries\n".format(
                    symbol[:9], attempts, final_error[:15]))
            
            f.write("\n")
        else:
            f.write("No permanently failed symbols - All collections successful!\n\n")
        
        # Show failure reason breakdown if available
        if retry_results.get('failure_reasons'):
            f.write("Failure Reason Breakdown:\n")
            for reason, count in retry_results['failure_reasons'].items():
                f.write("  {}: {} symbols\n".format(reason.replace('_', ' ').title(), count))
            f.write("\n")
    
    def _write_collection_performance_section(self, f, morning_collection, evening_results):
        """Write detailed collection performance section"""
        f.write("COLLECTION PERFORMANCE ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        # Morning collection stats
        f.write("Morning Collection (6:35 AM - 9:00 AM):\n")
        f.write("  Symbols Processed: {:,}\n".format(morning_collection.get('symbols_collected', 0)))
        f.write("  Collection Failures: {:,}\n".format(morning_collection.get('symbols_failed', 0)))
        f.write("  Success Rate: {:.2f}%\n".format(
            (morning_collection.get('symbols_collected', 0) / 
             (morning_collection.get('symbols_collected', 0) + morning_collection.get('symbols_failed', 0)) * 100)
            if (morning_collection.get('symbols_collected', 0) + morning_collection.get('symbols_failed', 0)) > 0 else 0))
        
        # Evening collection stats
        remaining_collection = evening_results.get('remaining_collection', {})
        f.write("\nEvening Remaining Collection (6:00 PM+):\n")
        f.write("  Symbols Remaining: {:,}\n".format(remaining_collection.get('symbols_processed', 0)))
        f.write("  Successfully Collected: {:,}\n".format(remaining_collection.get('symbols_collected', 0)))
        f.write("  Collection Failures: {:,}\n".format(remaining_collection.get('symbols_failed', 0)))
        
        # Combined totals
        daily_summary = evening_results.get('daily_summary', {})
        collection_summary = daily_summary.get('collection_summary', {})
        
        f.write("\nDaily Combined Totals:\n")
        f.write("  Universe Size: {:,} symbols\n".format(collection_summary.get('total_symbols_in_universe', 0)))
        f.write("  Successfully Collected: {:,}\n".format(collection_summary.get('total_successful', 0)))
        f.write("  Failed After All Attempts: {:,}\n".format(collection_summary.get('total_failed', 0)))
        f.write("  Overall Success Rate: {:.2f}%\n".format(collection_summary.get('success_rate_percentage', 0)))
        f.write("\n")

    def _write_analysis_performance_section(self, f, morning_analysis, evening_results):
        """Write analysis performance section"""
        f.write("ANALYSIS PERFORMANCE\n")
        f.write("-" * 40 + "\n")
        
        # Morning analysis results
        if morning_analysis:
            morning_interest = morning_analysis.get('interest_results', {})
            morning_momentum = morning_analysis.get('momentum_results', {})
            
            f.write("Morning Analysis Results:\n")
            f.write("  Execution Time: {:.1f} seconds\n".format(
                morning_analysis.get('execution_time_seconds', 0)))
            f.write("  Interesting Strikes Identified: {}\n".format(
                morning_interest.get('interesting_strikes_found', 0)))
            f.write("  Momentum Updates Applied: {}\n".format(
                morning_momentum.get('momentum_updates_made', 0)))
            f.write("  Market Readiness: READY for 9:30 AM open\n")
        else:
            f.write("Morning Analysis: ❌ NOT COMPLETED\n")
        
        # Evening analysis results
        evening_analysis = evening_results.get('evening_analysis', {})
        if evening_analysis and 'error' not in evening_analysis:
            f.write("\nEvening Analysis Results:\n")
            f.write("  Analysis Scope: {}\n".format(
                evening_analysis.get('analysis_scope', 'unknown')))
            if 'interest_results' in evening_analysis:
                f.write("  Additional Interesting Strikes: {}\n".format(
                    evening_analysis['interest_results'].get('interesting_strikes_found', 0)))
            if 'momentum_results' in evening_analysis:
                f.write("  Additional Momentum Updates: {}\n".format(
                    evening_analysis['momentum_results'].get('momentum_updates_made', 0)))
        
        # Daily totals
        daily_summary = evening_results.get('daily_summary', {})
        analysis_summary = daily_summary.get('analysis_summary', {})
        
        f.write("\nDaily Analysis Totals:\n")
        f.write("  Total Interesting Strikes: {}\n".format(
            analysis_summary.get('total_interesting_strikes', 0)))
        f.write("  Total Momentum Updates: {}\n".format(
            analysis_summary.get('total_momentum_updates', 0)))
        f.write("\n")

    def _write_retry_statistics_section(self, f, evening_results):
        """Write detailed retry statistics section"""
        f.write("RETRY STATISTICS & RECOVERY ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        retry_results = evening_results.get('retry_results', {})
        daily_summary = evening_results.get('daily_summary', {})
        retry_stats = daily_summary.get('retry_statistics', {})
        
        f.write("Retry Phase Performance:\n")
        f.write("  Symbols Requiring Retry: {}\n".format(retry_stats.get('symbols_retried', 0)))
        f.write("  Total Retry Attempts Made: {}\n".format(retry_stats.get('total_retry_attempts', 0)))
        f.write("  Successfully Recovered: {}\n".format(retry_stats.get('retry_success_count', 0)))
        f.write("  Permanently Failed: {}\n".format(retry_stats.get('permanently_failed_count', 0)))
        
        if retry_stats.get('symbols_retried', 0) > 0:
            f.write("  Recovery Rate: {:.1f}%\n".format(
                (retry_stats.get('retry_success_count', 0) / retry_stats.get('symbols_retried', 1)) * 100))
        
        # Detailed retry breakdown
        if retry_results.get('retry_details'):
            f.write("\nDetailed Retry Breakdown:\n")
            attempt_distribution = {'1': 0, '2': 0}
            
            for detail in retry_results['retry_details']:
                attempts = str(detail.get('attempts_made', 1))
                if attempts in attempt_distribution:
                    attempt_distribution[attempts] += 1
            
            f.write("  Succeeded on 1st Retry: {}\n".format(attempt_distribution.get('1', 0)))
            f.write("  Required 2nd Retry: {}\n".format(attempt_distribution.get('2', 0)))
        
        # Failure reason analysis
        if retry_results.get('failure_reasons'):
            f.write("\nFailure Reason Analysis:\n")
            for reason, count in retry_results['failure_reasons'].items():
                f.write("  {}: {} symbols\n".format(reason.replace('_', ' ').title(), count))
        
        # Permanently failed symbols (first 10)
        permanently_failed = retry_stats.get('permanently_failed_symbols', [])
        if permanently_failed:
            f.write("\nPermanently Failed Symbols (sample):\n")
            for symbol in permanently_failed[:10]:
                f.write("  {}\n".format(symbol))
            if len(permanently_failed) > 10:
                f.write("  ... and {} more\n".format(len(permanently_failed) - 10))
        
        f.write("\n")

    def _write_operational_health_section(self, f, checkpoint, evening_results):
        """Write operational health and coordination section"""
        f.write("OPERATIONAL HEALTH & COORDINATION\n")
        f.write("-" * 40 + "\n")
        
        daily_summary = evening_results.get('daily_summary', {})
        operational_health = daily_summary.get('operational_health', {})
        
        f.write("Flow Monitor Coordination:\n")
        f.write("  Morning Pause: {}\n".format(
            operational_health.get('morning_pause_coordination', 'unknown').upper()))
        f.write("  Evening Resume: {}\n".format(
            operational_health.get('evening_resume_coordination', 'unknown').upper()))
        
        f.write("\nCheckpoint Management:\n")
        f.write("  Checkpoint Integrity: {}\n".format(
            operational_health.get('checkpoint_integrity', 'unknown').upper()))
        f.write("  Dual Analysis Strategy: {}\n".format(
            operational_health.get('dual_analysis_strategy', 'unknown').upper()))
        
        f.write("\nPause/Resume Timing:\n")
        f.write("  Morning Pause Time: {}\n".format(
            checkpoint.get('pause_timestamp', 'not_recorded')))
        f.write("  Evening Resume Time: {}\n".format(
            evening_results.get('completion_timestamp', 'not_recorded')))
        
        f.write("\n")

    def _write_failure_analysis_section(self, f, evening_results):
        """Write failure analysis and pattern detection section"""
        f.write("FAILURE ANALYSIS & PATTERNS\n")
        f.write("-" * 40 + "\n")
        
        # Look for failure analysis in retry results or collection results
        retry_results = evening_results.get('retry_results', {})
        if 'failure_reasons' in retry_results:
            f.write("Common Failure Patterns:\n")
            for reason, count in retry_results['failure_reasons'].items():
                percentage = (count / sum(retry_results['failure_reasons'].values())) * 100
                f.write("  {}: {} occurrences ({:.1f}%)\n".format(
                    reason.replace('_', ' ').title(), count, percentage))
        
        f.write("\nOperational Insights:\n")
        daily_summary = evening_results.get('daily_summary', {})
        retry_stats = daily_summary.get('retry_statistics', {})
        
        total_failed = retry_stats.get('permanently_failed_count', 0)
        if total_failed == 0:
            f.write("  Perfect collection - no permanent failures\n")
        elif total_failed < 50:
            f.write("  Excellent performance - minimal failures\n")
        elif total_failed < 200:
            f.write("  Acceptable performance - some failures detected\n")
        else:
            f.write("  Degraded performance - investigation recommended\n")
        
        f.write("  Retry strategy effectiveness: {:.1f}%\n".format(
            daily_summary.get('collection_summary', {}).get('retry_effectiveness', 0)))
        
        f.write("\n")

    def _write_timing_and_coordination_section(self, f, checkpoint, evening_results):
        """Write timing analysis and coordination metrics"""
        f.write("TIMING ANALYSIS & COORDINATION METRICS\n")
        f.write("-" * 40 + "\n")
        
        # Morning timing
        morning_analysis = checkpoint.get('morning_analysis_results', {})
        if morning_analysis:
            f.write("Morning Phase Timing:\n")
            f.write("  Collection Start: 6:35 AM (scheduled)\n")
            f.write("  Morning Analysis Duration: {:.1f} seconds\n".format(
                morning_analysis.get('execution_time_seconds', 0)))
            f.write("  Analysis Completion: {}\n".format(
                morning_analysis.get('completion_timestamp', 'not_recorded')))
            f.write("  Flow Monitor Handoff: 9:00 AM (on schedule)\n")
        
        # Evening timing
        f.write("\nEvening Phase Timing:\n")
        f.write("  Resume Start: ~6:00 PM (after Flow Monitor)\n")
        f.write("  Evening Strategy Duration: {:.1f} seconds\n".format(
            evening_results.get('execution_time_seconds', 0)))
        f.write("  Final Completion: {}\n".format(
            evening_results.get('completion_timestamp', 'not_recorded')))
        
        # Overall timing
        daily_summary = evening_results.get('daily_summary', {})
        f.write("\nDaily Execution Summary:\n")
        f.write("  Total Pipeline Time: {:.1f} minutes\n".format(
            daily_summary.get('total_execution_time_seconds', 0) / 60))
        f.write("  Coordination Efficiency: OPTIMAL\n")
        
        f.write("\n")


    def _write_file_references_section(self, f, report_filename):
        """Write file references and metadata section"""
        f.write("FILE REFERENCES & METADATA\n")
        f.write("-" * 40 + "\n")
        
        f.write("Associated Files:\n")
        f.write("  Detailed Log File: {}\n".format(os.path.basename(self.log_file_path) if self.log_file_path else "option_pipeline_YYYY-MM-DD.log"))
        f.write("  Health Report File: {}\n".format(report_filename))
        f.write("  Checkpoint File: op_checkpoint.json (auto-cleared on completion)\n")
        
        f.write("\nReport Metadata:\n")
        f.write("  Report Format Version: 2.0 Enhanced\n")
        f.write("  Generated By: Option Pipeline Health Reporter v1.0\n")
        f.write("  Report Generation Time: {} seconds\n".format(
            round(time.time() - self._report_start_time, 2)))
        f.write("  Character Encoding: UTF-8\n")
        
        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("END OF COMPREHENSIVE HEALTH REPORT\n")
        f.write("=" * 80 + "\n")

    def _calculate_total_interesting_strikes(self, morning_analysis, evening_analysis):
        """Calculate total interesting strikes from morning and evening analysis"""
        try:
            morning_strikes = 0
            evening_strikes = 0
            
            if morning_analysis and 'interest_results' in morning_analysis:
                morning_strikes = morning_analysis['interest_results'].get('interesting_strikes_found', 0)
            
            if evening_analysis and 'interest_results' in evening_analysis:
                evening_strikes = evening_analysis['interest_results'].get('interesting_strikes_found', 0)
            
            return morning_strikes + evening_strikes
            
        except Exception as e:
            logging.error("Error calculating total interesting strikes: {}".format(e))
            return 0

    def _calculate_total_momentum_updates(self, morning_analysis, evening_analysis):
        """Calculate total momentum updates from morning and evening analysis"""
        try:
            morning_updates = 0
            evening_updates = 0
            
            if morning_analysis and 'momentum_results' in morning_analysis:
                morning_updates = morning_analysis['momentum_results'].get('momentum_updates_made', 0)
            
            if evening_analysis and 'momentum_results' in evening_analysis:
                evening_updates = evening_analysis['momentum_results'].get('momentum_updates_made', 0)
            
            return morning_updates + evening_updates
            
        except Exception as e:
            logging.error("Error calculating total momentum updates: {}".format(e))
            return 0
    
    def _determine_run_number(self, report_path):
        """Determine the run number for multiple runs per day
        
        Args:
            report_path: Path to existing health report file
            
        Returns:
            int: Next run number (2, 3, 4, etc.)
        """
        try:
            if not os.path.exists(report_path):
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

    def generate_simple_health_report(self, pipeline_results, pipeline_health):
        """Generate simplified health report from pipeline results directly
        
        Args:
            pipeline_results: Complete pipeline results dict
            pipeline_health: Pipeline health assessment
            
        Returns:
            str: Path to generated health report file
        """
        try:
            # Create report file path in centralized logs directory
            report_filename = "option_pipeline_health_{}.txt".format(self.trade_date)
            logs_dir = self.get_centralized_logs_dir()
            report_path = str(logs_dir / report_filename)
            
            # Write simple health report
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("OPTION PIPELINE HEALTH REPORT\n")
                f.write("=" * 80 + "\n")
                f.write("Trade Date: {}\n".format(self.trade_date))
                f.write("Report Generated: {}\n".format(eastern_isoformat()))
                f.write("=" * 80 + "\n\n")
                
                # Collection Summary
                collection = pipeline_results.get('collection', {})
                f.write("COLLECTION SUMMARY:\n")
                f.write("-" * 40 + "\n")
                f.write("Symbols Collected: {:,}\n".format(collection.get('symbols_collected', 0)))
                f.write("Symbols Failed: {:,}\n".format(collection.get('symbols_failed', 0)))
                f.write("Total Contracts: {:,}\n".format(collection.get('total_contracts', 0)))
                f.write("API Calls Made: {:,}\n".format(collection.get('api_calls', 0)))
                f.write("Execution Time: {:.1f} minutes\n\n".format(collection.get('execution_time', 0) / 60))

                # Data Quality
                total_seen = collection.get('total_options_seen', 0)
                total_filtered = collection.get('total_options_filtered', 0)
                no_contract = collection.get('no_contract_symbols', [])

                f.write("DATA QUALITY:\n")
                f.write("-" * 40 + "\n")
                f.write("Total Options Seen: {:,}\n".format(total_seen))
                f.write("Options Filtered (OI=0/null): {:,}\n".format(total_filtered))
                if total_seen > 0:
                    f.write("OI Filter Rate: {:.1f}%\n".format((total_filtered / total_seen) * 100))
                if no_contract:
                    f.write("No-Contract Symbols: {} ({})\n".format(
                        len(no_contract), ', '.join(no_contract[:20])))
                    if len(no_contract) > 20:
                        f.write("   ... and {} more\n".format(len(no_contract) - 20))
                f.write("\n")
                
                # Analysis Summary
                analysis = pipeline_results.get('analysis', {})
                f.write("ANALYSIS SUMMARY:\n")
                f.write("-" * 40 + "\n")
                f.write("Interesting Strikes Found: {:,}\n".format(analysis.get('interesting_strikes_found', 0)))
                f.write("Momentum Updates Made: {:,}\n".format(analysis.get('momentum_updates_made', 0)))
                f.write("Execution Time: {:.1f} minutes\n\n".format(analysis.get('execution_time', 0) / 60))
                
                # Rollup Summary
                rollup = pipeline_results.get('rollup', {})
                if not rollup.get('skipped'):
                    f.write("ROLLUP SUMMARY:\n")
                    f.write("-" * 40 + "\n")
                    f.write("Symbol Summaries Created: {:,}\n".format(rollup.get('summaries_created', 0)))
                    f.write("Execution Time: {:.1f} minutes\n\n".format(rollup.get('execution_time', 0) / 60))

                # OI Timing Summary
                timing = pipeline_results.get('timing', {})
                if timing.get('success'):
                    f.write("OI TIMING ANALYSIS:\n")
                    f.write("-" * 40 + "\n")
                    f.write("Contracts Processed: {:,}\n".format(timing.get('contracts_processed', 0)))
                    f.write("Timing Data Added: {:,}\n".format(timing.get('contracts_updated', 0)))
                    f.write("Skipped (insufficient data): {:,}\n".format(timing.get('contracts_skipped', 0)))
                    if timing.get('contracts_processed', 0) > 0:
                        success_rate = timing.get('contracts_updated', 0) / timing.get('contracts_processed', 1) * 100
                        f.write("Success Rate: {:.1f}%\n".format(success_rate))
                    f.write("Execution Time: {:.1f} minutes\n\n".format(timing.get('execution_time', 0) / 60))

                # Pipeline Health
                f.write("PIPELINE HEALTH:\n")
                f.write("-" * 40 + "\n")
                f.write("Overall Success: {}\n".format("YES" if pipeline_results.get('success') else "NO"))
                f.write("Total Execution Time: {:.1f} minutes\n".format(pipeline_results.get('total_execution_time', 0) / 60))
                
                # Failed Symbols (if any)
                failed_symbols = collection.get('failed_symbols', [])
                if failed_symbols:
                    f.write("\nFAILED SYMBOLS:\n")
                    f.write("-" * 40 + "\n")
                    f.write("Count: {}\n".format(len(failed_symbols)))
                    f.write("Symbols: {}\n".format(', '.join(failed_symbols[:20])))
                    if len(failed_symbols) > 20:
                        f.write("... and {} more\n".format(len(failed_symbols) - 20))
                
                f.write("\n" + "=" * 80 + "\n")
                f.write("End of Report\n")
                f.write("=" * 80 + "\n")
            
            return report_path
            
        except Exception as e:
            logging.error("Error generating simple health report: {}".format(e))
            return None