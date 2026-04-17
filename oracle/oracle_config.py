#!/usr/bin/env python3
"""
Oracle Configuration Management (oracle_config.py)
-------------------------------------------------
Configuration loading and validation for Oracle CLI.
Handles paths, API keys, and database connections.

Features:
- Loads configuration from root config.json
- Validates required sections and paths
- Sets up logging infrastructure
- Provides clean configuration interface

Author: Ben (with assistance from Claude)
Date: 2025-07-10
"""

import os
import sys
import json
import logging
from pathlib import Path
from tools.timezone_utils import now_eastern, eastern_timestamp_string

class OracleConfig:
    """Configuration management for Oracle CLI"""
    
    def __init__(self, config_path=None):
        """Initialize configuration
        
        Args:
            config_path: Optional path to config.json. If None, searches for project root.
        """
        self.config_path = config_path or self._find_project_config()
        self.config = self._load_config()
        self.project_root = Path(self.config_path).parent
        
        # Set up logging immediately after config load
        self._setup_logging()
        
        logging.info("Oracle configuration initialized successfully")
        logging.info("Project root: {}".format(self.project_root))
    
    def _find_project_config(self):
        """Find config.json in the project root directory"""
        # Start from current file location (oracle directory)
        current_dir = Path(__file__).parent
        
        # Project root should be two levels up: oracle -> options_scanner -> root
        project_root = current_dir.parent
        
        # Look for config.json in the project root
        config_file = project_root / 'config.json'
        
        if config_file.exists():
            return str(config_file)
        
        # Fallback: search upward from current directory
        search_dir = current_dir
        for _ in range(5):  # Reasonable search limit
            config_candidate = search_dir / 'config.json'
            if config_candidate.exists():
                # Verify this looks like the right config by checking for known sections
                try:
                    with open(config_candidate, 'r', encoding='utf-8') as f:
                        test_config = json.load(f)
                    if 'tradier' in test_config or 'claude_api' in test_config:
                        return str(config_candidate)
                except (json.JSONDecodeError, IOError):
                    pass
            search_dir = search_dir.parent
        
        raise FileNotFoundError("Could not find config.json in project root or parent directories")
    
    def _load_config(self):
        """Load and validate configuration from JSON file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Validate required sections exist
            required_sections = ['claude_api']
            missing_sections = []
            
            for section in required_sections:
                if section not in config:
                    missing_sections.append(section)
            
            if missing_sections:
                raise ValueError("Missing required configuration sections: {}".format(', '.join(missing_sections)))
            
            # Validate Claude API configuration
            claude_config = config.get('claude_api', {})
            if 'api_key' not in claude_config:
                raise ValueError("Missing required field: claude_api.api_key")
            
            # Set defaults for Oracle-specific configuration if not present
            if 'oracle' not in config:
                config['oracle'] = {}
            
            oracle_defaults = {
                'max_query_timeout': 30,
                'max_result_rows': 10000,
                'log_level': 'INFO',
                'claude_model': claude_config.get('model', 'claude-sonnet-4-20250514'),
                'claude_max_tokens': claude_config.get('max_tokens', 4000)
            }
            
            # Apply defaults for missing Oracle settings
            for key, default_value in oracle_defaults.items():
                if key not in config['oracle']:
                    config['oracle'][key] = default_value
            
            return config
            
        except FileNotFoundError:
            raise FileNotFoundError("Configuration file not found: {}".format(self.config_path))
        except json.JSONDecodeError as e:
            raise ValueError("Invalid JSON in configuration file: {}".format(e))
        except Exception as e:
            raise RuntimeError("Failed to load configuration: {}".format(e))
    
    def _setup_logging(self):
        """Set up comprehensive logging infrastructure"""
        # Create logs directory
        logs_dir = self.get_logs_directory()
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Get current date for log files
        date_str = now_eastern().strftime('%Y-%m-%d')
        
        # Set up log level
        log_level = getattr(logging, self.config['oracle'].get('log_level', 'INFO').upper())
        
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        error_formatter = logging.Formatter(
            '%(asctime)s - ERROR - %(name)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Set up main log file (oracle_config)
        config_log_file = logs_dir / "oracle_config_{}.log".format(date_str)
        config_handler = logging.FileHandler(config_log_file, mode='a', encoding='utf-8')
        config_handler.setLevel(log_level)
        config_handler.setFormatter(detailed_formatter)
        
        # Set up database log file (will be used by database module)
        database_log_file = logs_dir / "database_{}.log".format(date_str)
        
        # Set up error-only log file
        error_log_file = logs_dir / "errors_{}.log".format(date_str)
        error_handler = logging.FileHandler(error_log_file, mode='a', encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(error_formatter)
        
        # Set up console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        # Configure root logger
        root_logger.setLevel(log_level)
        root_logger.addHandler(config_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(console_handler)
        
        # Store database log file path for other modules
        self._database_log_file = database_log_file
        
        logging.info("Logging infrastructure initialized")
        logging.info("Config log: {}".format(config_log_file))
        logging.info("Database log: {}".format(database_log_file))
        logging.info("Error log: {}".format(error_log_file))
    
    def get_database_path(self):
        """Get path to datalake.db"""
        db_path = self.project_root / 'data' / 'datalake.db'
        return str(db_path)
    
    def get_logs_directory(self):
        """Get logs directory path"""
        return Path(__file__).parent / 'oracle_logs'
    
    def get_cache_directory(self):
        """Get cache directory path"""
        return Path(__file__).parent / 'cache'
    
    def get_database_log_file(self):
        """Get database log file path for use by database module"""
        return str(self._database_log_file)
    
    def get_default_model(self):
        """Get default Claude model, preferring Sonnet for quality
        
        Returns:
            str: Model identifier, defaults to Sonnet
        """
        # Check if explicitly set in config
        oracle_model = self.config.get('oracle', {}).get('default_model')
        if oracle_model:
            return oracle_model
        
        # Otherwise default to Sonnet for quality
        return 'claude-3-5-sonnet-20241022'
    
    @property
    def claude_api_key(self):
        """Get Claude API key"""
        return self.config['claude_api']['api_key']
    
    @property
    def claude_model(self):
        """Get Claude model name"""
        return self.config['oracle']['claude_model']
    
    @property
    def claude_max_tokens(self):
        """Get Claude max tokens"""
        return self.config['oracle']['claude_max_tokens']
    
    @property
    def max_query_timeout(self):
        """Get maximum query timeout in seconds"""
        return self.config['oracle']['max_query_timeout']
    
    @property
    def max_result_rows(self):
        """Get maximum result rows limit"""
        return self.config['oracle']['max_result_rows']
    
    def validate_environment(self):
        """Validate that the environment is properly set up"""
        issues = []
        
        # Check database file exists
        db_path = Path(self.get_database_path())
        if not db_path.exists():
            issues.append("Database file not found: {}".format(db_path))
        elif not db_path.is_file():
            issues.append("Database path is not a file: {}".format(db_path))
        
        # Check data directory exists
        data_dir = db_path.parent
        if not data_dir.exists():
            issues.append("Data directory not found: {}".format(data_dir))
        
        # Check logs directory is writable
        logs_dir = self.get_logs_directory()
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            test_file = logs_dir / 'test_write.tmp'
            test_file.write_text('test')
            test_file.unlink()
        except Exception as e:
            issues.append("Logs directory not writable: {}".format(e))
        
        # Check cache directory can be created
        cache_dir = self.get_cache_directory()
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            issues.append("Cannot create cache directory: {}".format(e))
        
        # Check Claude API key format
        api_key = self.claude_api_key
        if not api_key.startswith('sk-ant-'):
            issues.append("Claude API key format appears invalid (should start with 'sk-ant-')")
        
        if issues:
            error_msg = "Environment validation failed:\n  - {}".format('\n  - '.join(issues))
            logging.error(error_msg)
            raise RuntimeError(error_msg)
        
        logging.info("Environment validation passed")
        return True
    
    def get_config_summary(self):
        """Get a summary of the current configuration (safe for logging)"""
        summary = {
            'config_path': self.config_path,
            'project_root': str(self.project_root),
            'database_path': self.get_database_path(),
            'logs_directory': str(self.get_logs_directory()),
            'cache_directory': str(self.get_cache_directory()),
            'claude_model': self.claude_model,
            'claude_max_tokens': self.claude_max_tokens,
            'max_query_timeout': self.max_query_timeout,
            'max_result_rows': self.max_result_rows,
            'claude_api_key': '{}...{}'.format(self.claude_api_key[:8], self.claude_api_key[-4:]) if self.claude_api_key else 'NOT SET'
        }
        return summary


class SessionLogger:
    """Session-based conversation logging for Oracle CLI"""
    
    def __init__(self, config):
        """Initialize session logger
        
        Args:
            config: OracleConfig instance
        """
        self.config = config
        self.session_id = None
        self.session_file = None
        self.session_data = None
        self.session_start_time = None
        
        # Create sessions directory
        self.sessions_dir = self.config.get_logs_directory() / 'sessions'
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        logging.info("SessionLogger initialized")
    
    def start_session(self, session_logging_enabled=True):
        """Start a new session with logging
        
        Args:
            session_logging_enabled: Whether to enable session logging
        """
        if not session_logging_enabled:
            logging.info("Session logging disabled")
            return
        
        # Generate session ID using EST timestamp
        timestamp = now_eastern().strftime("%Y%m%d_%H%M%S")
        self.session_id = "oracle_session_{}".format(timestamp)
        self.session_start_time = now_eastern()
        
        # Create session file path
        self.session_file = self.sessions_dir / "{}.json".format(self.session_id)
        
        # Initialize session data structure
        self.session_data = {
            "session_id": self.session_id,
            "session_start": now_eastern().isoformat(),
            "session_end": None,
            "queries": [],
            "session_summary": {
                "total_queries": 0,
                "total_cost": 0.0,
                "session_duration_minutes": 0.0,
                "primary_topics": [],
                "models_used": set(),
                "errors_count": 0
            }
        }
        
        # Write initial session file
        self._write_session_file()
        
        logging.info("Session started: {} at {}".format(self.session_id, self.session_file))
    
    def log_query(self, user_question, response_data):
        """Log a complete query interaction
        
        Args:
            user_question: User's input question
            response_data: Complete response from oracle_vanna
        """
        if not self.session_data:
            return  # Session logging disabled
        
        try:
            # Extract data from response
            success = response_data.get('success', False)
            sql_generated = response_data.get('sql_generated', '')
            raw_results = response_data.get('raw_results', [])
            analysis_content = response_data.get('content', '')
            execution_time = response_data.get('execution_time_seconds', 0.0)
            token_breakdown = response_data.get('token_breakdown', {})
            error_info = response_data.get('error', '') if not success else None
            
            # Process raw results with smart truncation
            processed_results = self._process_raw_results(raw_results)
            
            # Extract models used from token breakdown
            models_used = self._extract_models_used(token_breakdown)
            
            # Create query log entry
            query_entry = {
                "timestamp": now_eastern().isoformat(),
                "user_question": user_question,
                "success": success,
                "sql_generated": sql_generated,
                "raw_results": processed_results,
                "analysis_response": analysis_content,
                "execution_time_seconds": execution_time,
                "token_breakdown": token_breakdown,
                "models_used": models_used,
                "error_info": error_info
            }
            
            # Add to session data
            self.session_data["queries"].append(query_entry)
            
            # Update session summary
            self._update_session_summary(query_entry, models_used)
            
            # Write updated session file
            self._write_session_file()
            
            logging.debug("Query logged: {} chars response, {} execution time".format(
                len(analysis_content), execution_time))
            
        except Exception as e:
            logging.error("Failed to log query: {}".format(e))
            # Don't break Oracle if logging fails
    
    def end_session(self):
        """End the current session and finalize the log"""
        if not self.session_data:
            return
        
        try:
            # Calculate final session duration
            if self.session_start_time:
                duration = (now_eastern() - self.session_start_time).total_seconds() / 60
                self.session_data["session_summary"]["session_duration_minutes"] = round(duration, 2)
            
            # Set session end time
            self.session_data["session_end"] = now_eastern().isoformat()
            
            # Convert sets to lists for JSON serialization
            if "models_used" in self.session_data["session_summary"]:
                self.session_data["session_summary"]["models_used"] = list(
                    self.session_data["session_summary"]["models_used"]
                )
            
            # Final write
            self._write_session_file()
            
            logging.info("Session ended: {} - {} queries, {:.2f} minutes, ${:.4f} total cost".format(
                self.session_id,
                self.session_data["session_summary"]["total_queries"],
                self.session_data["session_summary"]["session_duration_minutes"],
                self.session_data["session_summary"]["total_cost"]
            ))
            
        except Exception as e:
            logging.error("Failed to end session: {}".format(e))
    
    def _process_raw_results(self, raw_results):
        """Process raw results with smart truncation and format normalization
        
        Args:
            raw_results: Raw results in various formats
            
        Returns:
            dict: Processed results with truncation info
        """
        # Normalize results format first
        normalized_results = self._normalize_results(raw_results)
        
        if not normalized_results:
            return {"total_count": 0, "data": []}
        
        result_count = len(normalized_results)
        
        # Smart truncation threshold
        if result_count <= 20:
            # Store everything for small result sets
            return {
                "total_count": result_count,
                "data": normalized_results,
                "truncated": False
            }
        else:
            # Store sample for large result sets
            return {
                "total_count": result_count,
                "sample_data": normalized_results[:5],  # First 5 rows as sample
                "truncated": True,
                "truncation_note": "Showing first 5 of {} results - full data analyzed by Claude".format(result_count)
            }

    def _normalize_results(self, raw_results):
        """Ensure raw_results is a list of dictionaries for consistent processing
        
        Args:
            raw_results: Raw results in various formats
            
        Returns:
            list: Normalized list of dictionaries
        """
        if not raw_results:
            return []
        
        # Already correct format - list of dictionaries
        if isinstance(raw_results, list) and all(isinstance(item, dict) for item in raw_results):
            return raw_results
        
        # Handle other formats gracefully
        if isinstance(raw_results, list) and raw_results:
            first_item = raw_results[0]
            
            # Handle list of tuples or lists
            if isinstance(first_item, (tuple, list)):
                return [{"column_{}".format(i): val for i, val in enumerate(item)} for item in raw_results]
            
            # Handle list of single values
            if not isinstance(first_item, dict):
                return [{"value": item} for item in raw_results]
        
        # Handle single dictionary
        if isinstance(raw_results, dict):
            return [raw_results]
        
        # Fallback for any other format
        logging.warning("Unexpected raw_results format: {}, converting to string".format(type(raw_results)))
        return [{"raw_data": str(raw_results)}]
    
    def _extract_models_used(self, token_breakdown):
        """Extract models used from token breakdown
        
        Args:
            token_breakdown: Token usage information
            
        Returns:
            list: Models used in this query
        """
        models = []
        
        if isinstance(token_breakdown, dict):
            # Handle two-model breakdown (SQL + Analysis)
            if 'sql_generation' in token_breakdown:
                sql_model = token_breakdown['sql_generation'].get('model', '')
                if sql_model:
                    # Convert to friendly name
                    model_name = 'haiku' if 'haiku' in sql_model.lower() else 'sonnet'
                    models.append("sql_gen:{}".format(model_name))
            
            if 'results_analysis' in token_breakdown:
                analysis_model = token_breakdown['results_analysis'].get('model', '')
                if analysis_model:
                    model_name = 'haiku' if 'haiku' in analysis_model.lower() else 'sonnet'
                    models.append("analysis:{}".format(model_name))
        
        return models
    
    def _update_session_summary(self, query_entry, models_used):
        """Update session summary with query data
        
        Args:
            query_entry: The query entry that was just added
            models_used: List of models used for this query
        """
        summary = self.session_data["session_summary"]
        
        # Update counters
        summary["total_queries"] += 1
        
        if not query_entry["success"]:
            summary["errors_count"] += 1
        
        # Update cost
        token_breakdown = query_entry.get("token_breakdown", {})
        if isinstance(token_breakdown, dict) and "combined_cost" in token_breakdown:
            summary["total_cost"] += token_breakdown["combined_cost"]
        
        # Track models used
        if not isinstance(summary["models_used"], set):
            summary["models_used"] = set()
        
        for model in models_used:
            summary["models_used"].add(model)
        
        # Extract topics using KLMN800 whitelist
        question = query_entry.get("user_question", "")
        symbols = self._extract_valid_symbols(question)
        for symbol in symbols[:3]:  # Limit to first 3 symbols found
            if symbol not in summary["primary_topics"]:
                summary["primary_topics"].append(symbol)
    
    def _extract_valid_symbols(self, question):
        """Extract valid stock symbols from question using KLMN800 whitelist
        
        Args:
            question: User's question text
            
        Returns:
            list: Valid symbols found in the question
        """
        try:
            # Import KLMN800 symbols via DB-backed query
            from core.symbols_klmn800 import get_specialty_list

            # Convert to set for fast lookup
            valid_symbols = set(get_specialty_list('klmn_800'))
            
            # Find potential symbols (3-5 letter uppercase words)
            import re
            question_upper = question.upper()
            potential_symbols = re.findall(r'\b[A-Z]{3,5}\b', question_upper)
            
            # Filter against whitelist
            found_symbols = [symbol for symbol in potential_symbols if symbol in valid_symbols]
            
            return found_symbols
            
        except Exception as e:
            logging.warning("Failed to extract symbols using whitelist: {}".format(e))
            # Fallback to no topic extraction
            return []
            
    def _write_session_file(self):
        """Write session data to file with error handling"""
        if not self.session_file or not self.session_data:
            return
        
        try:
            # Create a copy for JSON serialization
            session_copy = json.loads(json.dumps(self.session_data, default=str))
            
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_copy, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logging.error("Failed to write session file {}: {}".format(self.session_file, e))
    
    def get_session_stats(self):
        """Get current session statistics
        
        Returns:
            dict: Session statistics or None if no active session
        """
        if not self.session_data:
            return None
        
        return {
            "session_id": self.session_id,
            "queries_count": len(self.session_data["queries"]),
            "total_cost": self.session_data["session_summary"]["total_cost"],
            "duration_minutes": self.session_data["session_summary"]["session_duration_minutes"],
            "models_used": list(self.session_data["session_summary"]["models_used"]) if isinstance(self.session_data["session_summary"]["models_used"], set) else self.session_data["session_summary"]["models_used"]
        }

# Create a singleton config instance for the application
config = OracleConfig()

# Quick validation if run directly
if __name__ == "__main__":
    print("Oracle Configuration Test")
    print("=" * 50)
    
    try:
        config = OracleConfig()
        print("✅ Configuration loaded successfully")
        
        summary = config.get_config_summary()
        for key, value in summary.items():
            print("  {}: {}".format(key, value))
        
        print("\n✅ Environment validation...")
        config.validate_environment()
        print("✅ All validation checks passed")
        
    except Exception as e:
        print("❌ Configuration test failed: {}".format(e))
        sys.exit(1)
