#!/usr/bin/env python3
"""
Option Pipeline Main Orchestrator (op_main.py)
---------------------------------------------------------
Streamlined orchestrator for the Open Interest Delta analysis pipeline.
Runs sequential collection without checkpoint/pause complexity.

Pipeline Flow:
1. Collection
2. Analysis (Gap from Maximum, Momentum, Age tracking)
3. Symbol Rollup (Aggregation to symbol level)
4. Health Report (Performance metrics)

Author: Ben (with assistance from Claude)
Date: 2025-08-20
Version: 2.0 - Simplified for sequential execution
"""

import os
import sys
import time
import json
import logging
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from tools.autofix import handle_error
from tools.log_utils import beautiful_log

# Import OID modules
from strategies.option_pipeline.op_config import OIDConfig
from strategies.option_pipeline.op_storage import OIDStorage  
# from strategies.option_pipeline.oid_analyzer import OIDAnalyzer  # DEPRECATED - analysis moved to storage layer
from strategies.option_pipeline.op_collector import OIDCollector 
from strategies.option_pipeline.op_symbol_rollup import OIDSymbolRollup
from core.symbols_klmn800 import get_specialty_list
from strategies.option_pipeline.op_health_reporter import OIDHealthReporter

# Import timezone utilities
def get_project_root():
    """Get the root directory of the project"""
    current_file = os.path.abspath(__file__)    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

project_root = get_project_root()
tools_dir = os.path.join(project_root, 'tools')

if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern, eastern_date_string, eastern_isoformat


class OPOrchestrator:
    """Orchestrator for sequential Option Pipeline analysis"""
    
    def __init__(self, no_interaction=False):
        """Initialize orchestrator with storage and analysis components
        
        Args:
            no_interaction: If True, skip all user prompts
        """
        self.config = OIDConfig()
        self.storage = OIDStorage(self.config)
        # self.analyzer = OIDAnalyzer(self.storage)  # DEPRECATED - analysis moved to storage layer
        self.no_interaction = no_interaction
        
        # Component results storage
        self.pipeline_results = {
            'start_time': time.time(),
            'collection': {},
            'analysis': {},
            'rollup': {},
            'health': {},
            'errors': []
        }
    
    def wait_for_enter(self):
        """Wait for user to press Enter unless in no-interaction mode"""
        if not self.no_interaction:
            input("\nPress Enter to continue...")
    
    def run_pipeline(self, trade_date, symbol=None, skip_rollup=False):
        """
        Run complete Option Pipeline sequentially

        Args:
            trade_date: Trade date string (YYYY-MM-DD)
            symbol: Optional single symbol for testing
            skip_rollup: Skip symbol rollup phase (for debugging)

        Returns:
            dict: Complete pipeline results
        """
        pipeline_start = time.time()

        # Initialize diagnostic logging
        diag_logger = setup_diagnostic_logging()
        current_time = now_eastern()

        # Determine phase (morning vs evening based on time)
        phase = 'evening' if current_time.hour >= 16 else 'morning'

        diag_logger.info("[{}] {} Pipeline Started".format(
            current_time.strftime('%Y-%m-%d %H:%M:%S'),
            phase.title()
        ))

        try:
            # Calculate total phases dynamically
            # 4 phases: Collection, Rollup, OI Timing, Health Report
            # (Analysis phase deprecated — moved to storage layer)
            total_phases = 3 if skip_rollup else 4
            current_phase = 1

            # Phase 1: Collection
            print("")
            print("")
            beautiful_log("Data Collection ({}/{})".format(current_phase, total_phases), 'info')
            collection_results = self._run_collection_phase(trade_date, symbol)
            self.pipeline_results['collection'] = collection_results

            if not collection_results.get('success'):
                logging.error("Collection phase failed - stopping pipeline")
                return self._finalize_results(False, "Collection failed")

            current_phase += 1

            # (Analysis phase deprecated — build_pattern calculated during insert, no Gap from Max needed)
            self.pipeline_results['analysis'] = {'success': True, 'skipped': True, 'reason': 'Deprecated - moved to storage layer'}

            # Phase 2: Symbol Rollup (conditional)
            if not skip_rollup:
                print("")
                print("")
                beautiful_log("Symbol Rollup ({}/{})".format(current_phase, total_phases), 'info')
                rollup_results = self._run_rollup_phase(trade_date, symbol)
                self.pipeline_results['rollup'] = rollup_results
                current_phase += 1
            else:
                beautiful_log("Skipping symbol rollup (--skip-rollup flag)", 'info')
                self.pipeline_results['rollup'] = {'skipped': True}

            # Phase 3: OI Timing Calculator (Smart Money Analysis)
            print("")
            print("")
            beautiful_log("OI Timing Analysis ({}/{})".format(current_phase, total_phases), 'info')
            timing_results = self._run_timing_phase(trade_date)
            self.pipeline_results['timing'] = timing_results

            current_phase += 1

            # Phase 4: Health Report
            print("")
            print("")
            beautiful_log("Health Report ({}/{})".format(current_phase, total_phases), 'info')
            health_results = self._generate_health_report(trade_date)
            self.pipeline_results['health'] = health_results
            
            # Calculate total execution time
            total_time = time.time() - pipeline_start
            self.pipeline_results['total_execution_time'] = total_time

            # Log diagnostic summary
            collection = self.pipeline_results.get('collection', {})
            analysis = self.pipeline_results.get('analysis', {})
            rollup = self.pipeline_results.get('rollup', {})
            timing = self.pipeline_results.get('timing', {})

            log_diagnostic_summary(
                diag_logger,
                phase,
                symbols_collected=collection.get('symbols_collected', 0),
                symbols_failed=collection.get('symbols_failed', 0),
                total_contracts=collection.get('total_contracts', 0),
                collection_time=collection.get('execution_time', 0),
                interesting_strikes=analysis.get('interesting_strikes_found', 0),
                momentum_updates=analysis.get('momentum_updates_made', 0),
                analysis_time=analysis.get('execution_time', 0),
                summaries_created=rollup.get('summaries_created', 0),
                rollup_time=rollup.get('execution_time', 0),
                timing_contracts=timing.get('contracts_updated', 0),
                timing_time=timing.get('execution_time', 0),
                total_time=total_time,
                success=True
            )

            return self._finalize_results(True, "Pipeline completed successfully")
            
        except Exception as e:
            logging.error("PIPELINE ERROR: {}".format(e))
            traceback.print_exc()
            self.pipeline_results['errors'].append(str(e))

            # AUTOFIX INTEGRATION: Top-level orchestrator crash
            handle_error(
                error_type='op_pipeline_unexpected_error',
                context={
                    'error': str(e),
                    'traceback': traceback.format_exc(),
                    'trade_date': trade_date,
                    'phase': 'unknown',
                    'pipeline_results': self.pipeline_results,
                    'main_py_pid': os.getppid()
                },
                severity='CRITICAL'
            )
            # Never reached - handle_error exits

            return self._finalize_results(False, "Pipeline error: {}".format(e))
    
    def _run_collection_phase(self, trade_date, symbol=None):
        """Run collection phase with beautiful progress logging
        
        Args:
            trade_date: Trade date string
            symbol: Optional single symbol for testing
            
        Returns:
            dict: Collection results
        """
        try:
            phase_start = time.time()
            
            # Determine universe
            if symbol:
                symbols_list = [symbol.upper()]
            else:
                symbols_list = get_specialty_list('klmn_800')
            
            # Initialize collector
            collector = OIDCollector()
            
            logging.info("   ├─ Universe: {} symbols".format(len(symbols_list)))
            logging.info("   └─ Start Time: {}".format(now_eastern().strftime('%H:%M:%S ET')))
            
            # Run collection using the correct method
            if symbol:
                success = collector.collect_daily_oi(single_symbol=symbol)
            else:
                success = collector.collect_daily_oi()
            
            # Get collection stats
            stats = collector.collection_stats
            phase_time = time.time() - phase_start

            # AUTOFIX INTEGRATION: Detect silent failure (zero contracts)
            if stats.get('total_contracts', 0) == 0 and stats.get('api_calls_made', 0) > 0:
                handle_error(
                    error_type='op_collection_zero_contracts',
                    context={
                        'symbols_attempted': stats.get('total_symbols', 0),
                        'successful_symbols': stats.get('successful_symbols', 0),
                        'failed_symbols': stats.get('failed_symbols', 0),
                        'api_calls_made': stats.get('api_calls_made', 0),
                        'trade_date': trade_date,
                        'failed_symbol_list': stats.get('failed_symbol_list', [])[:20],
                        'location': 'orchestrator',
                        'main_py_pid': os.getppid()
                    },
                    severity='CRITICAL'
                )
                # Never reached - handle_error exits with sys.exit(1)

            if success:
                # Log failed symbols if any (collector already printed the summary)
                if stats.get('failed_symbols', 0) > 0:
                    failed_list = stats.get('failed_symbol_list', [])
                    logging.warning("⚠️ {} symbols failed collection".format(len(failed_list)))
                    logging.info("   Failed symbols: {}".format(', '.join(failed_list[:15])))
                    if len(failed_list) > 15:
                        logging.info("   ... and {} more".format(len(failed_list) - 15))
            else:
                logging.error("Collection phase failed after {:.1f} minutes".format(phase_time / 60))

                # AUTOFIX INTEGRATION: Collection returned False
                handle_error(
                    error_type='op_collection_failed',
                    context={
                        'symbols_attempted': stats.get('total_symbols', 0),
                        'successful_symbols': stats.get('successful_symbols', 0),
                        'failed_symbols': stats.get('failed_symbols', 0),
                        'total_contracts': stats.get('total_contracts', 0),
                        'api_calls_made': stats.get('api_calls_made', 0),
                        'execution_time_minutes': phase_time / 60,
                        'trade_date': trade_date,
                        'failed_symbol_list': stats.get('failed_symbol_list', [])[:20],
                        'main_py_pid': os.getppid()
                    },
                    severity='CRITICAL'
                )
                # Never reached - handle_error exits

            return {
                'success': success,
                'execution_time': phase_time,
                'symbols_collected': stats.get('successful_symbols', 0),
                'symbols_failed': stats.get('failed_symbols', 0),
                'failed_symbols': stats.get('failed_symbol_list', []),
                'total_contracts': stats.get('total_contracts', 0),
                'api_calls': stats.get('api_calls_made', 0),
                'no_contract_symbols': stats.get('no_contract_symbols', []),
                'no_contract_count': len(stats.get('no_contract_symbols', [])),
                'total_options_seen': stats.get('total_options_seen', 0),
                'total_options_filtered': stats.get('total_options_filtered', 0),
            }

        except Exception as e:
            logging.error("❌ Collection phase error: {}".format(e))

            # AUTOFIX INTEGRATION: Unexpected collection error
            handle_error(
                error_type='op_collection_unexpected_error',
                context={
                    'error': str(e),
                    'traceback': traceback.format_exc(),
                    'trade_date': trade_date,
                    'symbols_attempted': stats.get('total_symbols', 0) if 'stats' in locals() else 0,
                    'phase': 'collection',
                    'main_py_pid': os.getppid()
                },
                severity='CRITICAL'
            )
            # Never reached - handle_error exits

            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - phase_start if 'phase_start' in locals() else 0
            }
    
    def _run_analysis_phase(self, trade_date, failed_symbols_list=None):
        """Run analysis phase (Gap from Maximum, Momentum, Age tracking)
        
        Args:
            trade_date: Trade date string
            failed_symbols_list: Optional list of symbols to analyze (evening retry mode)
            
        Returns:
            dict: Analysis results
        """
        try:
            phase_start = time.time()
            
            if failed_symbols_list:
                beautiful_log("Running two-phase analysis engine (evening retry mode)", 'info')
                logging.info("   ├─ Symbols: {} failed symbols from morning".format(len(failed_symbols_list)))
                logging.info("   ├─ Phase 1: Interest Detection (Gap from Maximum)")
                logging.info("   └─ Phase 2: Combined Momentum & Position Age Analysis")
            else:
                beautiful_log("Running two-phase analysis engine", 'info')
                logging.info("   ├─ Phase 1: Interest Detection (Gap from Maximum)")
                logging.info("   └─ Phase 2: Combined Momentum & Position Age Analysis")
            logging.info("")
            
            # Run interest detection (Gap from Maximum)
            interest_start = time.time()
            if failed_symbols_list:
                logging.info("   [1/2] Analyzing {} retry symbols for interesting strikes...".format(len(failed_symbols_list)))
                interest_success = self.analyzer.analyze_contracts_for_date(trade_date, failed_symbols_list)
            else:
                logging.info("   [1/2] Detecting interesting strikes using Gap from Maximum...")
                interest_success = self.analyzer.analyze_contracts_for_date(trade_date)
            interest_time = time.time() - interest_start
            
            if interest_success:
                interesting_count = self.analyzer.analysis_stats.get('interesting_strikes_found', 0)
                logging.info("   ✓ Found {:,} interesting strikes in {:.1f}s".format(
                    interesting_count, interest_time
                ))
                interest_results = {
                    'success': True,
                    'interesting_strikes_found': interesting_count,
                    'symbols_processed': self.analyzer.analysis_stats.get('symbols_processed', 0)
                }
            else:
                logging.error("   ✗ Interest detection failed")
                interest_results = {'success': False, 'interesting_strikes_found': 0}
            
            # Run combined momentum and position age analysis
            logging.info("   [2/2] Running combined momentum and position age analysis...")
            momentum_start = time.time()
            combined_results = self.analyzer.calculate_momentum_for_interesting_strikes(trade_date)
            combined_time = time.time() - momentum_start

            
            # Extract momentum_results from combined_results for compatibility
            momentum_results = {
                'success': combined_results.get('success', False),
                'momentum_updates_made': combined_results.get('momentum_updates_made', 0),
                'position_tracking_updates_made': combined_results.get('position_tracking_updates_made', 0)
            }

            if combined_results.get('momentum_updates_made', 0) > 0 or combined_results.get('position_tracking_updates_made', 0) > 0:
                logging.info("   ✓ Updated {:,} momentum values and tracked {:,} positions in {:.1f}s".format(
                    combined_results.get('momentum_updates_made', 0),
                    combined_results.get('position_tracking_updates_made', 0),
                    combined_time
                ))
                momentum_results = {
                    'success': True,
                    'momentum_updates_made': combined_results.get('momentum_updates_made', 0),
                    'position_tracking_updates_made': combined_results.get('position_tracking_updates_made', 0)
                }
            else:
                logging.error("   ✗ Momentum and position tracking failed")
                momentum_results = {'success': False, 'momentum_updates_made': 0}
            
            # For compatibility, create an age_results dict from the combined results
            age_results = {
                'success': True,
                'positions_tracked': combined_results.get('position_tracking_updates_made', 0)
            }

            # OI Timing now handled in separate phase (Phase 4) - removed old broken timing calculator
            # Old timing calculator had KeyError bug (used tuple indexing on dict results) - replaced with standalone script

            # Calculate totals
            phase_time = time.time() - phase_start
            all_success = (interest_results.get('success') and
                          momentum_results.get('success') and
                          age_results.get('success'))

            # Summary
            logging.info("")
            if all_success:
                beautiful_log("Analysis phase completed successfully", 'success')
            else:
                beautiful_log("Analysis phase completed with errors", 'warning')

            logging.info("   └─ Total execution time: {:.1f} seconds".format(phase_time))
            
            return {
                'success': all_success,
                'execution_time': phase_time,
                'interest_detection': interest_results,
                'momentum_analysis': momentum_results, 
                'age_tracking': age_results,
                'interesting_strikes_found': interest_results.get('interesting_strikes_found', 0),
                'momentum_updates_made': momentum_results.get('momentum_updates_made', 0),
                'position_tracking_updates_made': momentum_results.get('position_tracking_updates_made', 0)  # Add this
            }
            
        except Exception as e:
            logging.error("❌ Analysis phase error: {}".format(e))
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - phase_start if 'phase_start' in locals() else 0
            }
    
    def _run_rollup_phase(self, trade_date, symbol=None, failed_symbols_list=None):
        """Run symbol rollup phase to aggregate contract data to symbol level
        
        Args:
            trade_date: Trade date string
            symbol: Optional single symbol for testing
            failed_symbols_list: Optional list of symbols to rollup (evening retry mode)
            
        Returns:
            dict: Rollup results
        """
        try:
            phase_start = time.time()
            
            if failed_symbols_list:
                beautiful_log("Aggregating contract data for {} retry symbols".format(len(failed_symbols_list)), 'info')
                logging.info("   ├─ Symbols: {}".format(', '.join(failed_symbols_list[:10])))
                if len(failed_symbols_list) > 10:
                    logging.info("   │   ... and {} more".format(len(failed_symbols_list) - 10))
            else:
                beautiful_log("Aggregating contract data to symbol level", 'info')
            logging.info("   ├─ Calculating Put/Call ratios")
            logging.info("   ├─ Finding concentration strikes")
            logging.info("   └─ Generating display summaries")
            
            # Initialize rollup
            rollup = OIDSymbolRollup(self.storage)
            
            # Run rollup process with appropriate symbol filter
            if failed_symbols_list:
                rollup_stats = rollup.process_symbols(trade_date, symbol_filter=failed_symbols_list)
            elif symbol:  # Test mode
                rollup_stats = rollup.process_symbols(trade_date, symbol_filter=symbol)
            else:  # Full universe
                rollup_stats = rollup.process_symbols(trade_date)
            
            # Get results from the stats dictionary
            phase_time = time.time() - phase_start
            rollup_success = rollup_stats.get('summaries_created', 0) > 0 or rollup_stats.get('symbols_processed', 0) > 0
            
            # Rollup module already printed its own completion stats
            if not rollup_success:
                logging.error("❌ Symbol rollup failed after {:.1f} seconds".format(phase_time))
            
            return {
                'success': rollup_success,
                'execution_time': phase_time,
                'symbols_processed': rollup_stats.get('symbols_processed', 0),
                'symbols_with_data': rollup_stats.get('symbols_with_data', 0),
                'summaries_created': rollup_stats.get('summaries_created', 0)
            }


        except Exception as e:
            logging.error("❌ Symbol rollup error: {}".format(e))

            # AUTOFIX INTEGRATION: Rollup failure (non-blocking)
            handle_error(
                error_type='op_rollup_failed',
                context={
                    'error': str(e),
                    'traceback': traceback.format_exc(),
                    'trade_date': trade_date,
                    'symbols_processed': rollup_stats.get('symbols_processed', 0) if 'rollup_stats' in locals() else 0,
                    'phase': 'rollup'
                },
                severity='ERROR'  # Batch mode - rollup isn't critical
            )

            # Don't let rollup failure break the pipeline
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - phase_start if 'phase_start' in locals() else 0
            }

    def _run_timing_phase(self, trade_date):
        """Run OI timing calculator to determine when positioning was established

        Args:
            trade_date: Trade date string

        Returns:
            dict: Timing calculation results
        """
        try:
            phase_start = time.time()

            beautiful_log("Calculating OI timing (smart money vs retail analysis)", 'info')
            logging.info("   ├─ Finding when OI was established (50% threshold)")
            logging.info("   ├─ Getting stock prices on build dates")
            logging.info("   └─ Updating option_contracts with timing data")

            # Import and initialize OI timing calculator
            from strategies.option_pipeline.op_timing_calculator import OITimingCalculator

            calc = OITimingCalculator(db_path='data/datalake.db')

            # Process current date
            stats = calc.process_date(trade_date)

            # Close calculator
            calc.close()

            phase_time = time.time() - phase_start
            timing_success = stats.get('updated', 0) > 0

            if timing_success:
                logging.info("")
                beautiful_log("OI timing analysis completed successfully", 'success')
                logging.info("   ├─ Total contracts processed: {:,}".format(stats.get('total', 0)))
                logging.info("   ├─ Timing data added: {:,}".format(stats.get('updated', 0)))
                logging.info("   ├─ Skipped (insufficient data): {:,}".format(stats.get('skipped', 0)))
                logging.info("   └─ Execution time: {:.1f} seconds".format(phase_time))
            else:
                logging.warning("⚠️ OI timing analysis completed but no contracts updated")

            return {
                'success': timing_success,
                'execution_time': phase_time,
                'contracts_processed': stats.get('total', 0),
                'contracts_updated': stats.get('updated', 0),
                'contracts_skipped': stats.get('skipped', 0)
            }

        except Exception as e:
            logging.error("❌ OI timing calculator error: {}".format(e))

            # AUTOFIX INTEGRATION: Timing calculator failure (non-blocking)
            handle_error(
                error_type='op_timing_failed',
                context={
                    'error': str(e),
                    'traceback': traceback.format_exc(),
                    'trade_date': trade_date,
                    'phase': 'timing'
                },
                severity='ERROR'  # Batch mode - timing isn't critical
            )

            # Don't let timing failure break the pipeline
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - phase_start if 'phase_start' in locals() else 0
            }

    def _generate_health_report(self, trade_date):
        """Generate comprehensive health report
        
        Args:
            trade_date: Trade date string
            
        Returns:
            dict: Health report results
        """
        try:
            phase_start = time.time()
            
            beautiful_log("Generating comprehensive health report with full pipeline analytics", 'info')
            logging.info("   Checking collection coverage, analysis completeness, and data quality...")

            # Comprehensive collection status checking across all phases
            pipeline_health = self._check_comprehensive_pipeline_status(trade_date)
            
            # Initialize health reporter
            # CHANGED: Use centralized logs directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(script_dir))
            log_file_path = os.path.join(project_root, 'logs', 'option_pipeline_{}.log'.format(trade_date))

            health_reporter = OIDHealthReporter(trade_date, log_file_path)
            
            # Generate simplified health report directly from pipeline results
            report_path = health_reporter.generate_simple_health_report(
                self.pipeline_results,
                pipeline_health
            )
            
            phase_time = time.time() - phase_start
            
            if report_path:
                beautiful_log("Comprehensive health report generated in {:.1f} seconds".format(phase_time), 'success')
                logging.info("   └─ Report file: {}".format(os.path.relpath(report_path, project_root)))
                
                return {
                    'success': True,
                    'execution_time': phase_time,
                    'report_path': report_path,
                    'report_type': 'comprehensive',
                    'pipeline_health': pipeline_health
                }
            else:
                logging.error("❌ Comprehensive health report generation failed")
                
                return {
                'success': True,
                'execution_time': phase_time,
                'report_path': report_results.get('report_path', '')
            }
            
        except Exception as e:
            logging.error("❌ Health report error: {}".format(e))
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - phase_start if 'phase_start' in locals() else 0
            }

    def _check_comprehensive_pipeline_status(self, trade_date):
        """Comprehensive health check across all pipeline phases
        
        Args:
            trade_date: Trade date string
            
        Returns:
            dict: Complete pipeline health assessment
        """
        try:
            logging.debug("🔍 Performing comprehensive pipeline health check...")
            
            # Get complete universe for comparison
            universe_symbols = get_specialty_list('klmn_800')
            total_universe = len(universe_symbols)
            
            # Phase 1: Collection Status Check
            collection_query = """
            SELECT DISTINCT symbol 
            FROM option_contracts 
            WHERE date(created_at) = ?
            ORDER BY symbol
            """
            collected_result = self.storage.query_db(collection_query, (trade_date,))
            collected_symbols = set([row['symbol'] for row in collected_result]) if collected_result else set()
            
            # Phase 2: Analysis Status Check
            analysis_query = """
            SELECT COUNT(DISTINCT symbol) as analyzed_symbols
            FROM option_contracts
            WHERE date(created_at) = ?
                AND build_pattern IS NOT NULL
            """
            analysis_result = self.storage.query_db(analysis_query, (trade_date,))
            analyzed_count = analysis_result[0]['analyzed_symbols'] if analysis_result else 0
            
            # Phase 3: Momentum Analysis Status Check
            momentum_query = """
            SELECT COUNT(DISTINCT symbol) as momentum_symbols
            FROM option_contracts 
            WHERE date(created_at) = ? 
                AND (oi_momentum_5d IS NOT NULL)
            """
            momentum_result = self.storage.query_db(momentum_query, (trade_date,))
            momentum_count = momentum_result[0]['momentum_symbols'] if momentum_result else 0
            
            # Phase 4: Rollup Status Check (if rollup was run)
            rollup_query = """
            SELECT COUNT(*) as rollup_count
            FROM option_symbol_summary 
            WHERE trade_date = ?
            """
            rollup_result = self.storage.query_db(rollup_query, (trade_date,))
            rollup_count = rollup_result[0]['rollup_count'] if rollup_result else 0
            
            # Calculate health metrics
            collection_rate = len(collected_symbols) / total_universe * 100
            analysis_rate = analyzed_count / len(collected_symbols) * 100 if collected_symbols else 0
            momentum_rate = momentum_count / len(collected_symbols) * 100 if collected_symbols else 0
            
            # Determine overall health status
            missing_symbols = list(set(universe_symbols) - collected_symbols)
            
            health_status = "HEALTHY"
            if collection_rate < 95:
                health_status = "DEGRADED"
            if collection_rate < 85:
                health_status = "CRITICAL"
                
            pipeline_health = {
                'overall_status': health_status,
                'universe_size': total_universe,
                'collection_phase': {
                    'symbols_collected': len(collected_symbols),
                    'collection_rate': collection_rate,
                    'missing_symbols_count': len(missing_symbols),
                    'missing_symbols': missing_symbols[:20] if missing_symbols else []  # Show first 20
                },
                'analysis_phase': {
                    'symbols_analyzed': analyzed_count,
                    'analysis_rate': analysis_rate
                },
                'momentum_phase': {
                    'symbols_with_momentum': momentum_count,
                    'momentum_rate': momentum_rate
                },
                'rollup_phase': {
                    'summaries_created': rollup_count,
                    'rollup_enabled': rollup_count > 0
                }
            }
            
            # Log comprehensive status
            beautiful_log("Pipeline Health Assessment", 'info')
            logging.info("   • Overall Status: {}".format(health_status))
            logging.info("   • Collection: {}/{} symbols ({:.1f}%)".format(len(collected_symbols), total_universe, collection_rate))
            logging.info("   • Analysis: {}/{} symbols ({:.1f}%)".format(analyzed_count, len(collected_symbols), analysis_rate))
            logging.info("   • Momentum: {}/{} symbols ({:.1f}%)".format(momentum_count, len(collected_symbols), momentum_rate))
            logging.info("   • Rollup: {} summaries created".format(rollup_count))

            if missing_symbols:
                logging.info("   • Missing symbols: {} (showing first 10: {})".format(
                    len(missing_symbols), ', '.join(missing_symbols[:10])))

            # Data quality from collection phase
            collection = self.pipeline_results.get('collection', {})
            total_seen = collection.get('total_options_seen', 0)
            total_filtered = collection.get('total_options_filtered', 0)
            no_contract_count = collection.get('no_contract_count', 0)
            if total_seen > 0:
                filter_pct = (total_filtered / total_seen) * 100
                logging.info("   • OI Filter: {:,}/{:,} options filtered ({:.1f}%)".format(
                    total_filtered, total_seen, filter_pct))
            if no_contract_count > 0:
                logging.info("   • No-Contract Symbols: {}".format(no_contract_count))

            return pipeline_health
            
        except Exception as e:
            logging.warning("⚠️ Pipeline health check error: {} (returning UNKNOWN status)".format(e))
            return {
                'overall_status': 'UNKNOWN',
                'error': str(e),
                'universe_size': len(get_specialty_list('klmn_800')),
                'collection_phase': {'error': str(e)},
                'analysis_phase': {'error': str(e)},
                'momentum_phase': {'error': str(e)},
                'rollup_phase': {'error': str(e)}
            }
    
    def _finalize_results(self, success, message):
        """Finalize and return pipeline results
        
        Args:
            success: Overall pipeline success
            message: Summary message
            
        Returns:
            dict: Complete pipeline results
        """
        self.pipeline_results['success'] = success
        self.pipeline_results['message'] = message
        self.pipeline_results['completion_time'] = eastern_isoformat()
        
        return self.pipeline_results


def setup_logging(log_level='INFO', trade_date=None):
    """Configure logging for Option Pipeline orchestrator
    
    Args:
        log_level: Logging level (INFO, DEBUG, etc.)
        trade_date: Trade date for log file naming
        
    Returns:
        str: Path to log file
    """
    # CHANGED: Create centralized logs directory at project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # CHANGED: Renamed from oid to option_pipeline
    if trade_date:
        log_filename = 'option_pipeline_{}.log'.format(trade_date)
    else:
        log_filename = 'option_pipeline_{}.log'.format(datetime.now().strftime('%Y-%m-%d'))

    log_file_path = os.path.join(logs_dir, log_filename)
    
    # Configure logging
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatters — file keeps milliseconds, console gets clean HH:MM:SS
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_formatter.default_msec_format = None

    # File handler
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers = []
    
    # Add our handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    logging.info("Logging initialized - Level: {} - File: {}".format(log_level, log_filename))

    return log_file_path

def setup_diagnostic_logging():
    """Set up separate diagnostic log for high-level summaries only

    Returns:
        logging.Logger: Diagnostic logger instance
    """
    from pathlib import Path

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    logs_dir = Path(project_root) / "logs" / "diagnostic"
    logs_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime('%Y-%m-%d')
    logfile_name = 'option_pipeline_{}.log'.format(date_str)
    logfile = logs_dir / logfile_name

    diag_logger = logging.getLogger('option_pipeline_diagnostic')
    diag_logger.setLevel(logging.INFO)
    diag_logger.propagate = False  # Don't send to root logger

    # Clear existing handlers
    diag_logger.handlers = []

    # File handler only (no console spam)
    file_handler = logging.FileHandler(logfile, encoding='utf-8')
    formatter = logging.Formatter('%(message)s')  # Simple format
    file_handler.setFormatter(formatter)
    diag_logger.addHandler(file_handler)

    return diag_logger

def log_diagnostic_summary(diag_logger, phase, **metrics):
    """Write high-level diagnostic summary for this operation

    Args:
        diag_logger: Diagnostic logger instance
        phase: 'morning' or 'evening'
        **metrics: Phase-specific metrics to log
    """
    try:
        from tools.timezone_utils import now_eastern
        now = now_eastern().strftime('%Y-%m-%d %H:%M:%S')

        if phase == 'morning':
            # Morning run summary
            failed_count = metrics.get('symbols_failed', 0)
            diag_logger.info("[{}] Morning Collection: {} symbols collected{} | {} contracts | {:.1f}s".format(
                now,
                metrics.get('symbols_collected', 0),
                " | {} failed".format(failed_count) if failed_count > 0 else "",
                metrics.get('total_contracts', 0),
                metrics.get('collection_time', 0)
            ))
            diag_logger.info("[{}] Morning Analysis: {} interesting strikes | {} momentum updates | {:.1f}s".format(
                now,
                metrics.get('interesting_strikes', 0),
                metrics.get('momentum_updates', 0),
                metrics.get('analysis_time', 0)
            ))
            if not metrics.get('rollup_skipped', False):
                diag_logger.info("[{}] Morning Rollup: {} summaries created | {:.1f}s".format(
                    now,
                    metrics.get('summaries_created', 0),
                    metrics.get('rollup_time', 0)
                ))
            if metrics.get('timing_contracts', 0) > 0:
                diag_logger.info("[{}] OI Timing: {} contracts updated | {:.1f}s".format(
                    now,
                    metrics.get('timing_contracts', 0),
                    metrics.get('timing_time', 0)
                ))
            diag_logger.info("[{}] Morning Complete | Total: {:.1f}s | Success: {}".format(
                now,
                metrics.get('total_time', 0),
                'YES' if metrics.get('success', False) else 'NO'
            ))

        elif phase == 'evening':
            # Evening run summary
            failed_count = metrics.get('symbols_failed', 0)
            diag_logger.info("[{}] Evening Collection: {} symbols collected{} | {} contracts | {:.1f}s".format(
                now,
                metrics.get('symbols_collected', 0),
                " | {} failed".format(failed_count) if failed_count > 0 else "",
                metrics.get('total_contracts', 0),
                metrics.get('collection_time', 0)
            ))
            diag_logger.info("[{}] Evening Analysis: {} interesting strikes | {} momentum updates | {:.1f}s".format(
                now,
                metrics.get('interesting_strikes', 0),
                metrics.get('momentum_updates', 0),
                metrics.get('analysis_time', 0)
            ))
            if not metrics.get('rollup_skipped', False):
                diag_logger.info("[{}] Evening Rollup: {} summaries created | {:.1f}s".format(
                    now,
                    metrics.get('summaries_created', 0),
                    metrics.get('rollup_time', 0)
                ))
            if metrics.get('timing_contracts', 0) > 0:
                diag_logger.info("[{}] OI Timing: {} contracts updated | {:.1f}s".format(
                    now,
                    metrics.get('timing_contracts', 0),
                    metrics.get('timing_time', 0)
                ))
            diag_logger.info("[{}] Evening Complete | Total: {:.1f}s | Success: {}".format(
                now,
                metrics.get('total_time', 0),
                'YES' if metrics.get('success', False) else 'NO'
            ))

    except Exception as e:
        logging.error("Error writing diagnostic summary: {}".format(e))


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Option Pipeline Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python oid_main2.py                           # Full universe collection
  python oid_main2.py --no-interaction         # Automated mode (no prompts)
  python oid_main2.py --symbol AAPL             # Test single symbol
  python oid_main2.py --skip-rollup             # Skip symbol rollup phase
        """
    )
    
    # Optional arguments
    parser.add_argument('--symbol', type=str,
                       help='Test mode: Run single symbol through full pipeline')
    parser.add_argument('--skip-rollup', action='store_true',
                       help='Skip symbol rollup phase (for debugging)')
    parser.add_argument('--no-interaction', action='store_true',
                       help='Skip all user prompts (for automation)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level (default: INFO)')
    
    return parser.parse_args()


def main():
    """Main entry point for Option Pipeline orchestrator"""
    args = parse_arguments()
    
    # Determine trade date (always today)
    trade_date = eastern_date_string()
    
    # Set up logging
    log_file_path = setup_logging(args.log_level, trade_date)
    
    try:
        # Initialize orchestrator
        orchestrator = OPOrchestrator(no_interaction=args.no_interaction)
        
        # Wait for user confirmation unless no-interaction mode
        if not args.no_interaction:
            print("\nThis will run the complete Option Pipeline sequentially.")
            orchestrator.wait_for_enter()
        
        # Run the pipeline
        results = orchestrator.run_pipeline(
            trade_date=trade_date,
            symbol=args.symbol,
            skip_rollup=args.skip_rollup
        )
        
        # Wait before exit unless no-interaction mode
        orchestrator.wait_for_enter()
        
        # Return success code for automation
        return 0 if results['success'] else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        logging.warning("Pipeline interrupted by user (Ctrl+C)")
        return 2
    except Exception as e:
        print("\n❌ Fatal error: {}".format(e))
        logging.error("Fatal error: {}".format(e))
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())