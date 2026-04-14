#!/usr/bin/env python3
"""
Oracle Bridge for Claude Code Integration
----------------------------------------
Minimal Oracle interface optimized for programmatic access from Claude Code.
No interactive mode, no startup messages - just direct Q&A functionality.

Usage:
    from oracle_bridge import OracleBridge
    oracle = OracleBridge()
    result = oracle.ask("What are today's unusual flow alerts?")
    print(result['answer'])

Command line:
    python oracle_bridge.py "show me NVDA flow alerts"
    
Multi-query:
    echo "question1\nquestion2" | python oracle_bridge.py --multi

Author: Claude Code Integration
Date: 2025-08-30
"""

import sys
import json
import logging
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import os

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Suppress all startup logging and output
with open(os.devnull, 'w') as devnull:
    with redirect_stdout(devnull), redirect_stderr(devnull):
        # Set logging to ERROR level before any imports
        logging.getLogger().setLevel(logging.ERROR)
        logging.getLogger('oracle').setLevel(logging.ERROR)
        logging.getLogger('httpx').setLevel(logging.ERROR)
        logging.getLogger('anthropic').setLevel(logging.ERROR)
        
        # Now import Oracle components
        from oracle.oracle_vanna import OracleVannaClient
        from oracle.oracle_config import OracleConfig
        from oracle.oracle_data_access import DatabaseConnection

class OracleBridge:
    """Simple bridge for programmatic Oracle access from Claude Code"""
    
    def __init__(self, silent=True, raw_mode=False):
        """
        Initialize Oracle bridge
        
        Args:
            silent: If True, suppress all initialization output (default for Claude Code)
            raw_mode: If True, skip Claude analysis and return raw SQL results only
        """
        self.silent = silent
        self.raw_mode = raw_mode
        
        if silent:
            # Suppress all output during initialization
            with open(os.devnull, 'w') as devnull:
                with redirect_stdout(devnull), redirect_stderr(devnull):
                    self._initialize()
        else:
            self._initialize()
    
    def _initialize(self):
        """Internal initialization"""
        try:
            # Initialize Oracle components
            self.config = OracleConfig()
            self.client = OracleVannaClient(
                self.config, 
                debug_mode=False  # Always quiet mode for programmatic use
            )
            self._initialized = True
        except Exception as e:
            self._initialized = False
            self._init_error = str(e)
    
    def raw_query(self, question):
        """
        Execute just the SQL generation and return raw results without Claude analysis
        Much faster and cheaper for data extraction
        
        Args:
            question (str): The question to convert to SQL and execute
            
        Returns:
            dict: Raw SQL results without analysis
        """
        if not self._initialized:
            return {
                "success": False,
                "error": f"Oracle initialization failed: {getattr(self, '_init_error', 'Unknown error')}",
                "question": question
            }
        
        try:
            # Generate SQL using Vanna (Haiku model)
            if self.silent:
                with open(os.devnull, 'w') as devnull:
                    with redirect_stdout(devnull), redirect_stderr(devnull):
                        sql = self.client.vanna_instance.generate_sql(question)
            else:
                sql = self.client.vanna_instance.generate_sql(question)
            
            # Execute SQL directly through Vanna
            df_results = self.client.vanna_instance.run_sql(sql)
            
            # Convert to list of dicts
            if df_results is not None and not df_results.empty:
                results = df_results.to_dict('records')
            else:
                results = []
            
            return {
                "success": True,
                "question": question,
                "sql_generated": sql,
                "results": results,
                "row_count": len(results),
                "raw_data": True  # Flag to indicate this is raw mode
            }
            
        except Exception as e:
            return {
                "success": False,
                "question": question,
                "error": str(e),
                "raw_data": True
            }
    
    def ask(self, question):
        """
        Ask a single question to Oracle
        
        Args:
            question (str): The question to ask
            
        Returns:
            dict: Structured response with answer, metadata, and performance info
        """
        if not self._initialized:
            return {
                "success": False,
                "error": f"Oracle initialization failed: {getattr(self, '_init_error', 'Unknown error')}",
                "answer": "Oracle not available",
                "question": question
            }
        
        try:
            # Ask Oracle (with silent output if needed)
            if self.silent:
                with open(os.devnull, 'w') as devnull:
                    with redirect_stdout(devnull), redirect_stderr(devnull):
                        result = self.client.ask_question(question)
            else:
                result = self.client.ask_question(question)
            
            # Log the query with source="bridge" (override the default "interactive" logging)
            # The ask_question method already logs, but we need to re-log with correct source
            self.client.query_logger.log_query(question, result, source="bridge")
            
            # Extract and structure the response for Claude Code
            token_breakdown = result.get('token_breakdown', {})
            analysis_metadata = result.get('analysis_metadata', {})
            
            return {
                "success": True,
                "question": question,
                "answer": result.get('content', ''),
                "sql_generated": result.get('sql_generated'),
                "row_count": analysis_metadata.get('results_count', 0),
                "tokens": {
                    "sql_tokens": token_breakdown.get('sql_generation', {}).get('total_tokens', 0),
                    "analysis_tokens": token_breakdown.get('results_analysis', {}).get('total_tokens', 0),
                    "total_tokens": token_breakdown.get('total_tokens', 0)
                },
                "cost": token_breakdown.get('combined_cost', 0),
                "execution_time": result.get('execution_time_seconds', 0),
                "cached": '(cached result)' in result.get('content', ''),
                "models_used": analysis_metadata.get('models_used', {}),
                "timestamp": result.get('timestamp')
            }
            
        except Exception as e:
            return {
                "success": False,
                "question": question,
                "error": str(e),
                "answer": f"Query failed: {e}",
                "cost": 0,
                "execution_time": 0
            }
    
    def multi_ask(self, questions):
        """
        Ask multiple questions in sequence, building context
        
        Args:
            questions (list): List of questions to ask
            
        Returns:
            list: List of structured responses
        """
        results = []
        total_cost = 0
        total_time = 0
        
        for question in questions:
            result = self.ask(question)
            results.append(result)
            
            if result.get('success', False):
                total_cost += result.get('cost', 0)
                total_time += result.get('execution_time', 0)
        
        # Add summary to the results
        summary = {
            "investigation_summary": {
                "total_questions": len(questions),
                "successful_queries": sum(1 for r in results if r.get('success', False)),
                "total_cost": total_cost,
                "total_time": total_time,
                "average_time_per_query": total_time / len(questions) if questions else 0
            }
        }
        
        return {
            "queries": results,
            "summary": summary
        }
    
    def investigate(self, topic, max_queries=5):
        """
        Autonomous investigation mode - explore a topic with multiple queries
        
        Args:
            topic (str): Topic to investigate
            max_queries (int): Maximum number of queries to make
            
        Returns:
            dict: Investigation results with all queries and summary
        """
        investigation_questions = [
            f"What can you tell me about {topic}?",
            f"Show me recent activity related to {topic}",
            f"What are the most significant patterns in {topic}?",
            f"Are there any unusual trends in {topic}?",
            f"What should I know about {topic} for trading decisions?"
        ]
        
        # Limit to max_queries
        questions_to_ask = investigation_questions[:max_queries]
        
        return self.multi_ask(questions_to_ask)
    
    def get_usage_stats(self):
        """Get current session usage statistics"""
        if not self._initialized:
            return {"error": "Oracle not initialized"}
        
        try:
            stats = self.client.get_usage_summary()
            return {
                "session_duration_minutes": stats.get('duration_minutes', 0),
                "total_queries": stats.get('interaction_count', 0),
                "total_tokens": stats.get('total_tokens', 0),
                "total_cost": stats.get('total_cost', 0),
                "current_model": stats.get('current_model', 'Unknown')
            }
        except Exception as e:
            return {"error": f"Failed to get stats: {e}"}


def main():
    """Command line interface for testing and direct access"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "No question provided",
            "usage": "python oracle_bridge.py [--raw] 'your question here'"
        }))
        sys.exit(1)
    
    # Raw mode is now default - check for analysis mode flag
    raw_mode = True  # Default to raw mode
    start_index = 1
    if sys.argv[1] == "--analyze":
        raw_mode = False  # Use full analysis with Sonnet
        start_index = 2
        if len(sys.argv) < 3:
            print(json.dumps({"error": "No question provided after --analyze flag"}))
            sys.exit(1)
    
    # Initialize bridge
    bridge = OracleBridge(silent=True)
    
    if sys.argv[start_index] == "--multi":
        # Multi-query mode: read questions from stdin
        try:
            questions = []
            for line in sys.stdin:
                question = line.strip()
                if question:  # Skip empty lines
                    questions.append(question)
            
            if not questions:
                print(json.dumps({"error": "No questions provided via stdin"}))
                sys.exit(1)
            
            results = bridge.multi_ask(questions)
            
        except KeyboardInterrupt:
            print(json.dumps({"error": "Interrupted by user"}))
            sys.exit(1)
    
    elif sys.argv[start_index] == "--investigate":
        # Investigation mode
        if len(sys.argv) < start_index + 2:
            print(json.dumps({"error": "Topic required for investigation"}))
            sys.exit(1)
        
        topic = " ".join(sys.argv[start_index + 1:])
        results = bridge.investigate(topic)
    
    elif sys.argv[start_index] == "--stats":
        # Usage statistics
        results = bridge.get_usage_stats()
    
    else:
        # Single question mode
        question = " ".join(sys.argv[start_index:])
        if raw_mode:
            results = bridge.raw_query(question)
        else:
            results = bridge.ask(question)
    
    # Output results as JSON
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()