#!/usr/bin/env python3
"""
Claude API Client (claude_api.py)
--------------------------------
Claude API integration with function calling support for Oracle CLI.
Handles natural language processing and function execution coordination.

Features:
- Function calling integration with Oracle analysis functions
- Token usage tracking and cost estimation
- Model switching (Haiku vs Sonnet) with cost awareness
- Retry logic and error handling
- Conversation context management
- Comprehensive logging of API interactions

Author: Ben (with assistance from Claude)
Date: 2025-07-10
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from anthropic import Anthropic
from .functions import execute_function
from .functions.functions_registry import AVAILABLE_FUNCTIONS
from tools.timezone_utils import now_eastern, eastern_date_string, eastern_isoformat
from .oracle_intelligence import classify_and_optimize
from .oracle_semantic_cache import SemanticFunctionCache


# API-specific logger
api_logger = logging.getLogger('oracle.claude_api')

class TokenUsageTracker:
    """
    Enhanced token usage and cost tracking with dashboard capabilities.
    
    Step 4.1 Enhancement: Added detailed cost monitoring, function-level tracking,
    cost trends analysis, and dashboard-ready statistics for cost optimization.
    """
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        self.session_start = now_eastern()
        
        # Enhanced tracking for cost monitoring
        self.function_costs = {}  # Track cost per function
        self.hourly_costs = {}   # Track cost trends by hour
        self.cost_alerts = []    # Track when costs exceed thresholds
        self.daily_budget = 5.00  # Default $5 daily budget
        
        # Claude pricing (per million tokens) as of 2025-07-13
        self.pricing = {
            "claude-3-5-haiku-20241022": {"input": 0.25, "output": 1.25, "name": "Haiku"},
            "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00, "name": "Sonnet"},
            "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "name": "Sonnet 4"}
        }
        
        # Cost thresholds for monitoring
        self.cost_thresholds = {
            "function_warning": 0.05,    # Warn if single function call > $0.05
            "hourly_warning": 1.00,      # Warn if hourly spend > $1.00
            "daily_warning": 4.00,       # Warn if approaching daily budget
            "session_limit": 10.00       # Hard limit for session spending
        }
    
    def add_usage(self, model: str, input_tokens: int, output_tokens: int, 
                  function_name: str = None, execution_time: float = 0.0):
        """
        Enhanced usage tracking with function-level cost monitoring.
        
        Args:
            model: Claude model used
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
            function_name: Name of Oracle function executed (if applicable)
            execution_time: Function execution time in seconds
        """
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1
        
        # Calculate cost for this call
        call_cost = self.calculate_cost(model, input_tokens, output_tokens)
        current_hour = now_eastern().strftime('%Y-%m-%d %H:00')
        
        # Track function-level costs
        if function_name:
            if function_name not in self.function_costs:
                self.function_costs[function_name] = {
                    "total_cost": 0.0,
                    "call_count": 0,
                    "total_tokens": 0,
                    "avg_cost": 0.0,
                    "max_cost": 0.0,
                    "total_execution_time": 0.0,
                    "model_usage": {}
                }
            
            func_stats = self.function_costs[function_name]
            func_stats["total_cost"] += call_cost
            func_stats["call_count"] += 1
            func_stats["total_tokens"] += (input_tokens + output_tokens)
            func_stats["avg_cost"] = func_stats["total_cost"] / func_stats["call_count"]
            func_stats["max_cost"] = max(func_stats["max_cost"], call_cost)
            func_stats["total_execution_time"] += execution_time
            
            # Track model usage per function
            model_name = self.pricing.get(model, {}).get("name", model)
            func_stats["model_usage"][model_name] = func_stats["model_usage"].get(model_name, 0) + 1
        
        # Track hourly costs for trend analysis
        if current_hour not in self.hourly_costs:
            self.hourly_costs[current_hour] = {
                "cost": 0.0,
                "calls": 0,
                "tokens": 0
            }
        
        hourly_stats = self.hourly_costs[current_hour]
        hourly_stats["cost"] += call_cost
        hourly_stats["calls"] += 1
        hourly_stats["tokens"] += (input_tokens + output_tokens)
        
        # Check cost thresholds and generate alerts
        self._check_cost_thresholds(call_cost, function_name, current_hour)
        
        # Enhanced logging with cost awareness
        cost_level = "HIGH" if call_cost >= 0.05 else "MED" if call_cost >= 0.01 else "LOW"
        api_logger.info("{} COST API call: {} - {}in/{}out tokens - ${:.4f} - Function: {}".format(
            cost_level, model, input_tokens, output_tokens, call_cost, function_name or "direct"))
    
    def _check_cost_thresholds(self, call_cost: float, function_name: str, current_hour: str):
        """Check if costs exceed configured thresholds and generate alerts"""
        
        # Single function call cost alert
        if call_cost >= self.cost_thresholds["function_warning"]:
            alert = {
                "type": "high_function_cost",
                "function_name": function_name,
                "cost": call_cost,
                "threshold": self.cost_thresholds["function_warning"],
                "timestamp": eastern_isoformat(),
                "message": "Function {} cost ${:.4f} exceeds warning threshold ${:.2f}".format(
                    function_name, call_cost, self.cost_thresholds["function_warning"])
            }
            self.cost_alerts.append(alert)
            api_logger.warning(alert["message"])
        
        # Hourly spending alert
        hourly_total = self.hourly_costs[current_hour]["cost"]
        if hourly_total >= self.cost_thresholds["hourly_warning"]:
            alert = {
                "type": "high_hourly_cost",
                "hour": current_hour,
                "cost": hourly_total,
                "threshold": self.cost_thresholds["hourly_warning"],
                "timestamp": eastern_isoformat(),
                "message": "Hourly spending ${:.2f} exceeds warning threshold ${:.2f}".format(
                    hourly_total, self.cost_thresholds["hourly_warning"])
            }
            self.cost_alerts.append(alert)
            api_logger.warning(alert["message"])
        
        # Session total alert
        session_total = self.get_session_total_cost()
        if session_total >= self.cost_thresholds["daily_warning"]:
            alert = {
                "type": "approaching_daily_budget",
                "session_cost": session_total,
                "daily_budget": self.daily_budget,
                "timestamp": eastern_isoformat(),
                "message": "Session cost ${:.2f} approaching daily budget ${:.2f}".format(
                    session_total, self.daily_budget)
            }
            self.cost_alerts.append(alert)
            api_logger.warning(alert["message"])
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a specific API call"""
        if model not in self.pricing:
            # Default to Sonnet pricing for unknown models
            model = "claude-sonnet-4-20250514"
        
        prices = self.pricing[model]
        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]
        return input_cost + output_cost
    
    def get_session_total_cost(self) -> float:
        """Calculate total cost for current session"""
        total_cost = 0.0
        for func_stats in self.function_costs.values():
            total_cost += func_stats["total_cost"]
        return total_cost
    
    def get_cost_dashboard(self) -> Dict[str, Any]:
        """
        Generate comprehensive cost monitoring dashboard data.
        
        Returns detailed statistics for cost analysis and optimization.
        """
        session_duration = (now_eastern() - self.session_start).total_seconds() / 60
        total_cost = self.get_session_total_cost()
        
        # Calculate cost per minute and projected daily cost
        cost_per_minute = total_cost / max(session_duration, 1)
        projected_daily_cost = cost_per_minute * (24 * 60)
        
        # Find most expensive functions
        expensive_functions = sorted(
            self.function_costs.items(),
            key=lambda x: x[1]["total_cost"],
            reverse=True
        )[:5]
        
        # Calculate hourly trend
        hourly_trend = []
        for hour, stats in sorted(self.hourly_costs.items()):
            hourly_trend.append({
                "hour": hour,
                "cost": round(stats["cost"], 4),
                "calls": stats["calls"],
                "tokens": stats["tokens"],
                "avg_cost_per_call": round(stats["cost"] / max(stats["calls"], 1), 4)
            })
        
        # Budget analysis
        budget_utilization = (total_cost / self.daily_budget) * 100
        budget_status = "OVER_BUDGET" if total_cost > self.daily_budget else \
                       "WARNING" if budget_utilization > 80 else \
                       "HEALTHY" if budget_utilization > 50 else "LOW"
        
        # Cost optimization recommendations
        recommendations = self._generate_cost_recommendations()
        
        return {
            "session_summary": {
                "duration_minutes": round(session_duration, 1),
                "total_cost": round(total_cost, 4),
                "total_api_calls": self.total_calls,
                "cost_per_minute": round(cost_per_minute, 4),
                "projected_daily_cost": round(projected_daily_cost, 2),
                "avg_cost_per_call": round(total_cost / max(self.total_calls, 1), 4)
            },
            
            "budget_analysis": {
                "daily_budget": self.daily_budget,
                "current_spend": round(total_cost, 4),
                "budget_utilization_percent": round(budget_utilization, 1),
                "remaining_budget": round(self.daily_budget - total_cost, 4),
                "budget_status": budget_status,
                "projected_overage": max(0, round(projected_daily_cost - self.daily_budget, 2))
            },
            
            "function_costs": [
                {
                    "function_name": func_name,
                    "total_cost": round(stats["total_cost"], 4),
                    "call_count": stats["call_count"],
                    "avg_cost": round(stats["avg_cost"], 4),
                    "max_cost": round(stats["max_cost"], 4),
                    "cost_percentage": round((stats["total_cost"] / total_cost * 100), 1) if total_cost > 0 else 0
                }
                for func_name, stats in expensive_functions
            ],
            
            "hourly_trend": hourly_trend,
            
            "cost_alerts": self.cost_alerts[-10:],  # Last 10 alerts
            
            "optimization_recommendations": recommendations,
            
            "token_statistics": {
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_input_tokens + self.total_output_tokens,
                "avg_tokens_per_call": (self.total_input_tokens + self.total_output_tokens) / max(self.total_calls, 1)
            },
            
            "timestamp": eastern_isoformat()
        }
    
    def _generate_cost_recommendations(self) -> List[Dict[str, str]]:
        """Generate cost optimization recommendations based on usage patterns"""
        recommendations = []
        
        # Check for expensive functions
        for func_name, stats in self.function_costs.items():
            if stats["avg_cost"] > 0.05:
                if func_name == "model_profit_scenarios":
                    recommendations.append({
                        "type": "function_optimization",
                        "priority": "high",
                        "message": "Use 'quick' or 'standard' detail_level for model_profit_scenarios() to reduce costs",
                        "potential_savings": "50-80% cost reduction"
                    })
                else:
                    recommendations.append({
                        "type": "function_cost",
                        "priority": "medium",
                        "message": "Function '{}' has high average cost (${:.3f}) - consider optimization".format(
                            func_name, stats["avg_cost"]),
                        "potential_savings": "Function-specific optimization needed"
                    })
        
        # Check for repeated expensive calls
        repeated_expensive = [
            (name, stats) for name, stats in self.function_costs.items()
            if stats["call_count"] > 3 and stats["avg_cost"] > 0.02
        ]
        
        if repeated_expensive:
            recommendations.append({
                "type": "caching_opportunity",
                "priority": "high", 
                "message": "Enable caching for repeated expensive function calls",
                "potential_savings": "70-90% for cached results"
            })
        
        # Budget warnings
        total_cost = self.get_session_total_cost()
        if total_cost > self.daily_budget * 0.8:
            recommendations.append({
                "type": "budget_warning",
                "priority": "high",
                "message": "Approaching daily budget limit - consider using Haiku model for simple queries",
                "potential_savings": "75% cost reduction vs Sonnet"
            })
        
        return recommendations
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of token usage and costs for this session (backwards compatibility)"""
        dashboard = self.get_cost_dashboard()
        
        # Return simplified summary for backwards compatibility
        return {
            "session_duration_minutes": dashboard["session_summary"]["duration_minutes"],
            "total_api_calls": dashboard["session_summary"]["total_api_calls"],
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_total_cost": dashboard["session_summary"]["total_cost"],
            "avg_tokens_per_call": dashboard["token_statistics"]["avg_tokens_per_call"]
        }
    
    def set_daily_budget(self, budget: float):
        """Set daily spending budget for monitoring"""
        self.daily_budget = budget
        api_logger.info("Daily budget set to ${:.2f}".format(budget))
    
    def reset_session_tracking(self):
        """Reset tracking for new session while preserving configuration"""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        self.function_costs = {}
        self.hourly_costs = {}
        self.cost_alerts = []
        self.session_start = now_eastern()
        api_logger.info("Session tracking reset")

class ClaudeClient:
    """Claude API client with function calling and conversation management"""
    
    def __init__(self, config):
        """Initialize Claude client with configuration
        
        Args:
            config: OracleConfig instance with API settings
        """
        self.config = config
        self.api_key = config.claude_api_key
        self.default_model = config.claude_model
        self.max_tokens = config.claude_max_tokens
        
        # Initialize Anthropic client
        self.client = Anthropic(api_key=self.api_key)

        # Token usage tracking
        self.usage_tracker = TokenUsageTracker()
        
        # Conversation context (for multi-turn conversations)
        self.conversation_history = []
        
        # Initialize semantic cache
        self.semantic_cache = None
        self._initialize_semantic_cache()   
        
        # Set base system prompt FIRST
        self.system_prompt = """You are Oracle, an expert options trading analysis system.

        CORE RULES:
        - Match function complexity to query complexity
        - Simple queries = simple functions, complex queries = complex functions
        - Always prefer the most efficient function for the task
        - Use execute_custom_sql() for single data point lookups
        - Always assume any dates with unspecified years are for the current year."""

        # Initialize schema intelligence (which will ADD to the prompt)
        self.schema_intel = None
        self.base_system_prompt = None
        self._initialize_schema_intelligence()

        # Set up API-specific logging
        self._setup_api_logging()

        # Validate connection
        self._validate_connection()
        
        logging.info("Claude API client initialized successfully")
        logging.info("Default model: {}".format(self.default_model))
        logging.info("Max tokens: {}".format(self.max_tokens))
    
    def _setup_api_logging(self):
        """Set up API-specific logging"""
        # Check if handler already exists
        if api_logger.handlers:
            return
        
        # Get API log file path from config
        logs_dir = self.config.get_logs_directory()
        date_str = now_eastern().strftime('%Y-%m-%d')
        api_log_file = logs_dir / "claude_api_{}.log".format(date_str)
        
        # Create file handler for API operations
        api_handler = logging.FileHandler(api_log_file, mode='a', encoding='utf-8')
        api_handler.setLevel(logging.DEBUG)
        
        # Detailed formatter for API operations
        api_formatter = logging.Formatter(
            '%(asctime)s - CLAUDE_API - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        api_handler.setFormatter(api_formatter)
        
        api_logger.addHandler(api_handler)
        api_logger.setLevel(logging.DEBUG)
        api_logger.propagate = True
    
    def _validate_connection(self):
        """Test API connection with a simple call"""
        try:
            # Simple test call
            test_response = self.client.messages.create(
                model=self.default_model,
                max_tokens=50,
                messages=[{"role": "user", "content": "Test connection. Reply with just 'OK'."}]
            )
            
            # Track usage from test call
            if hasattr(test_response, 'usage'):
                self.usage_tracker.add_usage(
                    self.default_model,
                    test_response.usage.input_tokens,
                    test_response.usage.output_tokens
                )
            
            api_logger.info("API connection validation successful")
            
        except Exception as e:
            error_msg = "Claude API connection validation failed: {}".format(e)
            api_logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _initialize_semantic_cache(self):
        """Initialize semantic function cache"""
        try:
            # Don't initialize here - wait for set_database_connection
            self.semantic_cache = None
            api_logger.info("Semantic cache initialization deferred until database connection available")
        except Exception as e:
            api_logger.warning("Failed to initialize semantic cache: {}".format(e))
            self.semantic_cache = None

    def set_database_connection(self, db_connection):
        """Set database connection and initialize semantic cache"""
        try:
            from .oracle_semantic_cache import SemanticFunctionCache
            import sqlite3
            
            # Get the actual database path from the connection wrapper
            db_path = db_connection.db_path
            
            # Create a direct SQLite connection for the cache
            cache_db = sqlite3.connect(db_path)
            
            # Initialize semantic cache with raw connection
            self.semantic_cache = SemanticFunctionCache(cache_db)
            api_logger.info("Semantic cache initialized with database connection")
            
        except Exception as e:
            api_logger.warning("Failed to initialize semantic cache with DB: {}".format(e))
            self.semantic_cache = None

    def _initialize_schema_intelligence(self):
        """Initialize schema intelligence and enhanced system prompt"""
        try:
            # Import here to avoid circular imports
            from .oracle_data_access import DatabaseConnection
            from .oracle_intelligence import initialize_schema_intelligence
            
            # Create database connection
            db_connection = DatabaseConnection(self.config)
            
            # Initialize schema intelligence
            self.schema_intel = initialize_schema_intelligence(db_connection)
            
            self._build_system_prompt()
            
            api_logger.info("Schema intelligence initialized successfully")
            
        except Exception as e:
            api_logger.warning("Failed to initialize schema intelligence: {}".format(e))
            self.schema_intel = None
            self._build_system_prompt()
    
    def _build_system_prompt(self):
        """Add technical details to the base system prompt (OMNISCIENCE approach)"""
        
        if self.schema_intel:
            # Give Claude EVERYTHING - full schema with all columns
            schema_section = self.schema_intel.get_schema_prompt_section()
            sqlite_guidance = self.schema_intel.get_sqlite_syntax_guidance()
            
            self.system_prompt += f"""

    {schema_section}

    {sqlite_guidance}

    FUNCTION SELECTION:
    - COMPARISON queries: Use compare_to_baseline()
    - UNUSUAL ACTIVITY: Use find_unusual_activity()
    - SECTOR queries: Use get_sector_context()"""
        else:
            # Fallback with key table info
            self.system_prompt += """

    DATABASE TABLES: flow_alerts, option_contracts, symbol_metadata, symbol_baselines
    SQLITE SYNTAX: Use datetime('now'), LOWER() LIKE, not ILIKE/CURRENT_DATE

    FUNCTION SELECTION:
    - COMPARISON queries: Use compare_to_baseline()
    - UNUSUAL ACTIVITY: Use find_unusual_activity()
    - SECTOR queries: Use get_sector_context()"""

    def _extract_thinking_log(self, response_content: str) -> Optional[str]:
        """Extract and log Oracle's thinking process from response"""
        
        import re
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', response_content, re.DOTALL | re.IGNORECASE)
        
        if thinking_match:
            thinking_log = thinking_match.group(1).strip()
            
            # Clean up the thinking log for better readability
            thinking_lines = [line.strip() for line in thinking_log.split('\n') if line.strip()]
            formatted_thinking = '\n    '.join(thinking_lines)
            
            api_logger.info("🧠 ORACLE THINKING PROCESS:")
            api_logger.info("    {}".format(formatted_thinking))
            
            return thinking_log
        
        return None

    def send_message(self, message: str, model: Optional[str] = None, 
                    include_functions: bool = True, conversation_context: Optional[List] = None,
                    max_function_rounds: int = 3) -> Dict[str, Any]:
        """Send message to Claude with intelligent function pre-filtering and multi-step function calling support
        
        Step 4.2 Enhancement: Intelligent function selection based on query classification
        to prevent expensive functions from being used for simple queries.
        
        Args:
            message: User message to send
            model: Optional model override (defaults to config default)
            include_functions: Whether to include function definitions
            conversation_context: Optional conversation history
            max_function_rounds: Maximum rounds of function calls to prevent infinite loops
            
        Returns:
            Comprehensive response including function calls and results
        """
        model = model or self.default_model
        
        try:
                        
            # Build messages array
            messages = []
            
            # Add conversation context if provided
            if conversation_context:
                messages.extend(conversation_context)
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Track all function calls across rounds
            all_function_calls = []
            all_function_results = []
            total_api_time = 0
            round_count = 0
            
            # Step 4.2: Intelligent Function Pre-filtering
            intelligence_result = None
            filtered_functions = AVAILABLE_FUNCTIONS  # Default fallback
            enhanced_system_prompt = self.system_prompt
            
            if include_functions:
                try:
                    # Get query classification and function optimization
                    intelligence_result = classify_and_optimize(message, self.usage_tracker)
                    
                    # Use filtered functions from intelligence system
                    filtered_functions = intelligence_result['filtered_functions']
                    
                    # Enhance system prompt with query-specific guidance
                    query_guidance = []
                    
                    if intelligence_result['cost_guidance']:
                        query_guidance.append(intelligence_result['cost_guidance'])
                    
                    if intelligence_result['schema_guidance']:
                        query_guidance.append(intelligence_result['schema_guidance'])
                    
                    # Add classification insights
                    classification = intelligence_result['classification']
                    query_guidance.append("QUERY CLASSIFICATION: {} complexity, {} type (confidence: {:.2f})".format(
                        classification.complexity_level,
                        classification.query_type,
                        classification.confidence_score
                    ))
                    
                    if query_guidance:
                        # Only add critical guidance, not everything
                        critical_guidance = []
                        
                        if classification.query_type == 'comparison':
                            critical_guidance.append("🎯 COMPARISON: Use compare_to_baseline() not multiple overviews")
                        elif classification.query_type == 'recent_analysis':
                            critical_guidance.append("🎯 UNUSUAL ACTIVITY: Use find_unusual_activity()")
                        elif classification.cost_estimate == 'low':
                            critical_guidance.append("🎯 SIMPLE: Use execute_custom_sql() only")
                        
                        if critical_guidance:
                            enhanced_system_prompt = self.system_prompt + "\n\n" + "\n".join(critical_guidance)
                        else:
                            enhanced_system_prompt = self.system_prompt

                        # Add thinking log instructions for ALL queries (for debugging)
                        if include_functions:  # Show thinking for any query that might use functions
                            enhanced_system_prompt += """
                            THINKING LOG REQUIRED:
                            Before selecting functions, show your reasoning in <thinking> tags:
                            <thinking>
                            Query Analysis:
                            - Type: [simple lookup / comparison / unusual activity / profit modeling / etc.]
                            - Complexity justification: [why this complexity level?]
                            - Data requirements: [what specific information do I need?]
                            Function Selection Strategy:
                            - Primary function: [which function should I use and why?]
                            - Alternative considered: [what other functions could work?]
                            - Cost justification: [why is this function choice appropriate for this query?]
                            - Expected workflow: [single function or multi-step process?]
                            </thinking>
                            Then proceed with your function calls."""
                    
                    # Log intelligence insights
                    api_logger.info("Query intelligence: {} -> {} functions, {} cost, {} confidence".format(
                        classification.complexity_level,
                        len(filtered_functions),
                        classification.cost_estimate,
                        classification.confidence_score
                    ))
                    
                except Exception as e:
                    api_logger.warning("Function intelligence failed, using fallback: {}".format(e))
                    # Continue with default functions if intelligence fails
            
            # Prepare tools (functions) if requested
            tools = []
            if include_functions and filtered_functions:
                for func_name, func_def in filtered_functions.items():
                    tools.append({
                        "name": func_name,
                        "description": func_def["description"],
                        "input_schema": func_def["parameters"]
                    })
            
            # Enhanced system prompt with cost guidance
            enhanced_system_prompt = self.system_prompt
            if intelligence_result and intelligence_result.get('cost_guidance'):
                enhanced_system_prompt = "{}\n\n{}".format(
                    self.system_prompt, 
                    intelligence_result['cost_guidance']
                )
            
            current_messages = messages.copy()
            
            # Multi-round function calling loop
            while round_count < max_function_rounds:
                round_count += 1
                
                # Log the request with intelligence metadata
                function_count = len(tools) if include_functions else 0
                api_logger.info("Function calling round {}/{} - Sending message to {} ({} filtered functions)".format(
                    round_count, max_function_rounds, model, function_count))
                
                start_time = time.time()
                
                # Make API call with enhanced system prompt
                if tools:
                    response = self.client.messages.create(
                        model=model,
                        max_tokens=self.max_tokens,
                        system=enhanced_system_prompt,
                        messages=current_messages,
                        tools=tools
                    )
                else:
                    response = self.client.messages.create(
                        model=model,
                        max_tokens=self.max_tokens,
                        system=enhanced_system_prompt,
                        messages=current_messages
                    )
                
                api_time = time.time() - start_time
                total_api_time += api_time
                
                # Track token usage with function classification metadata
                if hasattr(response, 'usage'):
                    # Determine which function was called for cost tracking
                    called_function = None
                    if intelligence_result and 'classification' in intelligence_result:
                        # Will be updated when we process function calls
                        pass
                    
                    self.usage_tracker.add_usage(
                        model,
                        response.usage.input_tokens,
                        response.usage.output_tokens,
                        function_name=called_function
                    )
                
                # Process the response for this round
                round_result = self._process_response_round(response, model, api_time)
                
                # Log function selection analysis
                if round_result["function_calls"]:
                    for func_call in round_result["function_calls"]:
                        function_name = func_call["function_name"]
                        
                        # Check if function was in filtered set
                        was_filtered = function_name in filtered_functions if filtered_functions != AVAILABLE_FUNCTIONS else True
                        
                        api_logger.info("FUNCTION_SELECTION: Claude chose '{}' (filtered: {})".format(
                            function_name, "YES" if was_filtered else "NO"))
                        
                        # Log classification accuracy for learning
                        if intelligence_result and intelligence_result.get('classification'):
                            expected_type = intelligence_result['classification'].query_type
                            expected_cost = intelligence_result['classification'].cost_estimate
                            
                            api_logger.info("CLASSIFICATION_CHECK: Expected {} ({}), Claude chose {} - Match assessment pending execution".format(
                                expected_type, expected_cost, function_name))

                # Log function selection analysis with thinking context
                if round_result["function_calls"] and "thinking_log" in round_result:
                    api_logger.info("🎯 FUNCTION SELECTION ANALYSIS:")
                    
                    for func_call in round_result["function_calls"]:
                        function_name = func_call["function_name"]
                        
                        # Check if the thinking mentions the function choice
                        thinking_mentions_function = function_name in round_result["thinking_log"]
                        
                        api_logger.info("    Selected: {} | Mentioned in thinking: {}".format(
                            function_name, "YES" if thinking_mentions_function else "NO"))
                
                # Check if Claude wants to make more function calls
                api_logger.info("Round {} complete: {} function calls, content length: {}".format(
                    round_count, len(round_result["function_calls"]), len(round_result["content"])))
                
                # If no function calls in this round, we're done
                if not round_result["function_calls"]:
                    # Final response - update conversation history and return
                    final_content = round_result["content"]
                    
                    self.conversation_history.append({"role": "user", "content": message})
                    self.conversation_history.append({"role": "assistant", "content": final_content})
                    
                    # Include intelligence metadata in response
                    response_metadata = {
                        "success": True,
                        "model": model,
                        "api_time_seconds": round(total_api_time, 3),
                        "timestamp": eastern_isoformat(),
                        "content": final_content,
                        "function_calls": all_function_calls,
                        "function_results": all_function_results,
                        "rounds": round_count,
                        "token_usage": round_result["token_usage"]
                    }
                    
                    # Add Step 4.2 intelligence metadata
                    if intelligence_result:
                        response_metadata["intelligence"] = {
                            "classification": {
                                "complexity_level": intelligence_result['classification'].complexity_level if intelligence_result['classification'] else "unknown",
                                "query_type": intelligence_result['classification'].query_type if intelligence_result['classification'] else "unknown",
                                "confidence_score": intelligence_result['classification'].confidence_score if intelligence_result['classification'] else 0.0,
                                "cost_estimate": intelligence_result['classification'].cost_estimate if intelligence_result['classification'] else "unknown"
                            },
                            "function_filtering": {
                                "original_functions": len(AVAILABLE_FUNCTIONS),
                                "filtered_functions": len(filtered_functions),
                                "reduction_percentage": ((len(AVAILABLE_FUNCTIONS) - len(filtered_functions)) / len(AVAILABLE_FUNCTIONS) * 100) if len(AVAILABLE_FUNCTIONS) > 0 else 0
                            }
                        }
                    
                    return response_metadata
                
                # Execute function calls for this round
                round_function_results = []
                for function_call in round_result["function_calls"]:
                    # Check semantic cache first
                    cached_result = None
                    estimated_cost = 0.01  # Default cost estimate
                    
                    if self.semantic_cache:
                        # Estimate cost for this function call
                        if intelligence_result and 'classification' in intelligence_result:
                            if intelligence_result['classification'].cost_estimate == 'high':
                                estimated_cost = 0.08
                            elif intelligence_result['classification'].cost_estimate == 'medium':
                                estimated_cost = 0.03
                            else:
                                estimated_cost = 0.01
                        
                        # Try to get cached result
                        cached_result = self.semantic_cache.get_or_compute(
                            query=message,
                            function_name=function_call["function_name"],
                            function_params=function_call["parameters"],
                            estimated_cost=estimated_cost
                        )

                    api_logger.info(f"DEBUG: semantic_cache exists = {self.semantic_cache is not None}, cached_result = {cached_result}")

                    if cached_result:  # This will be False for None AND empty dicts
                        # Use cached result
                        function_result = {
                            "success": True,
                            "function_name": function_call["function_name"],
                            "call_id": function_call["call_id"],  # Use CURRENT call_id
                            "cached": True,
                            "execution_time_seconds": 0.001,
                            "timestamp": eastern_isoformat()
                        }
                        function_result.update(cached_result)
                        
                        # CRITICAL FIX: Ensure call_id matches current function call
                        function_result["call_id"] = function_call["call_id"]
                        
                        api_logger.info("Used cached result for {} (${:.4f} saved)".format(
                            function_call["function_name"], estimated_cost))
                    else:
                        # Execute the function normally
                        function_result = self._execute_function_call(function_call)
                        
                        # Store successful results in cache
                        if self.semantic_cache and function_result.get("success"):
                            try:
                                self.semantic_cache.store_result(
                                    query=message,
                                    function_name=function_call["function_name"],
                                    function_params=function_call["parameters"],
                                    result_data=function_result
                                )
                            except Exception as e:
                                api_logger.warning("Failed to cache function result: {}".format(e))
                    
                    round_function_results.append(function_result)
                    all_function_results.append(function_result)
                
                # Track all function calls
                all_function_calls.extend(round_result["function_calls"])
                
                # Prepare next round messages
                # Add assistant's response with tool calls
                assistant_message = {
                    "role": "assistant", 
                    "content": round_result["content"] if round_result["content"] else "I'll call some functions to help with your request."
                }
                
                # For Anthropic API, add tool_use content blocks to assistant message
                if round_result["function_calls"]:
                    assistant_content = []
                    if round_result["content"]:
                        assistant_content.append({"type": "text", "text": round_result["content"]})
                    
                    for func_call in round_result["function_calls"]:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": func_call["call_id"],
                            "name": func_call["function_name"],
                            "input": func_call["parameters"]
                        })
                    
                    assistant_message = {
                        "role": "assistant",
                        "content": assistant_content
                    }
                else:
                    assistant_message = {
                        "role": "assistant",
                        "content": round_result["content"]
                    }
                
                current_messages.append(assistant_message)
                
                # Add tool results as user message
                if round_function_results:
                    tool_results_content = []
                    for func_result in round_function_results:
                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": func_result["call_id"],
                            "content": json.dumps(func_result, indent=2, default=str)
                        })
                    
                    user_message = {
                        "role": "user",
                        "content": tool_results_content
                    }
                    current_messages.append(user_message)
                
                # If this is the last allowed round, force synthesis without functions
                if round_count >= max_function_rounds:
                    api_logger.info("Reached max function rounds ({}), forcing final synthesis".format(max_function_rounds))
                    include_functions = False  # Disable functions for final round
            
            # If we exit the loop without a final response, make one last synthesis call
            api_logger.info("Making final synthesis call after {} rounds".format(round_count))
            
            start_time = time.time()
            final_response = self.client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                messages=current_messages
            )
            api_time = time.time() - start_time
            total_api_time += api_time
            
            # Track final token usage
            if hasattr(final_response, 'usage'):
                self.usage_tracker.add_usage(
                    model,
                    final_response.usage.input_tokens,
                    final_response.usage.output_tokens
                )
            
            # Extract final content
            final_content = []
            for content_block in final_response.content:
                if content_block.type == "text":
                    final_content.append(content_block.text)
            
            final_text = "\n".join(final_content)
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": final_text})
            
            # Build final response with intelligence metadata
            final_response_data = {
                "success": True,
                "model": model,
                "api_time_seconds": round(total_api_time, 3),
                "timestamp": eastern_isoformat(),
                "content": final_text,
                "function_calls": all_function_calls,
                "function_results": all_function_results,
                "rounds": round_count,
                "token_usage": {
                    "input_tokens": getattr(final_response.usage, 'input_tokens', 0),
                    "output_tokens": getattr(final_response.usage, 'output_tokens', 0)
                }
            }
            
            # Add intelligence metadata
            if intelligence_result:
                final_response_data["intelligence"] = {
                    "classification": {
                        "complexity_level": intelligence_result['classification'].complexity_level if intelligence_result['classification'] else "unknown",
                        "query_type": intelligence_result['classification'].query_type if intelligence_result['classification'] else "unknown", 
                        "confidence_score": intelligence_result['classification'].confidence_score if intelligence_result['classification'] else 0.0,
                        "cost_estimate": intelligence_result['classification'].cost_estimate if intelligence_result['classification'] else "unknown"
                    },
                    "function_filtering": {
                        "original_functions": len(AVAILABLE_FUNCTIONS),
                        "filtered_functions": len(filtered_functions),
                        "reduction_percentage": ((len(AVAILABLE_FUNCTIONS) - len(filtered_functions)) / len(AVAILABLE_FUNCTIONS) * 100) if len(AVAILABLE_FUNCTIONS) > 0 else 0
                    }
                }
            
            return final_response_data
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": eastern_isoformat()
            }
            api_logger.error("API call failed: {}".format(e))
            return error_result

    def _process_response_round(self, response, model: str, api_time: float) -> Dict[str, Any]:
        """Process Claude's response for a single round of function calling
        
        Args:
            response: Raw API response from Claude
            model: Model that was used
            api_time: Time taken for API call
            
        Returns:
            Processed response for this round
        """
        result = {
            "success": True,
            "model": model,
            "api_time_seconds": round(api_time, 3),
            "timestamp": eastern_isoformat(),
            "content": "",
            "function_calls": [],
            "token_usage": {
                "input_tokens": getattr(response.usage, 'input_tokens', 0) if hasattr(response, 'usage') else 0,
                "output_tokens": getattr(response.usage, 'output_tokens', 0) if hasattr(response, 'usage') else 0
            }
        }
        
        # Extract text content and function calls
        text_content = []
        
        for content_block in response.content:
            if content_block.type == "text":
                text_content.append(content_block.text)

                # Extract thinking log
                thinking_log = self._extract_thinking_log(content_block.text)
                if thinking_log:
                    result["thinking_log"] = thinking_log

            elif content_block.type == "tool_use":
                # Handle function call
                function_call = {
                    "function_name": content_block.name,
                    "parameters": content_block.input,
                    "call_id": content_block.id
                }
                result["function_calls"].append(function_call)
                
                api_logger.info("Function call: {}({})".format(
                    content_block.name, 
                    ', '.join("{}={}".format(k, v) for k, v in content_block.input.items())
                ))
        
        result["content"] = "\n".join(text_content)
        return result
    
    def _process_response(self, response, model: str, api_time: float) -> Dict[str, Any]:
        """Process Claude's response and handle function calls
        
        Args:
            response: Raw API response from Claude
            model: Model that was used
            api_time: Time taken for API call
            
        Returns:
            Processed response with function results
        """
        result = {
            "success": True,
            "model": model,
            "api_time_seconds": round(api_time, 3),
            "timestamp": eastern_isoformat(),
            "content": "",
            "function_calls": [],
            "function_results": [],
            "token_usage": {
                "input_tokens": getattr(response.usage, 'input_tokens', 0) if hasattr(response, 'usage') else 0,
                "output_tokens": getattr(response.usage, 'output_tokens', 0) if hasattr(response, 'usage') else 0
            }
        }
        
        # Extract text content
        text_content = []
        
        for content_block in response.content:
            if content_block.type == "text":
                text_content.append(content_block.text)
            elif content_block.type == "tool_use":
                # Handle function call
                function_call = {
                    "function_name": content_block.name,
                    "parameters": content_block.input,
                    "call_id": content_block.id
                }
                result["function_calls"].append(function_call)
                
                api_logger.info("Function call: {}({})".format(
                    content_block.name, 
                    ', '.join("{}={}".format(k, v) for k, v in content_block.input.items())
                ))
                
                api_logger.info("Query classification: Function '{}' selected for query: '{}'".format(
                    content_block.name, message[:100]))

                # Execute the function
                function_result = self._execute_function_call(function_call)
                result["function_results"].append(function_result)
        
        result["content"] = "\n".join(text_content)
        
        # If there were function calls, we ALWAYS need a follow-up call to Claude
        # to synthesize the function results into a final response
        if result["function_calls"]:
            follow_up_result = self._synthesize_function_results(result, model)
            if follow_up_result:
                result["content"] = follow_up_result["content"]
                result["synthesis_call"] = follow_up_result
            else:
                # If synthesis fails, at least show we had function calls
                result["content"] += "\n\n[Function calls completed but synthesis failed]"
        
        return result
    
    def _execute_function_call(self, function_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a function call from Claude
        
        Args:
            function_call: Function call information
            
        Returns:
            Function execution result
        """
        try:
            start_time = time.time()

            # Which function is being called and why
            api_logger.info("Function selection: {} for params: {}".format(
                function_call["function_name"], 
                json.dumps(function_call["parameters"], default=str)[:200]  # First 200 chars
            ))
            
            # Execute the function
            function_result = execute_function(
                function_call["function_name"],
                function_call["parameters"]
            )
            
            execution_time = time.time() - start_time

            # How long it took and what came back
            result_size = 0
            if isinstance(function_result.get('data'), list):
                result_size = len(function_result['data'])
            elif 'unusual_flows' in function_result:
                result_size = len(function_result.get('unusual_flows', []))
            
            api_logger.info("Function {} completed in {:.3f}s - Success: {}, Results: {}".format(
                function_call["function_name"],
                execution_time,
                function_result.get("success", False),
                result_size
            ))
            
            # Add execution metadata
            function_result["execution_time_seconds"] = round(execution_time, 3)
            function_result["call_id"] = function_call["call_id"]
            
            api_logger.info("Function executed: {} in {:.3f}s (success: {})".format(
                function_call["function_name"], execution_time, function_result.get("success", False)
            ))
            
            return function_result
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "function_name": function_call["function_name"],
                "call_id": function_call["call_id"],
                "timestamp": eastern_isoformat()
            }
            api_logger.error("Function execution failed: {}".format(e))
            return error_result
    
    def _synthesize_function_results(self, initial_result: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        """Make a follow-up call to Claude to synthesize function results into a response
        
        Args:
            initial_result: Result from initial call with function calls
            model: Model to use for synthesis
            
        Returns:
            Synthesis result or None if it fails
        """
        try:
            # Build function results message
            function_results_text = []
            
            for func_result in initial_result["function_results"]:
                function_results_text.append("Function {} results:\n{}".format(
                    func_result.get("function_name", "unknown"),
                    json.dumps(func_result, indent=2, default=str)
                ))
            
            synthesis_message = (
                "Based on the function call results below, please provide a comprehensive analysis "
                "and answer to the user's question. Function results:\n\n{}"
            ).format("\n\n".join(function_results_text))
            
            # Make synthesis call (without functions to avoid loops)
            synthesis_response = self.client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                system=enhanced_system_prompt,
                messages=[{"role": "user", "content": synthesis_message}]
            )
            
            # Track token usage
            if hasattr(synthesis_response, 'usage'):
                self.usage_tracker.add_usage(
                    model,
                    synthesis_response.usage.input_tokens,
                    synthesis_response.usage.output_tokens
                )
            
            # Extract content
            synthesis_content = []
            for content_block in synthesis_response.content:
                if content_block.type == "text":
                    synthesis_content.append(content_block.text)
            
            synthesis_text = "\n".join(synthesis_content)
            api_logger.info("Function results synthesized successfully - {} chars".format(len(synthesis_text)))

            if not synthesis_text.strip():
                api_logger.warning("Synthesis produced empty content!")
                
            return {
                "content": synthesis_text,
                "token_usage": {
                    "input_tokens": getattr(synthesis_response.usage, 'input_tokens', 0),
                    "output_tokens": getattr(synthesis_response.usage, 'output_tokens', 0)
                }
            }
            
        except Exception as e:
            api_logger.error("Function synthesis failed: {}".format(e))
            return None
    
    def clear_conversation_history(self):
        """Clear conversation history for a fresh start"""
        self.conversation_history = []
        logging.info("Conversation history cleared")
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get current conversation history"""
        return self.conversation_history.copy()
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get current schema information"""
        
        if not self.schema_intel:
            return {"error": "Schema intelligence not available"}
        
        return {
            "available_tables": self.schema_intel.get_available_tables(),
            "table_count": len(self.schema_intel.get_available_tables()),
            "last_refresh": self.schema_intel.last_refresh.isoformat() if self.schema_intel.last_refresh else None,
            "schema_cache_size": len(self.schema_intel.schema_cache)
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get semantic cache performance statistics"""
        if not self.semantic_cache:
            return {"error": "Semantic cache not available"}
        
        return self.semantic_cache.get_cache_stats()

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get comprehensive usage summary with cost information"""
        usage_summary = self.usage_tracker.get_session_summary()
        
        # Add current model information
        usage_summary["default_model"] = self.default_model
        usage_summary["max_tokens_per_request"] = self.max_tokens
        
        # Format cost for display
        usage_summary["formatted_cost"] = "${:.4f}".format(usage_summary["estimated_total_cost"])
        
        # Add schema intelligence status
        usage_summary["schema_intelligence_enabled"] = self.schema_intel is not None
        if self.schema_intel:
            usage_summary["schema_info"] = self.get_schema_info()

        return usage_summary
    
    def estimate_cost_for_message(self, message: str, model: Optional[str] = None) -> float:
        """Estimate cost for a message before sending (rough estimate)
        
        Args:
            message: Message to estimate cost for
            model: Model to use for estimation
            
        Returns:
            Estimated cost in USD
        """
        model = model or self.default_model
        
        # Rough token estimation (very approximate)
        estimated_input_tokens = len(message.split()) * 1.3  # Rough words-to-tokens ratio
        estimated_output_tokens = 500  # Conservative estimate for response
        
        return self.usage_tracker.calculate_cost(model, int(estimated_input_tokens), estimated_output_tokens)

    def get_current_model(self):
        """Get the currently configured model"""
        return self.default_model

    def switch_model(self, new_model):
        """Switch the default model
        
        Args:
            new_model: New model identifier to use
        """
        self.default_model = new_model
        logging.info("Switched default model to: {}".format(new_model))



# Test functionality if run directly
if __name__ == "__main__":
    print("Claude API Client Test")
    print("=" * 50)
    
    try:
        from oracle.oracle_config import OracleConfig
        
        # Initialize config and client
        config = OracleConfig()
        client = ClaudeClient(config)
        
        print("✅ Client initialized successfully")
        print("Default model: {}".format(client.default_model))
        
        # Test a simple message
        print("\nTesting simple message...")
        response = client.send_message(
            "Hello! This is a test. Please respond briefly.",
            include_functions=False
        )
        
        if response["success"]:
            print("✅ Simple message test passed")
            print("Response: {}".format(response["content"][:100]))
            print("Tokens: {}in/{}out".format(
                response["token_usage"]["input_tokens"],
                response["token_usage"]["output_tokens"]
            ))
        else:
            print("❌ Simple message test failed: {}".format(response.get("error")))
        
        # Test function calling
        print("\nTesting function calling...")
        response = client.send_message(
            "What symbols are available? Show me 3 examples.",
            include_functions=True
        )
        
        if response["success"]:
            print("✅ Function calling test passed")
            print("Function calls made: {}".format(len(response["function_calls"])))
            for func_call in response["function_calls"]:
                print("  - {}".format(func_call["function_name"]))
        else:
            print("❌ Function calling test failed: {}".format(response.get("error")))
        
        # Show usage summary
        usage = client.get_usage_summary()
        print("\nUsage Summary:")
        print("  Total calls: {}".format(usage["total_api_calls"]))
        print("  Total tokens: {} in + {} out".format(
            usage["total_input_tokens"], usage["total_output_tokens"]
        ))
        print("  Estimated cost: {}".format(usage["formatted_cost"]))
        
        print("\n✅ Claude API client ready for Oracle integration!")
        
    except Exception as e:
        print("❌ Test failed: {}".format(e))
        import traceback
        traceback.print_exc()
