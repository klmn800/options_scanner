#!/usr/bin/env python3
"""
Oracle Vanna Integration (oracle_vanna.py)
------------------------------------------
Complete replacement for Oracle's function-based system using Vanna's RAG approach.
Integrates seamlessly with existing Oracle infrastructure while providing superior
natural language to SQL conversion capabilities.

Features:
- Vanna RAG engine with Claude integration
- Full Oracle infrastructure compatibility
- Cost tracking and session management
- Automatic schema training
- Options trading domain expertise
- Identical CLI experience to original Oracle

Author: Ben (with assistance from Claude)
Date: 2025-07-16
"""

import json
import logging
import time
import sqlite3
import hashlib
import anthropic
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

# Vanna imports
try:
    from vanna.anthropic import Anthropic_Chat
    from vanna.faiss.faiss import FAISS
except ImportError as e:
    print("❌ Vanna not installed. Run: pip install vanna[anthropic,faiss-cpu]")
    raise e

# Oracle infrastructure imports
from .oracle_config import OracleConfig
from .oracle_data_access import DatabaseConnection
from tools.timezone_utils import now_eastern, eastern_isoformat

# Set up logging
vanna_logger = logging.getLogger('oracle.vanna')

class QueryLogger:
    """
    Comprehensive query logging for Oracle interactions
    Logs all questions, SQL, answers, and performance metrics for debugging and review
    """
    
    def __init__(self, log_dir="oracle/oracle_logs/queries"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def log_query(self, question, response_data, source="interactive"):
        """
        Log a complete query interaction
        
        Args:
            question: The user's question
            response_data: Full response from Oracle
            source: 'interactive' for oracle_main.py or 'bridge' for oracle_bridge.py
        """
        try:
            # Determine log file (daily rotation)
            today = now_eastern().strftime('%Y-%m-%d')
            log_file = self.log_dir / f"oracle_queries_{today}.json"
            
            # Extract data from response
            token_breakdown = response_data.get('token_breakdown', {})
            analysis_metadata = response_data.get('analysis_metadata', {})
            
            log_entry = {
                "timestamp": eastern_isoformat(),
                "source": source,
                "question": question,
                "sql_generated": response_data.get('sql_generated'),
                "answer": response_data.get('content', ''),
                "success": response_data.get('success', False),
                "row_count": analysis_metadata.get('results_count', 0),
                "tokens": {
                    "sql_generation": token_breakdown.get('sql_generation', {}),
                    "results_analysis": token_breakdown.get('results_analysis', {}),
                    "total_tokens": token_breakdown.get('total_tokens', 0)
                },
                "cost": token_breakdown.get('combined_cost', 0),
                "execution_time": response_data.get('execution_time_seconds', 0),
                "cached": '(cached result)' in response_data.get('content', ''),
                "models_used": analysis_metadata.get('models_used', {}),
                "context_resolved": analysis_metadata.get('context_resolved', False),
                "original_question": analysis_metadata.get('original_question')
            }
            
            # Add error info if query failed
            if not log_entry["success"]:
                log_entry["error"] = response_data.get('error', 'Unknown error')
            
            # Read existing log or create new list
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            else:
                log_data = {"queries": []}
            
            # Add new entry
            log_data["queries"].append(log_entry)
            
            # Update summary statistics
            if "summary" not in log_data:
                log_data["summary"] = {}
            
            queries = log_data["queries"]
            successful_queries = [q for q in queries if q.get("success", False)]
            
            log_data["summary"] = {
                "date": today,
                "total_queries": len(queries),
                "successful_queries": len(successful_queries),
                "total_cost": sum(q.get("cost", 0) for q in successful_queries),
                "total_tokens": sum(q.get("tokens", {}).get("total_tokens", 0) for q in successful_queries),
                "avg_execution_time": sum(q.get("execution_time", 0) for q in successful_queries) / len(successful_queries) if successful_queries else 0,
                "sources": {
                    "interactive": len([q for q in queries if q.get("source") == "interactive"]),
                    "bridge": len([q for q in queries if q.get("source") == "bridge"])
                },
                "cached_responses": len([q for q in queries if q.get("cached", False)])
            }
            
            # Write updated log
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            vanna_logger.error(f"Failed to log query: {e}")

class ConversationContext:
    """
    Lightweight conversation context tracking for pronoun resolution
    and entity persistence within a single Oracle session.
    """
    
    def __init__(self):
        self.current_symbols = []  # Recently mentioned symbols
        self.recent_timeframes = []  # "last week", "today", etc.
        self.last_query_type = None  # "alerts", "volume", "analysis"
        self.last_entities = {}  # General entity storage
        self.context_window = 5  # Keep last 5 interactions
        
    def extract_symbols_from_text(self, text: str) -> List[str]:
        """Extract stock symbols from text using KLMN 800 universe validation"""
        import re
        
        # Import your proven KLMN 800 symbol universe
        try:
            from core.symbols_klmn800 import KLMN_800_SYMBOLS
            valid_symbols = set(KLMN_800_SYMBOLS)
        except ImportError:
            # Fallback if import fails
            vanna_logger.warning("Could not import KLMN_800_SYMBOLS, using basic validation")
            valid_symbols = set()
        
        # Extract potential symbols (2-5 uppercase letters)
        symbol_pattern = r'\b[A-Z]{2,5}\b'
        potential_symbols = re.findall(symbol_pattern, text.upper())
        
        # Filter using KLMN 800 universe only
        symbols = []
        for symbol in potential_symbols:
            if symbol in valid_symbols:
                symbols.append(symbol)
        
        return list(set(symbols))  # Remove duplicates
    
    def extract_timeframes_from_text(self, text: str) -> List[str]:
        """Extract timeframe references from text"""
        import re
        
        timeframe_patterns = [
            r'today', r'yesterday', r'this week', r'last week', r'this month',
            r'last month', r'this quarter', r'last quarter', r'this year',
            r'\d+ days?', r'\d+ weeks?', r'\d+ months?', r'recent', r'latest'
        ]
        
        timeframes = []
        text_lower = text.lower()
        
        for pattern in timeframe_patterns:
            matches = re.findall(pattern, text_lower)
            timeframes.extend(matches)
        
        return timeframes
    
    def update_context(self, question: str, response_data: Dict[str, Any]):
        """Update context based on question and response"""
        try:
            # Extract symbols ONLY from the user's question, not from SQL
            question_symbols = self.extract_symbols_from_text(question)
            
            # Don't extract from SQL - it contains keywords like AS, IS, etc.
            # that would confuse the context
            
            # Update current symbols (keep most recent at front)
            for symbol in question_symbols:
                if symbol in self.current_symbols:
                    self.current_symbols.remove(symbol)
                self.current_symbols.insert(0, symbol)
            
            # Trim to context window
            self.current_symbols = self.current_symbols[:self.context_window]
            
            # Extract timeframes from question only
            timeframes = self.extract_timeframes_from_text(question)
            for timeframe in timeframes:
                if timeframe in self.recent_timeframes:
                    self.recent_timeframes.remove(timeframe)
                self.recent_timeframes.insert(0, timeframe)
            
            self.recent_timeframes = self.recent_timeframes[:self.context_window]
            
            # Determine query type from question
            question_lower = question.lower()
            if any(word in question_lower for word in ['alert', 'unusual', 'flow']):
                self.last_query_type = 'alerts'
            elif any(word in question_lower for word in ['volume', 'trading']):
                self.last_query_type = 'volume'
            elif any(word in question_lower for word in ['price', 'performance', 'return']):
                self.last_query_type = 'performance'
            elif any(word in question_lower for word in ['call', 'put', 'option']):
                self.last_query_type = 'options'
            else:
                self.last_query_type = 'general'
                
            vanna_logger.debug("Context updated - Symbols: {}, Timeframes: {}, Type: {}".format(
                self.current_symbols[:3], self.recent_timeframes[:2], self.last_query_type))
                
        except Exception as e:
            vanna_logger.warning("Context update failed: {}".format(e))
    
    def resolve_references(self, question: str) -> str:
        """Resolve pronouns and references in the question"""
        import re
        try:
            resolved_question = question
            question_lower = question.lower()
            
            # Pronoun resolution patterns
            replacements = []
            
            # "it" resolution - use most recent symbol
            if re.search(r'\bit\b', question_lower):
                if self.current_symbols:
                    target_symbol = self.current_symbols[0]
                    # Replace "it" with symbol, preserving case
                    resolved_question = re.sub(r'\bit\b', target_symbol, resolved_question, flags=re.IGNORECASE)
                    replacements.append("'it' -> '{}'".format(target_symbol))
            
            # "this/that symbol" resolution
            symbol_refs = re.findall(r'\b(this|that)\s+symbol\b', question_lower)
            if symbol_refs and self.current_symbols:
                target_symbol = self.current_symbols[0]
                resolved_question = re.sub(r'\b(this|that)\s+symbol\b', target_symbol, 
                                         resolved_question, flags=re.IGNORECASE)
                replacements.append("'this/that symbol' -> '{}'".format(target_symbol))
            
            # "these/those symbols" resolution (multiple symbols)
            multi_refs = re.findall(r'\b(these|those)\s+symbols?\b', question_lower)
            if multi_refs and len(self.current_symbols) > 1:
                symbol_list = ", ".join(self.current_symbols[:3])
                resolved_question = re.sub(r'\b(these|those)\s+symbols?\b', symbol_list,
                                         resolved_question, flags=re.IGNORECASE)
                replacements.append("'these/those symbols' -> '{}'".format(symbol_list))
            
            # "the previous/last query" type references
            if any(phrase in question_lower for phrase in ['previous', 'last query', 'earlier']):
                if self.last_query_type and self.current_symbols:
                    context_hint = " for {} related to {}".format(self.last_query_type, self.current_symbols[0])
                    resolved_question += context_hint
                    replacements.append("added context: {}".format(context_hint))
            
            # Log resolution if any changes made
            if replacements:
                vanna_logger.info("Reference resolution: {}".format(", ".join(replacements)))
            
            if replacements:
                vanna_logger.info("Reference resolution: {}".format(", ".join(replacements)))
            else:
                vanna_logger.debug("No references found to resolve in: '{}'".format(question))

            return resolved_question

            return resolved_question
            
        except Exception as e:
            vanna_logger.warning("Reference resolution failed: {}".format(e))
            return question  # Return original if resolution fails
    
    def get_context_summary(self) -> str:
        """Get current context for debugging/logging"""
        return "Symbols: {}, Timeframes: {}, Type: {}".format(
            self.current_symbols[:3], self.recent_timeframes[:2], self.last_query_type)
    
    def clear_context(self):
        """Clear all context (for session reset)"""
        self.current_symbols = []
        self.recent_timeframes = []
        self.last_query_type = None
        self.last_entities = {}
        vanna_logger.info("Conversation context cleared")
        
class TokenUsageTracker:
    """
    Enhanced token usage and cost tracking - extracted from claude_api.py
    Provides detailed cost monitoring for Vanna operations.
    """
    
    def __init__(self, debug_mode=False):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        self.session_start = now_eastern()
        self.debug_mode = debug_mode
        
        # Enhanced tracking for cost monitoring
        self.query_costs = {}  # Track cost per query type
        self.hourly_costs = {}   # Track cost trends by hour
        self.cost_alerts = []    # Track when costs exceed thresholds
        self.daily_budget = 5.00  # Default $5 daily budget
        
        # Claude pricing (per million tokens) as of 2025-07-16
        self.pricing = {
            "claude-3-5-haiku-20241022": {"input": 0.25, "output": 1.25, "name": "Haiku"},
            "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00, "name": "Sonnet"},
            "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "name": "Sonnet 4"}
        }
        
        # Cost thresholds for monitoring
        self.cost_thresholds = {
            "query_warning": 0.02,       # Warn if single query > $0.02
            "hourly_warning": 1.00,      # Warn if hourly spend > $1.00
            "daily_warning": 4.00,       # Warn if approaching daily budget
            "session_limit": 10.00       # Hard limit for session spending
        }
    
    def add_usage(self, model: str, input_tokens: int, output_tokens: int, 
                  query_type: str = None, execution_time: float = 0.0):
        """Enhanced usage tracking with query-level cost monitoring"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1
        
        # Calculate cost for this call
        call_cost = self.calculate_cost(model, input_tokens, output_tokens)
        current_hour = now_eastern().strftime('%Y-%m-%d %H:00')
        
        # Track query-level costs
        if query_type:
            if query_type not in self.query_costs:
                self.query_costs[query_type] = {
                    "total_cost": 0.0,
                    "call_count": 0,
                    "total_tokens": 0,
                    "avg_cost": 0.0,
                    "max_cost": 0.0,
                    "total_execution_time": 0.0
                }
            
            query_stats = self.query_costs[query_type]
            query_stats["total_cost"] += call_cost
            query_stats["call_count"] += 1
            query_stats["total_tokens"] += (input_tokens + output_tokens)
            query_stats["avg_cost"] = query_stats["total_cost"] / query_stats["call_count"]
            query_stats["max_cost"] = max(query_stats["max_cost"], call_cost)
            query_stats["total_execution_time"] += execution_time
        
        # Track hourly costs for trend analysis
        if current_hour not in self.hourly_costs:
            self.hourly_costs[current_hour] = {"cost": 0.0, "calls": 0, "tokens": 0}
        
        hourly_stats = self.hourly_costs[current_hour]
        hourly_stats["cost"] += call_cost
        hourly_stats["calls"] += 1
        hourly_stats["tokens"] += (input_tokens + output_tokens)
        
        # Check cost thresholds and generate alerts
        self._check_cost_thresholds(call_cost, query_type, current_hour)
        
        # Enhanced logging with cost awareness (debug mode only)
        if self.debug_mode:
            cost_level = "HIGH" if call_cost >= 0.02 else "MED" if call_cost >= 0.005 else "LOW"
            vanna_logger.info(f"{cost_level} COST: {model} - {input_tokens}in/{output_tokens}out tokens - ${call_cost:.4f} - Query: {query_type or 'direct'}")
    
    def _check_cost_thresholds(self, call_cost: float, query_type: str, current_hour: str):
        """Check if costs exceed configured thresholds and generate alerts"""
        
        # Single query cost alert
        if call_cost >= self.cost_thresholds["query_warning"]:
            alert = {
                "type": "high_query_cost",
                "query_type": query_type,
                "cost": call_cost,
                "threshold": self.cost_thresholds["query_warning"],
                "timestamp": eastern_isoformat(),
                "message": f"Query '{query_type}' cost ${call_cost:.4f} exceeds warning threshold ${self.cost_thresholds['query_warning']:.2f}"
            }
            self.cost_alerts.append(alert)
            vanna_logger.warning(alert["message"])
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a specific API call"""
        if model not in self.pricing:
            model = "claude-3-5-sonnet-20241022"  # Default to Sonnet
        
        prices = self.pricing[model]
        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]
        return input_cost + output_cost
    
    def get_session_total_cost(self) -> float:
        """Calculate total cost for current session"""
        total_cost = 0.0
        for query_stats in self.query_costs.values():
            total_cost += query_stats["total_cost"]
        return total_cost
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of token usage and costs for this session"""
        session_duration = (now_eastern() - self.session_start).total_seconds() / 60
        total_cost = self.get_session_total_cost()
        
        return {
            "session_duration_minutes": round(session_duration, 1),
            "total_api_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_total_cost": round(total_cost, 4),
            "avg_tokens_per_call": round((self.total_input_tokens + self.total_output_tokens) / max(self.total_calls, 1), 1),
            "formatted_cost": f"${total_cost:.4f}"
        }

class OracleVannaClient:
    """
    Main Oracle-Vanna integration class
    Combines Vanna's RAG capabilities with Oracle's proven infrastructure

    Two-Model Strategy:
    - Haiku (via Vanna): Fast, cost-efficient SQL generation with domain knowledge
    - Sonnet (direct): Superior analytical reasoning for intelligent insights
    """
    
    def __init__(self, config: OracleConfig, model_override: str = None, debug_mode: bool = False):
        """Initialize Oracle-Vanna client with existing Oracle configuration"""
        self.config = config
        self.model_override = model_override
        self.debug_mode = debug_mode
        self.usage_tracker = TokenUsageTracker(debug_mode=debug_mode)
        self.conversation_history = []
        self.conversation_context = ConversationContext()
        self.vanna_instance = None
        self.db_connection = None
        
        # Suppress HTTP request logging unless in debug mode
        if not debug_mode:
            import logging
            logging.getLogger("httpx").setLevel(logging.WARNING)
        
        # Query result cache with intelligent TTL
        self.query_cache = {}
        self.cache_ttl_default = 3600  # 1 hour default
        self.cache_ttl_historical = 86400  # 24 hours for historical queries
        self.cache_ttl_failed = 300  # 5 minutes for failed queries
        
        # Initialize query logger for comprehensive logging
        self.query_logger = QueryLogger()
        
        # Load Vanna-specific settings from config
        self.vanna_config = self._load_vanna_settings()
        
        # Initialize components
        self._initialize_vanna()
        self._setup_database_connection()
        
        vanna_logger.info("Oracle-Vanna client initialized successfully")
    
    def _initialize_vanna(self):
        """Initialize Vanna with Claude and FAISS"""
        try:
            class OracleVanna(Anthropic_Chat, FAISS):
                def __init__(self, config=None):
                    Anthropic_Chat.__init__(self, config=config)
                    FAISS.__init__(self, config=config)
                    
                    # Store reference to Oracle's usage tracker and debug mode
                    self._oracle_tracker = None
                    self._debug_mode = False
                
                def set_oracle_tracker(self, tracker):
                    """Set reference to Oracle's cost tracking system"""
                    self._oracle_tracker = tracker
                
                def set_debug_mode(self, debug_mode):
                    """Set debug mode to control verbose output"""
                    self._debug_mode = debug_mode
                
                def generate_sql(self, question: str, **kwargs):
                    """Override to suppress verbose SQL generation output unless in debug mode"""
                    if not self._debug_mode:
                        # Suppress all Vanna output including progress bars
                        import sys
                        import os
                        from contextlib import redirect_stdout, redirect_stderr
                        
                        # Also temporarily disable tqdm progress bars
                        import tqdm
                        original_tqdm = tqdm.tqdm
                        tqdm.tqdm = lambda *args, **kwargs: args[0] if args else []
                        
                        try:
                            with open(os.devnull, 'w') as devnull:
                                with redirect_stdout(devnull), redirect_stderr(devnull):
                                    result = super().generate_sql(question, **kwargs)
                        finally:
                            tqdm.tqdm = original_tqdm
                        return result
                    else:
                        return super().generate_sql(question, **kwargs)
                
                def submit_prompt(self, prompt, **kwargs):
                    """Override to capture exact token usage from Anthropic response"""
                    if prompt is None:
                        raise Exception("Prompt is None")

                    if len(prompt) == 0:
                        raise Exception("Prompt is empty")

                    start_time = time.time()

                    # Prepare the prompt for Anthropic (same logic as parent)
                    system_message = ''
                    no_system_prompt = []
                    for prompt_message in prompt:
                        role = prompt_message['role']
                        if role == 'system':
                            system_message = prompt_message['content']
                        else:
                            no_system_prompt.append({"role": role, "content": prompt_message['content']})

                    # Make the API call and capture the FULL response
                    full_response = self.client.messages.create(
                        model=self.config["model"],
                        messages=no_system_prompt,
                        system=system_message,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )

                    # Extract exact token usage
                    if self._oracle_tracker and hasattr(full_response, 'usage'):
                        input_tokens = full_response.usage.input_tokens
                        output_tokens = full_response.usage.output_tokens
                        execution_time = time.time() - start_time
                        
                        # Classify query type
                        prompt_text = system_message + ' '.join([msg.get('content', '') for msg in no_system_prompt])
                        query_type = self._classify_query_type(prompt_text)
                        
                        # Track exact usage
                        self._oracle_tracker.add_usage(
                            model=self.config["model"],
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            query_type=query_type,
                            execution_time=execution_time
                        )
                        
                        # Store the exact token data for this call
                        self._last_call_tokens = {
                            'input_tokens': input_tokens,
                            'output_tokens': output_tokens,
                            'total_tokens': input_tokens + output_tokens,
                            'cost': self._oracle_tracker.calculate_cost(self.config["model"], input_tokens, output_tokens),
                            'model': self.config["model"]
                        }

                    # Return just the text content (maintaining Vanna compatibility)
                    return full_response.content[0].text
                
                def _classify_query_type(self, prompt: str) -> str:
                    """Classify the type of query for cost tracking"""
                    prompt_lower = prompt.lower()
                    
                    if "generate sql" in prompt_lower or "create query" in prompt_lower:
                        return "sql_generation"
                    elif "explain" in prompt_lower or "documentation" in prompt_lower:
                        return "explanation"
                    elif "train" in prompt_lower or "learn" in prompt_lower:
                        return "training"
                    else:
                        return "general_query"
            
            # Create Vanna instance with Claude configuration and Vanna-specific settings
            effective_model = self._get_effective_model()
            vanna_config = {
                'api_key': self.config.claude_api_key,
                'model': effective_model,
                'max_tokens': self.config.claude_max_tokens,  # ← Use Oracle's config
                'path': self.vanna_config.get('vector_store_path', './oracle/vanna_storage'),
                'embedding_model': self.vanna_config.get('embedding_model', 'all-MiniLM-L6-v2'),
                'n_results': 10,  # Number of similar examples to retrieve
                'embedding_dim': 384  # Standard for all-MiniLM-L6-v2
            }
            
            # Ensure storage directory exists
            storage_path = Path(vanna_config['path'])
            storage_path.mkdir(parents=True, exist_ok=True)
            
            self.vanna_instance = OracleVanna(config=vanna_config)
            self.vanna_instance.set_oracle_tracker(self.usage_tracker)
            self.vanna_instance.set_debug_mode(self.debug_mode)
            
            vanna_logger.info(f"Vanna initialized with Claude + FAISS vector store")
            vanna_logger.info(f"Model: {effective_model}")
            vanna_logger.info(f"Storage: {vanna_config['path']}")
            vanna_logger.info(f"Embedding model: {vanna_config['embedding_model']}")
            
        except Exception as e:
            vanna_logger.error(f"Failed to initialize Vanna: {e}")
            raise RuntimeError(f"Vanna initialization failed: {e}")
    
    def _setup_database_connection(self):
        """Set up database connection using Oracle's proven database access"""
        try:
            # Use Oracle's database connection with debug mode
            self.db_connection = DatabaseConnection(self.config, debug_mode=self.debug_mode)
            
            # Connect Vanna to the database
            db_path = self.config.get_database_path()
            self.vanna_instance.connect_to_sqlite(db_path)
            
            vanna_logger.info(f"Connected to database: {db_path}")
            
        except Exception as e:
            vanna_logger.error(f"Database connection failed: {e}")
            raise RuntimeError(f"Database connection failed: {e}")
    
    def should_retrain(self) -> bool:
        """Check if retraining is needed based on config settings"""
        try:
            if not self.vanna_config.get('training_on_startup', True):
                return False
            
            # Check if auto-retrain period has passed
            auto_retrain_days = self.vanna_config.get('auto_retrain_days', 7)
            storage_path = Path(self.vanna_config.get('vector_store_path', './oracle/vanna_storage'))
            
            # Look for existing training timestamp
            timestamp_file = storage_path / 'last_training.json'
            
            if timestamp_file.exists():
                try:
                    with open(timestamp_file, 'r') as f:
                        training_data = json.load(f)
                    
                    last_training = datetime.fromisoformat(training_data.get('timestamp', '2000-01-01'))
                    days_since_training = (now_eastern() - last_training.replace(tzinfo=None)).days
                    
                    if days_since_training >= auto_retrain_days:
                        vanna_logger.info(f"Auto-retrain triggered: {days_since_training} days since last training")
                        return True
                    else:
                        vanna_logger.info(f"Training recent: {days_since_training} days ago (threshold: {auto_retrain_days})")
                        return False
                        
                except Exception as e:
                    vanna_logger.warning(f"Could not read training timestamp: {e}")
                    return True
            else:
                vanna_logger.info("No previous training found - first run training needed")
                return True
                
        except Exception as e:
            vanna_logger.error(f"Error checking retrain status: {e}")
            return True
    
    def _save_training_timestamp(self):
        """Save timestamp of successful training"""
        try:
            storage_path = Path(self.vanna_config.get('vector_store_path', './oracle/vanna_storage'))
            storage_path.mkdir(parents=True, exist_ok=True)
            
            timestamp_file = storage_path / 'last_training.json'
            training_data = {
                'timestamp': eastern_isoformat(),
                'version': '1.0',
                'examples_count': len(self.get_training_summary().get('total_training_items', 0))
            }
            
            with open(timestamp_file, 'w') as f:
                json.dump(training_data, f, indent=2)
                
            vanna_logger.info("Training timestamp saved")
            
        except Exception as e:
            vanna_logger.warning(f"Could not save training timestamp: {e}")
    
    def train_on_schema(self):
        """Train Vanna on Oracle's database schema"""
        try:
            vanna_logger.info("Training Vanna on database schema...")
            
            # Get schema using Oracle's data access layer
            schema_info = self.db_connection.get_database_schema()
            
            if 'error' in schema_info:
                vanna_logger.error(f"Schema retrieval failed: {schema_info['error']}")
                return False
            
            # Train on ALL tables in database - fully dynamic
            vanna_logger.info(f"Training on {len(schema_info['tables'])} database tables")
            
            for table_name, table_info in schema_info['tables'].items():
                if 'columns' in table_info:
                    # Create DDL statement
                    columns = table_info['columns']
                    ddl = f"CREATE TABLE {table_name} (\n"
                    col_defs = []
                    
                    for col in columns:
                        col_name = col['name']
                        col_type = col['type']
                        nullable = "" if col['nullable'] else " NOT NULL"
                        primary = " PRIMARY KEY" if col['primary_key'] else ""
                        col_defs.append(f"    {col_name} {col_type}{nullable}{primary}")
                    
                    ddl += ",\n".join(col_defs) + "\n)"
                    
                    # Train Vanna on this table
                    self.vanna_instance.train(ddl=ddl)
                    vanna_logger.info(f"Trained on {table_name} schema")
            
            vanna_logger.info("Schema training completed successfully")
            return True
            
        except Exception as e:
            vanna_logger.error(f"Schema training failed: {e}")
            return False
    
    def train_on_examples(self):
        """Train Vanna on options trading specific examples"""
        try:
            vanna_logger.info("Training on options trading examples...")
            
            # Options trading specific query examples (limited by max_training_examples)
            max_examples = self.vanna_config.get('max_training_examples', 50)
            
            examples = [
                {
                    "question": "What are the most recent options flow alerts?",
                    "sql": "SELECT symbol, significance_score, alert_reason, alert_timestamp FROM flow_alerts ORDER BY alert_timestamp DESC LIMIT 10"
                },
                {
                    "question": "Which symbols had the most alerts today?",
                    "sql": "SELECT symbol, COUNT(*) as alert_count FROM flow_alerts WHERE DATE(alert_timestamp) = DATE('now') GROUP BY symbol ORDER BY alert_count DESC"
                },
                {
                    "question": "Show me recent AAPL options alerts",
                    "sql": "SELECT * FROM flow_alerts WHERE symbol = 'AAPL' ORDER BY alert_timestamp DESC LIMIT 5"
                },
                {
                    "question": "What symbols had high volume today?",
                    "sql": "SELECT symbol, AVG(volume) as avg_volume FROM flow_options_scans WHERE DATE(scan_timestamp) = DATE('now') GROUP BY symbol ORDER BY avg_volume DESC LIMIT 10"
                },
                {
                    "question": "Show me high significance alerts",
                    "sql": "SELECT symbol, significance_score, alert_reason, alert_timestamp FROM flow_alerts WHERE significance_score >= 5.0 ORDER BY alert_timestamp DESC"
                },
                {
                    "question": "What sectors have had alerts recently?",
                    "sql": "SELECT DISTINCT sm.sector, COUNT(fa.id) as alert_count FROM flow_alerts fa JOIN symbol_metadata sm ON fa.symbol = sm.symbol WHERE DATE(fa.alert_timestamp) >= DATE('now', '-7 days') GROUP BY sm.sector ORDER BY alert_count DESC"
                },
                {
                    "question": "Show me put vs call activity for NVDA",
                    "sql": "SELECT option_type, COUNT(*) as contract_count, SUM(volume) as total_volume FROM flow_options_scans WHERE symbol = 'NVDA' AND DATE(scan_timestamp) = DATE('now') GROUP BY option_type"
                },
                {
                    "question": "What are the top stocks by options volume?",
                    "sql": "SELECT symbol, SUM(volume) as total_volume FROM flow_options_scans WHERE DATE(scan_timestamp) = DATE('now') GROUP BY symbol ORDER BY total_volume DESC LIMIT 10"
                },
                {
                    "question": "Show me unusual call activity",
                    "sql": "SELECT symbol, strike, expiration_date, volume, significance_score FROM flow_options_scans WHERE option_type = 'call' AND alert_threshold_met = 1 ORDER BY significance_score DESC LIMIT 10"
                },
                {
                    "question": "Find options with high premium value",
                    "sql": "SELECT symbol, strike, expiration_date, option_type, premium_value FROM flow_options_scans WHERE premium_value > 100000 ORDER BY premium_value DESC LIMIT 10"
                },
                {
                    "question": "What are the current baselines for TSLA?",
                    "sql": "SELECT symbol, volume_mean, volume_std, vol_oi_mean, vol_oi_std, last_updated FROM symbol_baselines WHERE symbol = 'TSLA'"
                },
                {
                    "question": "Show me symbols with recent price movements",
                    "sql": "SELECT symbol, close_price, change_percent, volume FROM historical_prices WHERE trade_date = DATE('now') AND ABS(change_percent) > 2 ORDER BY ABS(change_percent) DESC"
                }
            ]
            
            # Limit examples based on config
            examples_to_use = examples[:max_examples]
            
            # Train on each example
            for example in examples_to_use:
                self.vanna_instance.train(
                    question=example["question"],
                    sql=example["sql"]
                )
                vanna_logger.info(f"Trained example: {example['question'][:50]}...")
            
            vanna_logger.info(f"Example training completed: {len(examples_to_use)} examples")
            return True
            
        except Exception as e:
            vanna_logger.error(f"Example training failed: {e}")
            return False
    
    def train_on_documentation(self):
        """Train Vanna on options trading terminology and concepts"""
        try:
            vanna_logger.info("Training on options trading documentation...")
            
            docs = [
                "Significance score is a measure from 0-10 of how unusual an options flow is, with higher scores indicating more unusual activity.",
                "Flow alerts are generated when options activity meets certain thresholds for unusualness based on volume, open interest, and statistical analysis.",
                "Strike price is the price at which an option can be exercised. It's a key component of option contracts.",
                "Expiration date is when an option contract expires and becomes worthless if not exercised.",
                "Volume represents the number of option contracts traded during a specific period.",
                "Open interest is the total number of outstanding option contracts that have not been settled.",
                "Call options give the holder the right to buy the underlying stock at the strike price.",
                "Put options give the holder the right to sell the underlying stock at the strike price.",
                "Moneyness describes whether an option is in-the-money (ITM), at-the-money (ATM), or out-of-the-money (OTM).",
                "The underlying price is the current market price of the stock that the option is based on.",
                "Implied volatility (IV) reflects the market's expectation of future volatility in the underlying stock.",
                "Premium value is the total dollar amount of options contracts, calculated as price × volume × 100.",
                "Days to expiration (DTE) is the number of calendar days until the option expires.",
                "The Greeks (delta, gamma, theta, vega) measure various risk sensitivities of options.",
                "Alert timestamps are stored in Eastern Time (EST/EDT) to match market hours."
            ]
            
            for doc in docs:
                self.vanna_instance.train(documentation=doc)
            
            vanna_logger.info("Documentation training completed successfully")
            return True
            
        except Exception as e:
            vanna_logger.error(f"Documentation training failed: {e}")
            return False
    
    def _sync_metadata_files(self):
        """Synchronize JSON metadata files with current database schema to prevent drift"""
        try:
            vanna_logger.info("Synchronizing metadata files with current database schema...")
            
            storage_path = Path(self.vanna_config.get('vector_store_path', './oracle/vanna_storage'))
            
            # Get current schema directly from database
            current_schema = self.db_connection.get_database_schema()
            
            # Update DDL metadata with current schema
            ddl_metadata = []
            for table_name, columns in current_schema.items():
                column_defs = []
                for col_name, col_info in columns.items():
                    col_def = f"    {col_name} {col_info['type']}"
                    if col_info.get('pk'):
                        col_def += " PRIMARY KEY"
                    elif col_info.get('notnull'):
                        col_def += " NOT NULL"
                    column_defs.append(col_def)
                
                ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(column_defs) + "\n)"
                
                ddl_metadata.append({
                    "id": f"schema_sync_{table_name}_{now_eastern().strftime('%Y%m%d')}",
                    "ddl": ddl
                })
            
            # Write updated DDL metadata
            ddl_file = storage_path / 'ddl_metadata.json'
            with open(ddl_file, 'w') as f:
                json.dump(ddl_metadata, f, indent=2)
            
            vanna_logger.info(f"Updated DDL metadata for {len(ddl_metadata)} tables")
            
            # Load and preserve existing SQL examples but ensure no duplicates
            sql_file = storage_path / 'sql_metadata.json'
            existing_sql = []
            if sql_file.exists():
                try:
                    with open(sql_file, 'r') as f:
                        existing_sql = json.load(f)
                except Exception as e:
                    vanna_logger.warning(f"Could not load existing SQL metadata: {e}")
            
            # Remove duplicates based on question text
            seen_questions = set()
            unique_sql = []
            for item in existing_sql:
                question = item.get('question', '').strip()
                if question and question not in seen_questions:
                    seen_questions.add(question)
                    unique_sql.append(item)
            
            # Write cleaned SQL metadata
            with open(sql_file, 'w') as f:
                json.dump(unique_sql, f, indent=2)
            
            vanna_logger.info(f"Cleaned SQL metadata: {len(unique_sql)} unique examples")
            
            return True
            
        except Exception as e:
            vanna_logger.error(f"Failed to sync metadata files: {e}")
            return False

    def full_training_sequence(self):
        """Execute complete training sequence with config awareness"""
        vanna_logger.info("Starting full Oracle training sequence...")
        
        # Clear existing vector stores for fresh training (prevents duplicates)
        storage_path = Path(self.vanna_config.get('vector_store_path', './oracle/vanna_storage'))
        faiss_files_deleted = 0
        for faiss_file in storage_path.glob('*.faiss'):
            try:
                faiss_file.unlink()
                faiss_files_deleted += 1
            except Exception as e:
                vanna_logger.warning(f"Could not delete {faiss_file}: {e}")
        
        if faiss_files_deleted > 0:
            vanna_logger.info(f"Cleared {faiss_files_deleted} existing vector stores for fresh training")
        
        training_results = {
            'schema': self.train_on_schema(),
            'examples': self.train_on_examples(),
            'documentation': self.train_on_documentation()
        }
        
        success_count = sum(training_results.values())
        total_count = len(training_results)
        
        vanna_logger.info(f"Training completed: {success_count}/{total_count} components successful")
        
        if success_count == total_count:
            vanna_logger.info("🎯 Full training sequence completed successfully!")
            
            # Sync metadata files to prevent future drift
            sync_success = self._sync_metadata_files()
            if sync_success:
                vanna_logger.info("✅ Metadata files synchronized with current schema")
            else:
                vanna_logger.warning("⚠️ Metadata sync had issues but training completed")
            
            self._save_training_timestamp()
            return True
        else:
            vanna_logger.warning(f"⚠️ Training had issues: {training_results}")
            return success_count > 0  # Return True if at least some training succeeded
    
    def force_comprehensive_training(self):
        """Force complete retraining with all tables - ignores timing restrictions"""
        try:
            vanna_logger.info("🔄 FORCING comprehensive Vanna retraining with all tables...")
            
            # Clear existing training timestamp to force retrain
            storage_path = Path(self.vanna_config.get('vector_store_path', './oracle/vanna_storage'))
            timestamp_file = storage_path / 'last_training.json'
            if timestamp_file.exists():
                timestamp_file.unlink()
                vanna_logger.info("Cleared existing training timestamp")
            
            # Run full training sequence (which will now use the expanded table list)
            training_result = self.full_training_sequence()
            
            if training_result:
                vanna_logger.info("🎯 COMPREHENSIVE training completed successfully!")
                vanna_logger.info("Vanna now knows about ALL 16 tables in your system")
            else:
                vanna_logger.warning("⚠️ Training had some issues but partially completed")
            
            return training_result
            
        except Exception as e:
            vanna_logger.error("Force training failed: {}".format(e))
            return False
            
    def _get_cache_key(self, question: str) -> str:
        """Generate a cache key for the question"""
        import hashlib
        return hashlib.md5(question.lower().encode()).hexdigest()
    
    def _get_cache_ttl(self, question: str, success: bool = True) -> int:
        """Determine appropriate cache TTL based on query pattern and success"""
        question_lower = question.lower()
        
        # Failed queries get short cache
        if not success:
            return self.cache_ttl_failed
        
        # Historical queries (date filters, past data) get longer cache
        historical_indicators = [
            'date(', 'yesterday', 'last week', 'last month', 
            '2024-', '2025-', 'trade_date <', 'alert_timestamp <'
        ]
        if any(indicator in question_lower for indicator in historical_indicators):
            return self.cache_ttl_historical
        
        # Current day queries get default cache
        current_indicators = ['today', 'now', 'current', 'latest', 'recent']
        if any(indicator in question_lower for indicator in current_indicators):
            return self.cache_ttl_default
        
        # Analysis queries that don't depend on time get longer cache
        analysis_indicators = ['profitability', 'summary', 'analysis', 'compare', 'pattern']
        if any(indicator in question_lower for indicator in analysis_indicators):
            return self.cache_ttl_historical
        
        # Default to standard cache
        return self.cache_ttl_default

    def _is_cache_valid(self, cache_entry: Dict, question: str = "") -> bool:
        """Check if cache entry is still valid (not expired)"""
        import time
        
        # Get appropriate TTL for this query type
        ttl = cache_entry.get('ttl', self.cache_ttl_default)
        
        # If we have the original question, recalculate TTL for accuracy
        if question:
            success = cache_entry.get('success', True)
            ttl = self._get_cache_ttl(question, success)
        
        return time.time() - cache_entry['timestamp'] < ttl
    
    def ask_question(self, question: str) -> Dict[str, Any]:
        """
        Ask Oracle a question using Vanna's RAG approach with conversation context
        
        Enhanced with conversation persistence and caching:
        1. Check cache for recent identical questions
        2. Resolve references using conversation context
        3. Generate SQL with context-enhanced prompts  
        4. Execute and analyze results
        5. Cache results and update context for next interaction
        """
        try:
            start_time = time.time()
            
            # STEP 1: Check cache first
            resolved_question = self.conversation_context.resolve_references(question)
            cache_key = self._get_cache_key(resolved_question)
            
            if cache_key in self.query_cache and self._is_cache_valid(self.query_cache[cache_key], resolved_question):
                cached_response = self.query_cache[cache_key]['response']
                # Add cache indicator to the response
                cached_response['content'] = cached_response['content'] + "\n\n📋 (cached result)"
                if self.debug_mode:
                    vanna_logger.info("Returning cached result for question: {}".format(resolved_question))
                return cached_response
            
            # STEP 2: Resolve references using conversation context
            if resolved_question != question:
                if self.debug_mode:
                    vanna_logger.info("Question resolved: '{}' -> '{}'".format(question, resolved_question))
            
            if self.debug_mode:
                vanna_logger.info("Processing question: {}".format(resolved_question))
            
            # STEP 3: Generate SQL using Vanna with resolved question
            sql = self.vanna_instance.generate_sql(resolved_question)
            if self.debug_mode:
                vanna_logger.info("Generated SQL: {}".format(sql))
            
            # STEP 4: Execute SQL using Vanna's connection
            df_results = self.vanna_instance.run_sql(sql)

            # Convert DataFrame to list of dicts for Oracle compatibility
            if df_results is not None and not df_results.empty:
                results = df_results.to_dict('records')
            else:
                results = []

            # Get exact token data from SQL generation (Vanna/Haiku)
            sql_tokens = getattr(self.vanna_instance, '_last_call_tokens', {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'cost': 0.0,
                'model': self._get_effective_model()
            })
            
            # STEP 5: Analyze results with Claude Sonnet for intelligence
            analysis_result = self._analyze_results_with_claude(resolved_question, sql, results)
            
            # Calculate total execution time
            execution_time = time.time() - start_time
            
            # Combine token usage from both API calls
            total_tokens = {
                'sql_generation': sql_tokens,
                'results_analysis': analysis_result['analysis_tokens'],
                'combined_cost': sql_tokens['cost'] + analysis_result['analysis_tokens']['cost'],
                'total_tokens': sql_tokens['total_tokens'] + analysis_result['analysis_tokens']['total_tokens']
            }
            
            # Determine primary content (analysis or fallback)
            if analysis_result['success']:
                primary_content = analysis_result['analysis_content']
                analysis_used = True
            else:
                primary_content = self._format_results_for_display(results, resolved_question)
                analysis_used = False
                vanna_logger.warning("Using fallback formatting due to analysis failure")
            
            # Build comprehensive response (hide raw results unless debug mode)
            response = {
                'success': True,
                'content': primary_content,  # Natural language analysis (primary)
                'sql_generated': sql if self.debug_mode else None,  # Hide SQL unless debug
                'execution_time_seconds': round(execution_time, 3),
                'timestamp': eastern_isoformat(),
                'query_type': 'vanna_with_analysis',
                'token_breakdown': total_tokens,  # Always keep token tracking
                'analysis_metadata': {
                    'analysis_used': analysis_used,
                    'fallback_used': analysis_result.get('fallback_used', False),
                    'results_count': len(results),
                    'models_used': {
                        'sql_generation': sql_tokens['model'],
                        'analysis': analysis_result['analysis_tokens']['model']
                    },
                    'context_resolved': resolved_question != question,
                    'original_question': question if resolved_question != question else None
                }
            }
            
            # Only include raw results in debug mode
            if self.debug_mode:
                response['raw_results'] = results
            
            # STEP 6: Update conversation context for next interaction
            self.conversation_context.update_context(resolved_question, response)
            
            # STEP 7: Cache the response for future identical questions with intelligent TTL
            success = response.get('success', False)
            ttl = self._get_cache_ttl(resolved_question, success)
            
            self.query_cache[cache_key] = {
                'response': response.copy(),  # Store a copy to avoid mutation
                'timestamp': time.time(),
                'ttl': ttl,
                'success': success,
                'question_pattern': resolved_question[:100]  # Store truncated question for debugging
            }
            
            # Add to conversation history with full context
            self.conversation_history.append({
                'user_input': question,
                'resolved_input': resolved_question if resolved_question != question else None,
                'sql_generated': sql,
                'results_count': len(results) if results else 0,
                'token_breakdown': total_tokens,
                'analysis_used': analysis_used,
                'context_summary': self.conversation_context.get_context_summary(),
                'timestamp': eastern_isoformat()
            })
            
            # Enhanced logging (debug mode only for detailed info)
            if self.debug_mode:
                vanna_logger.info("Question processed successfully in {:.2f}s".format(execution_time))
                vanna_logger.info("SQL tokens: {}in/{}out = ${:.4f} ({})".format(
                    sql_tokens['input_tokens'], sql_tokens['output_tokens'], 
                    sql_tokens['cost'], sql_tokens['model']))
                if analysis_result['success']:
                    analysis_tokens = analysis_result['analysis_tokens']
                    vanna_logger.info("Analysis tokens: {}in/{}out = ${:.4f} ({})".format(
                        analysis_tokens['input_tokens'], analysis_tokens['output_tokens'], 
                        analysis_tokens['cost'], analysis_tokens['model']))
                vanna_logger.info("Total cost: ${:.4f}".format(total_tokens['combined_cost']))
                vanna_logger.debug("Context: {}".format(self.conversation_context.get_context_summary()))
            
            # Log the query for comprehensive audit trail
            self.query_logger.log_query(question, response, source="interactive")
            
            return response
            
        except Exception as e:
            vanna_logger.error("Error processing question: {}".format(e))
            error_response = {
                'success': False,
                'error': str(e),
                'content': "❌ Error processing question: {}".format(e),
                'timestamp': eastern_isoformat(),
                'fallback_used': True
            }
            
            # Log the failed query as well
            self.query_logger.log_query(question, error_response, source="interactive")
            
            return error_response
            
    def _analyze_results_with_claude(self, question: str, sql: str, results: List[Dict]) -> Dict[str, Any]:
        """
        Send results to Claude Sonnet for intelligent analysis and insights
        
        Args:
            question: Original user question
            sql: Generated SQL query
            results: Raw database results
            
        Returns:
            Dict with analysis content, token usage, and metadata
        """
        analysis_start_time = time.time()
        
        try:
            # Import Claude client for direct Sonnet access
            import anthropic
            
            # Create dedicated analysis client with Sonnet
            analysis_client = anthropic.Anthropic(api_key=self.config.claude_api_key)
            
            # Build comprehensive analysis prompt
            analysis_prompt = self._build_analysis_prompt(question, sql, results)
            
            if self.debug_mode:
                vanna_logger.info(f"Starting Claude Sonnet analysis for {len(results)} results")
            
            # Make analysis API call with Sonnet
            analysis_response = analysis_client.messages.create(
                model="claude-3-5-sonnet-20241022",  # Force Sonnet for analysis
                max_tokens=4000,  # More tokens for detailed analysis
                temperature=0.1,  # Low temperature for consistent insights
                messages=[
                    {
                        "role": "user", 
                        "content": analysis_prompt
                    }
                ]
            )
            
            analysis_time = time.time() - analysis_start_time
            
            # Extract analysis content and exact token usage
            analysis_content = analysis_response.content[0].text
            input_tokens = analysis_response.usage.input_tokens
            output_tokens = analysis_response.usage.output_tokens
            
            # Calculate analysis cost
            analysis_cost = self.usage_tracker.calculate_cost(
                "claude-3-5-sonnet-20241022", 
                input_tokens, 
                output_tokens
            )
            
            # Track analysis usage separately
            self.usage_tracker.add_usage(
                model="claude-3-5-sonnet-20241022",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                query_type="results_analysis",
                execution_time=analysis_time
            )
            
            # Always show analysis completion summary (performance info you like)
            vanna_logger.info(f"Analysis completed in {analysis_time:.2f}s - {input_tokens}in/{output_tokens}out tokens - ${analysis_cost:.4f}")
            
            return {
                'success': True,
                'analysis_content': analysis_content,
                'analysis_tokens': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                    'cost': analysis_cost,
                    'model': 'claude-3-5-sonnet-20241022'
                },
                'analysis_time': analysis_time
            }
            
        except Exception as e:
            analysis_time = time.time() - analysis_start_time
            vanna_logger.error(f"Analysis failed after {analysis_time:.2f}s: {e}")
            
            # Return fallback to raw formatting
            return {
                'success': False,
                'error': str(e),
                'analysis_content': self._format_results_for_display(results, question),
                'analysis_tokens': {
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'total_tokens': 0,
                    'cost': 0.0,
                    'model': 'fallback'
                },
                'analysis_time': analysis_time,
                'fallback_used': True
            }
    
    def _build_analysis_prompt(self, question: str, sql: str, results: List[Dict]) -> str:
        """Build comprehensive analysis prompt for Claude Sonnet"""
        
        # Get current timestamp for context
        current_time = eastern_isoformat()
        
        # Determine result context
        result_count = len(results)
        has_financial_data = any(
            key in str(results).lower() 
            for key in ['price', 'volume', 'premium', 'cost', 'change']
        ) if results else False
        
        has_sector_data = any(
            key in str(results).lower() 
            for key in ['sector', 'industry', 'technology', 'financial']
        ) if results else False
        
        # Build context-aware prompt
        prompt = f"""You are Oracle, an expert options trading analyst. A user asked: "{question}"

        I generated this SQL query and executed it against our options trading database:

        ```sql
        {sql}
        ```

        The query returned {result_count} results at {current_time} EST:

        ```json
        {json.dumps(results, indent=2, default=str)}
        ```

        Your task: Provide intelligent analysis and actionable trading insights based on these results.

        ANALYSIS GUIDELINES:
        1. **Start with a clear, direct answer** to the user's question
        2. **Identify patterns and trends** in the data that matter for trading
        3. **Provide context** - what do these numbers mean for traders?
        4. **Include actionable insights** - what should someone do with this information?
        5. **Note any correlations** or relationships between data points
        6. **Highlight unusual activity** or significant findings
        7. **Keep it conversational** but professional - you're talking to a trader

        DOMAIN CONTEXT:
        - Significance scores >7.0 indicate highly unusual options activity
        - Premium values >$100K represent substantial institutional flows  
        - Alert timestamps show when unusual activity was detected
        - Volume comparisons to baselines reveal relative unusualness
        - Sector analysis helps identify rotation patterns
        - Strike prices and expiration dates matter for directional bets

        FORMATTING:
        - Lead with the key insight in the first sentence
        - Use natural paragraphs, not bullet points
        - Include specific numbers and percentages from the data
        - Mention timeframes and context where relevant
        - End with practical implications or next steps

        Do NOT:
        - Simply restate the raw data
        - Use generic trading advice
        - Ignore the specific question asked
        - Make predictions about future price movements
        - Recommend specific buy/sell actions

        Analyze the results and provide valuable insights that help the user understand what this data means for options trading."""

        return prompt
    
    def _format_results_for_display(self, results: List[Dict], question: str) -> str:
        """Format SQL results for display in Oracle's CLI"""
        if not results:
            return "No results found for your query."
        
        result_count = len(results)
        
        # Create a natural language summary
        content = f"Found {result_count} result{'s' if result_count != 1 else ''} for: {question}\n\n"
        
        # Show first few results in a readable format
        display_limit = min(5, result_count)
        
        for i, row in enumerate(results[:display_limit]):
            content += f"Result {i+1}:\n"
            for key, value in row.items():
                # Format value for display
                if value is None:
                    formatted_value = 'NULL'
                elif isinstance(value, float):
                    formatted_value = f"{value:.4f}" if abs(value) < 1000 else f"{value:,.2f}"
                elif isinstance(value, int) and abs(value) > 1000:
                    formatted_value = f"{value:,}"
                else:
                    formatted_value = str(value)
                
                content += f"  {key}: {formatted_value}\n"
            content += "\n"
        
        if result_count > display_limit:
            content += f"... and {result_count - display_limit} more results\n"
        
        return content
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history compatible with Oracle's CLI"""
        return self.conversation_history.copy()
    
    def clear_conversation_history(self):
        """Clear conversation history and context"""
        self.conversation_history = []
        self.conversation_context.clear_context()
        vanna_logger.info("Conversation history and context cleared")
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary with conversation context information"""
        base_summary = self.usage_tracker.get_session_summary()
        
        # Add Oracle-specific metadata with context info
        base_summary.update({
            "default_model": self.get_current_model(),
            "max_tokens_per_request": self.config.claude_max_tokens,
            "conversation_turns": len(self.conversation_history),
            "system_type": "Oracle (Powered by Vanna)",
            "context_summary": self.conversation_context.get_context_summary(),
            "context_enabled": True
        })
        
        return base_summary
    
    def get_vanna_status(self) -> Dict[str, Any]:
        """Get comprehensive Vanna configuration and status"""
        try:
            storage_path = Path(self.vanna_config.get('vector_store_path', './oracle/vanna_storage'))
            
            # Check for training files
            training_files = {
                'sql_index': (storage_path / 'sql_index.faiss').exists(),
                'ddl_index': (storage_path / 'ddl_index.faiss').exists(), 
                'doc_index': (storage_path / 'doc_index.faiss').exists(),
                'last_training': (storage_path / 'last_training.json').exists()
            }
            
            # Get training summary
            training_summary = self.get_training_summary()
            
            return {
                "success": True,
                "config": self.vanna_config,
                "storage_path": str(storage_path),
                "training_files": training_files,
                "training_summary": training_summary,
                "needs_retraining": self.should_retrain(),
                "current_model": self.get_current_model(),
                "timestamp": eastern_isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": eastern_isoformat()
            }

    def get_training_summary(self) -> Dict[str, Any]:
        """Get summary of Vanna's training data"""
        try:
            # Get training data from Vanna
            training_data = self.vanna_instance.get_training_data()
            
            return {
                "success": True,
                "ddl_count": len(training_data.get('ddl', [])),
                "question_sql_count": len(training_data.get('sql', [])),
                "documentation_count": len(training_data.get('documentation', [])),
                "total_training_items": sum([
                    len(training_data.get('ddl', [])),
                    len(training_data.get('sql', [])),
                    len(training_data.get('documentation', []))
                ])
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "total_training_items": 0
            }
    
    def estimate_cost_for_question(self, question: str) -> float:
        """Estimate cost for a question before processing"""
        # Rough estimation based on question complexity
        estimated_input_tokens = len(question.split()) * 10  # Include context
        estimated_output_tokens = 200  # SQL + explanation
        
        return self.usage_tracker.calculate_cost(
            self._get_effective_model(),
            int(estimated_input_tokens),
            estimated_output_tokens
        )
    
    def _load_vanna_settings(self) -> Dict[str, Any]:
        """Load Vanna-specific settings from Oracle config"""
        try:
            # Get Oracle section from config
            oracle_config = self.config.config.get('oracle', {})
            vanna_settings = oracle_config.get('vanna', {})
            
            # Apply defaults for missing settings
            defaults = {
                "training_on_startup": True,
                "auto_retrain_days": 7,
                "vector_store_path": "./oracle/vanna_storage",
                "embedding_model": "all-MiniLM-L6-v2", 
                "max_training_examples": 50,
                "similarity_threshold": 0.7
            }
            
            # Merge defaults with user settings
            for key, default_value in defaults.items():
                if key not in vanna_settings:
                    vanna_settings[key] = default_value
            
            vanna_logger.info(f"Vanna settings loaded: {vanna_settings}")
            return vanna_settings
            
        except Exception as e:
            vanna_logger.warning(f"Failed to load Vanna settings, using defaults: {e}")
            return {
                "training_on_startup": True,
                "auto_retrain_days": 7,
                "vector_store_path": "./oracle/vanna_storage",
                "embedding_model": "all-MiniLM-L6-v2",
                "max_training_examples": 50,
                "similarity_threshold": 0.7
            }
    
    def _get_effective_model(self) -> str:
        """Get the effective model to use (override or config default)"""
        if self.model_override:
            # Map short names to full model identifiers
            model_map = {
                'haiku': 'claude-3-5-haiku-20241022',
                'sonnet': 'claude-3-5-sonnet-20241022'
            }
            return model_map.get(self.model_override.lower(), self.model_override)
        
        return self.config.claude_model
    
    def get_current_model(self) -> str:
        """Get the currently active model"""
        return self._get_effective_model()
    
    def switch_model(self, new_model: str):
        """Switch Claude model"""
        old_model = self._get_effective_model()
        
        # Map short names to full identifiers
        model_map = {
            'haiku': 'claude-3-5-haiku-20241022',
            'sonnet': 'claude-3-5-sonnet-20241022'
        }
        
        if new_model.lower() in model_map:
            self.model_override = new_model.lower()
            effective_model = model_map[new_model.lower()]
        else:
            self.model_override = new_model
            effective_model = new_model
        
        vanna_logger.info(f"Model switched: {old_model} -> {effective_model}")
        vanna_logger.warning("Note: Model changes take effect on next question for optimal performance")
        
        # Update the Vanna instance's model if possible
        if hasattr(self.vanna_instance, 'model'):
            self.vanna_instance.model = effective_model

if __name__ == "__main__":
    sys.exit(main())