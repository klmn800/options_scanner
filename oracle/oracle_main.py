#!/usr/bin/env python3
"""
Oracle CLI - Main Interface (oracle_main.py)
-------------------------------------------
Main entry point and conversation loop for the Oracle CLI.
Orchestrates configuration, database access, and Claude API integration
into a smooth conversational interface for options trading intelligence.

Features:
- Natural language conversation loop with Claude
- Cost tracking and transparency
- Special commands for session management
- Graceful error handling and shutdown
- Command line arguments for flexibility
- Session statistics and export capabilities

Author: Ben (with assistance from Claude)
Date: 2025-07-10
Phase: 1, Step 1.3 - Main CLI Interface
"""

import argparse
import logging
import signal
import sys
import time
import json
import traceback
from datetime import datetime
from pathlib import Path
from colorama import Fore, Style, init

# Import Oracle components
from oracle.oracle_config import OracleConfig, SessionLogger
from oracle.oracle_vanna import OracleVannaClient
from oracle.oracle_data_access import DatabaseConnection

class OracleSession:
    """Manages Oracle CLI session state and statistics"""
    
    def __init__(self):
        self.start_time = time.time()
        self.session_costs = {
            'total_tokens_in': 0,
            'total_tokens_out': 0,
            'total_cost': 0.0,
            'interaction_count': 0
        }
        self.conversation_history = []
        self.current_model = None
        
    def add_interaction(self, user_input, claude_response, tokens_in, tokens_out, cost, model):
        """Record an interaction for session tracking"""
        self.session_costs['total_tokens_in'] += tokens_in
        self.session_costs['total_tokens_out'] += tokens_out
        self.session_costs['total_cost'] += cost
        self.session_costs['interaction_count'] += 1
        self.current_model = model
        
        self.conversation_history.append({
            'timestamp': datetime.now().isoformat(),
            'user_input': user_input,
            'claude_response': claude_response,
            'tokens_in': tokens_in,
            'tokens_out': tokens_out,
            'cost': cost,
            'model': model
        })
    
    def get_duration_minutes(self):
        """Get session duration in minutes"""
        return (time.time() - self.start_time) / 60
    
    def get_stats_summary(self):
        """Get formatted session statistics"""
        duration = self.get_duration_minutes()
        costs = self.session_costs
        
        return {
            'duration_minutes': duration,
            'interaction_count': costs['interaction_count'],
            'total_tokens': costs['total_tokens_in'] + costs['total_tokens_out'],
            'total_cost': costs['total_cost'],
            'current_model': self.current_model
        }


class OracleCLI:
    """Main Oracle CLI application"""
    
    def __init__(self, args):
        self.args = args
        self.session = OracleSession()
        self.shutdown_requested = False
        
        # Initialize colorama for cross-platform color support
        init(autoreset=True)
        
        # Initialize configuration FIRST
        self.config = OracleConfig()
        
        # Initialize session logger
        self.session_logger = SessionLogger(self.config)
        
        # Determine model override
        model_override = None
        if hasattr(self.args, 'model') and self.args.model:
            model_override = self.args.model
        
        # Initialize Vanna client with proper config and debug flag
        self.vanna_client = OracleVannaClient(self.config, model_override=model_override, debug_mode=args.debug)
        self.data_access = None
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n" + "="*50)
        print("Shutdown requested by user...")
        self.shutdown_requested = True
    
    def initialize(self):
        """Initialize all Oracle components"""
        try:
            print("Initializing Oracle CLI...")
            
            # Configuration already loaded in __init__
            print("  📋 Configuration loaded...")
            
            # Initialize data access with debug mode
            print("  🗃️  Connecting to database...")
            self.data_access = DatabaseConnection(self.config, debug_mode=self.args.debug)
            
            # Vanna client already initialized in __init__
            print("  🤖 Oracle (Powered by Vanna) ready...")
            
            # Check training status and handle retraining
            print("  🧠 Checking training status...")
            training_summary = self.vanna_client.get_training_summary()

            # Check if forced retraining requested
            if self.args.retrain:
                print("  🔄 FORCE RETRAINING requested - training on ALL tables...")
                self.vanna_client.force_comprehensive_training()
                print("  🎯 Comprehensive training completed!")
            elif training_summary.get("total_training_items", 0) == 0:
                print("  🎯 First run detected - training Oracle on your data...")
                self.vanna_client.full_training_sequence()
                print("  ✅ Training completed!")
            else:
                print(f"  ✅ Training data loaded ({training_summary.get('total_training_items', 0)} items)")
            
            # Validate everything is working
            print("  ✅ Running connectivity tests...")
            self._validate_setup()

            # Start session logging (check for --no-session-logging flag)
            session_logging_enabled = not getattr(self.args, 'no_session_logging', False)
            self.session_logger.start_session(session_logging_enabled)
            if session_logging_enabled:
                print("  📝 Session logging enabled...")
            else:
                print("  📝 Session logging disabled...")

            return True
            
        except Exception as e:
            print("❌ Initialization failed: {}".format(e))
            logging.error("Oracle initialization error: {}".format(e))
            return False
    
    def _validate_setup(self):
        """Validate that all components are working with lightweight checks"""
        # Skip heavy COUNT queries on massive tables during startup
        try:
            # Test basic connectivity with a fast query
            test_result = self.data_access.execute_query("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
            if not test_result['success']:
                raise RuntimeError("Basic database connectivity test failed")
            
            logging.info("Database connectivity validated (skipped heavy table counts for speed)")
            logging.info("All components validated successfully")
            
        except Exception as e:
            raise RuntimeError(f"Database validation failed: {e}")
    
    def display_welcome(self):
        """Display welcome message with system information"""
        print("\n" + "="*60)
        print("Oracle CLI - Options Trading Intelligence")
        print("="*60)
        
        # Get database health information
        health = self.data_access.check_database_health()
        checks = health.get('checks', {})

        print("Connected to datalake.db")
        print("  Database status: {}".format(health['overall_status']))

        # Show table counts if available
        if 'option_contracts' in checks and checks['option_contracts']['passed']:
            print("  {}".format(checks['option_contracts']['message']))
        if 'flow_alerts' in checks and checks['flow_alerts']['passed']:
            print("  Flow alerts: {}".format(checks['flow_alerts']['message']))
        if 'symbol_metadata' in checks and checks['symbol_metadata']['passed']:
            print("  Symbol metadata: {}".format(checks['symbol_metadata']['message']))
        
        # Model information
        model_display = self.vanna_client.get_current_model()
        if 'haiku' in model_display.lower():
            cost_info = "(fast & economical)"
        elif 'sonnet' in model_display.lower():
            cost_info = "(quality mode)"
        else:
            cost_info = ""

        print("\nModel: {} {}".format(model_display, cost_info))
        
        if self.args.no_functions:
            print("⚠️  Function calling disabled - using custom SQL only")
        
        print("\nType /help for commands, /exit to quit")
        print("="*60)
    
    def conversation_loop(self):
        """Main conversation loop"""
        print("\nReady for your questions!")
        
        while not self.shutdown_requested:
            try:
                # Get user input
                user_input = input("\nOracle> ").strip()
                
                if not user_input:
                    continue
                
                # Handle special commands
                if user_input.startswith('/'):
                    if self._handle_special_command(user_input):
                        continue
                    else:
                        break  # Exit requested
                
                # Process with Claude
                self._process_user_question(user_input)
                
            except EOFError:
                # Handle Ctrl+D
                print("\nGoodbye!")
                break
            except KeyboardInterrupt:
                # This is handled by signal handler
                break
            except Exception as e:
                print("❌ Error processing question: {}".format(e))
                logging.error("Conversation error: {}".format(e))
                print("You can continue with another question or type /exit to quit.")
    
    def _handle_special_command(self, command):
        """Handle special commands like /help, /stats, etc."""
        parts = command[1:].split()
        cmd = parts[0].lower()
        
        if cmd in ['exit', 'quit']:
            return False
        
        elif cmd == 'help':
            self._show_help()
        
        elif cmd == 'stats':
            self._show_stats()
        
        elif cmd == 'clear':
            self._clear_conversation()
        
        elif cmd == 'export':
            filename = parts[1] if len(parts) > 1 else None
            self._export_conversation(filename)
        
        elif cmd == 'model':
            model = parts[1] if len(parts) > 1 else None
            self._switch_model(model)
        
        else:
            print("Unknown command: {}. Type /help for available commands.".format(command))
        
        return True
    
    def _process_user_question(self, user_input):
        """Process user question with Claude"""
        print("🤔 Thinking...", end='', flush=True)
        
        try:
            start_time = time.time()
            
            # Send to Claude with model override if specified
            model_override = None
            if hasattr(self.args, 'model') and self.args.model:
                model_map = {
                    'haiku': 'claude-3-5-haiku-20241022',
                    'sonnet': 'claude-3-5-sonnet-20241022'
                }
                model_override = model_map.get(self.args.model.lower())
            
            response_data = self.vanna_client.ask_question(
                user_input
            )
            
            # Clear thinking indicator
            print("\r" + " " * 20 + "\r", end='')

            # Log the query to session
            self.session_logger.log_query(user_input, response_data)
            
            if response_data and response_data.get('success', False):
                # Display Claude's response in yellow
                content = response_data.get('content', '')
                if content.strip():
                    print(Fore.YELLOW + content + Style.RESET_ALL)
                else:
                    print("❌ Received empty response from Claude")
                    
                # Display cost information - FIXED: Handle new two-model token breakdown
                token_breakdown = response_data.get('token_breakdown', {})
                if token_breakdown and 'combined_cost' in token_breakdown:
                    # Enhanced format with SQL + Analysis breakdown
                    sql_tokens = token_breakdown.get('sql_generation', {})
                    analysis_tokens = token_breakdown.get('results_analysis', {})
                    combined_cost = token_breakdown.get('combined_cost', 0.0)
                    total_tokens = token_breakdown.get('total_tokens', 0)
                    
                    print("\n[SQL: {}in/{}out + Analysis: {}in/{}out = {:,} tokens | ${:.4f} total]".format(
                        sql_tokens.get('input_tokens', 0),
                        sql_tokens.get('output_tokens', 0), 
                        analysis_tokens.get('input_tokens', 0),
                        analysis_tokens.get('output_tokens', 0),
                        total_tokens,
                        combined_cost
                    ))
                else:
                    # Fallback to single-model format (backwards compatibility)
                    tokens_used = response_data.get('tokens_used', {})
                    total_tokens = tokens_used.get('total_tokens', 0)
                    cost = tokens_used.get('cost', 0.0)
                    model_used = tokens_used.get('model', 'unknown')
                    
                    if total_tokens > 0:
                        model_name = 'haiku' if 'haiku' in model_used.lower() else 'sonnet'
                        print("\n[Tokens: {:,} | Cost: ${:.4f} ({})]".format(
                            total_tokens, cost, model_name
                        ))
                    else:
                        print("\n[Tokens: N/A | Cost: N/A]")
            
            elif response_data and not response_data.get('success', True):
                # Handle API errors
                error_msg = response_data.get('error', 'Unknown error')
                print("❌ Claude API error: {}".format(error_msg))
            else:
                print("❌ No response received from Claude")
                    
        except Exception as e:
            print("\r" + " " * 20 + "\r", end='')  # Clear thinking indicator
            print("❌ Error getting response: {}".format(e))
            logging.error("Claude API error: {}".format(e))
    
    def _show_help(self):
        """Display help information"""
        print("\nOracle CLI Commands:")
        print("="*30)
        print("/help               - Show this help message")
        print("/stats              - Show session statistics")
        print("/clear              - Clear conversation history")
        print("/export [filename]  - Export conversation to file")
        print("/model [model]      - Switch Claude model (haiku/sonnet)")
        print("/exit or /quit      - Exit Oracle CLI")
        print("\nExample Questions:")
        print("- What symbols are available?")
        print("- What's unusual about AAPL today?")
        print("- Show me recent flow alerts")
        print("- How does PEP volume compare to normal?")
    
    def _show_stats(self):
        """Display session statistics"""
        stats = self.vanna_client.get_usage_summary()
        
        print("\nSession Statistics:")
        print("="*25)
        print("Duration: {:.1f} minutes".format(stats['duration_minutes']))
        print("Messages: {}".format(stats['interaction_count']))
        print("Total tokens: {:,}".format(stats['total_tokens']))
        print("Estimated cost: ${:.4f}".format(stats['total_cost']))
        print("Current model: {}".format(stats['current_model'] or 'Not set'))
    
    def _clear_conversation(self):
        """Clear conversation history"""
        if self.vanna_client:
            self.vanna_client.clear_conversation_history()
        print("Conversation history cleared.")
    
    def _export_conversation(self, filename=None):
        """Export conversation to file"""
        if not self.session.conversation_history:
            print("No conversation to export.")
            return
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = "oracle_conversation_{}.json".format(timestamp)
        
        try:
            # Ensure .json extension
            if not filename.endswith('.json'):
                filename += '.json'
            
            export_data = {
                'session_info': self.session.get_stats_summary(),
                'conversation': self.session.conversation_history
            }
            
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            print("Conversation exported to: {}".format(filename))
            
        except Exception as e:
            print("❌ Export failed: {}".format(e))
    
    def _switch_model(self, model):
        """Switch Claude model"""
        if not model:
            current = self.vanna_client.switch_model(new_model)
            print("Current model: {}".format(current))
            print("Available models: haiku, sonnet")
            return
        
        model_map = {
            'haiku': 'claude-3-5-haiku-20241022',
            'sonnet': 'claude-3-5-sonnet-20241022'
        }
        
        if model.lower() not in model_map:
            print("❌ Unknown model: {}. Available: haiku, sonnet".format(model))
            return
        
        try:
            new_model = model_map[model.lower()]
            self.vanna_client.switch_model(new_model)
            print("✅ Switched to model: {}".format(model.lower()))
        except Exception as e:
            print("❌ Model switch failed: {}".format(e))
    
    def display_goodbye(self):
        """Display goodbye message with session summary"""
        # End session logging
        self.session_logger.end_session()
        
        print("\n" + "="*50)
        print("Thank you for using Oracle CLI!")
        
        # Get session statistics from session logger if available
        session_stats = self.session_logger.get_session_stats()
        if session_stats:
            print("Session summary:")
            print("  Duration: {:.1f} minutes".format(session_stats['duration_minutes']))
            print("  Messages: {}".format(session_stats['queries_count']))
            print("  Total cost: ${:.4f}".format(session_stats['total_cost']))
            print("  Session log: {}".format(self.session_logger.session_file or 'Not logged'))
        elif self.session.session_costs['interaction_count'] > 0:
            # Fallback to old session tracking
            stats = self.session.get_stats_summary()
            print("Session summary:")
            print("  Duration: {:.1f} minutes".format(stats['duration_minutes']))
            print("  Messages: {}".format(stats['interaction_count']))
            print("  Total cost: ${:.4f}".format(stats['total_cost']))
        
        print("="*50)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Oracle CLI - Conversational AI for Options Trading Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python oracle_main.py                    # Start normal session
  python oracle_main.py --test             # Run test conversation
  python oracle_main.py --model haiku      # Use Haiku model
  python oracle_main.py --no-functions     # Disable function calling
  python oracle_main.py --debug            # Enable debug logging
        """
    )
    
    parser.add_argument('--test', action='store_true',
                       help='Run a test conversation with sample queries')
    parser.add_argument('--model', choices=['haiku', 'sonnet'],
                       help='Override default Claude model')
    parser.add_argument('--no-functions', action='store_true',
                       help='Disable function calling (custom SQL only)')
    parser.add_argument('--export', metavar='FILE',
                       help='Export conversation to file')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--retrain', action='store_true',
                        help='Force comprehensive Vanna retraining on startup')                        
    parser.add_argument('--no-interaction', action='store_true',
        help='Run in batch mode without interactive prompts (for overnight runs)')
    parser.add_argument('--no-session-logging', action='store_true',
        help='Disable session-based conversation logging'
    )
    
    return parser.parse_args()


def setup_logging(debug=False):
    """Set up logging configuration"""
    # CHANGED: Use centralized logs directory at project root
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO
    # CHANGED: Renamed from oracle_main to oracle
    log_file = log_dir / 'oracle_{}.log'.format(
        datetime.now().strftime('%Y-%m-%d')
    )

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler() if debug else logging.NullHandler()
        ]
    )


def run_test_session(oracle_cli):
    """Run a simple test session"""
    print("\n🧪 Running test session...")
    
    test_questions = [
        "What symbols are available?",
        "Show me the database schema"
    ]
    
    for question in test_questions:
        print("\nTest question: {}".format(question))
        oracle_cli._process_user_question(question)
    
    print("\n✅ Test session completed!")


def main():
    """Main entry point for Oracle CLI"""
    args = parse_arguments()
    setup_logging(args.debug)
    
    oracle_cli = OracleCLI(args)
    
    try:
        # Initialize components
        if not oracle_cli.initialize():
            print("❌ Failed to initialize Oracle CLI")
            return 1
        
        # Display welcome message
        oracle_cli.display_welcome()
        
        # Run test session or normal conversation
        if args.test:
            run_test_session(oracle_cli)
        else:
            oracle_cli.conversation_loop()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 0
    except Exception as e:
        logging.error("Fatal error: {}".format(e))
        print("❌ Fatal error: {}".format(e))
        return 1
    finally:
        oracle_cli.display_goodbye()


if __name__ == "__main__":
    sys.exit(main())