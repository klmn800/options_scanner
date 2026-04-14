#!/usr/bin/env python3
"""
Flow Monitor Configuration (fm_config.py)
-----------------------------------------
Simple configuration loader for Flow Monitor operations.
Provides settings and initializes the Tradier client.

Handles:
- Configuration loading from root config.json
- Tradier client initialization (direct, no shared dependencies)
- Database path resolution
- Collection and alert parameters

No complex logic - just reliable configuration management.

Author: Ben (with assistance from Claude)
Date: 2025-06-26
"""

import json
import logging
import os
import sys
from pathlib import Path
import threading

# Global shutdown event for graceful shutdown
shutdown_event = threading.Event()

class FMConfig:
    def __init__(self, config_path=None):
        """Initialize configuration and Tradier client
        
        Args:
            config_path: Optional path to config.json. If None, uses default root location.
        """
        self.config_path = config_path or self._find_root_config()
        self.config = self._load_config()
        self.flow_monitor_config = self.config.get('flow_monitor', {})
        self._tradier_client = None
        
        # Initialize Tradier client immediately
        self._create_tradier_client()
    
    def _find_root_config(self):
        """Find config.json in the root options_scanner directory"""
        # Start from current file location and work up
        current_dir = Path(__file__).parent
        root_indicators = ['config.json', 'data', 'core']
        
        # Try current directory and parent directories
        for _ in range(5):  # Reasonable limit
            if (current_dir / 'config.json').exists():
                config_files = list(current_dir.glob('config.json'))
                if config_files and any((current_dir / indicator).exists() for indicator in root_indicators):
                    return str(config_files[0])
            current_dir = current_dir.parent
        
        # Relative fallback instead of hardcoded
        project_root = Path(__file__).parent.parent.parent
        fallback_config = project_root / 'config.json'
        return str(fallback_config)
    
    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Validate required sections
            required_sections = ['tradier', 'flow_monitor']
            for section in required_sections:
                if section not in config:
                    raise ValueError("Missing required configuration section: {}".format(section))
            
            # Validate required Tradier fields
            tradier_config = config['tradier']
            if 'api_key' not in tradier_config:
                raise ValueError("Missing required field: tradier.api_key")
            
            logging.debug("Configuration loaded from: {}".format(self.config_path))
            return config
            
        except FileNotFoundError:
            logging.error("Configuration file not found: {}".format(self.config_path))
            raise
        except json.JSONDecodeError as e:
            logging.error("Invalid JSON in configuration file: {}".format(e))
            raise
        except Exception as e:
            logging.error("Failed to load configuration: {}".format(e))
            raise
    
    def _create_tradier_client(self):
        """Initialize Tradier API client directly"""
        # Get core directory using relative path
        current_file = os.path.abspath(__file__)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        core_dir = os.path.join(project_root, 'core')
        tools_dir = os.path.join(project_root, 'tools')  # ADD THIS

        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
            
        if tools_dir not in sys.path:  # ADD THIS
            sys.path.insert(0, tools_dir)  # ADD THIS

        # Path setup complete (no debug output in production)
        
        try:
            from tradier_api import TradierDataClient
            
            # Create client with minimal cache directory
            cache_dir = Path(__file__).parent / 'cache'
            cache_dir.mkdir(exist_ok=True)
            
            self._tradier_client = TradierDataClient(self.config, str(cache_dir))
            
            # Test connection
            if self._tradier_client.test_connection():
                logging.debug("Tradier API client initialized successfully")
            else:
                logging.error("Failed to connect to Tradier API")
                raise ConnectionError("Tradier API connection test failed")
                
        except ImportError as e:
            logging.error("Failed to import TradierDataClient: {}".format(e))
            raise
        except Exception as e:
            logging.error("Failed to initialize Tradier client: {}".format(e))
            raise
    
    @property
    def tradier_client(self):
        """Return initialized Tradier client"""
        if not hasattr(self, '_tradier_client') or self._tradier_client is None:
            raise RuntimeError("Tradier client not initialized")
        return self._tradier_client

    @property
    def database_path(self):
        """Return path to datalake.db"""
        root_dir = Path(self.config_path).parent
        return str(root_dir / 'data' / 'datalake.db')
             
    @property
    def alerts_db_path(self):
        """Return path to fm_alerts.db (in flow_monitor folder)"""
        alerts_path = Path(__file__).parent / 'fm_alerts.db'
        return str(alerts_path)

    def get_dip_thresholds(self):
        """Return dip detection threshold parameters for z-score system

        Used by fm_watchlist.py to detect buy-the-dip opportunities using
        volatility-normalized z-scores with range-based detection.

        Only triggers for BUILDING sentiment alerts (requires next-day OI data).

        Returns:
            dict: Dip detection configuration with keys:
                - use_zscore_detection: Enable z-score logic (default: True)
                - zscore_min: Minimum z-score for dip (shallow end, default: -0.10)
                - zscore_max: Maximum z-score for dip (deep end, default: -0.20)
                - fallback_min_pct: Minimum % drop when no RV (default: -1.5)
                - fallback_max_pct: Maximum % drop when no RV (default: -3.5)
                - rv_cap: Cap RV at this value to prevent meme stock chaos (default: 0.12)
                - min_rv_for_zscore: Below this RV, use percentage fallback (default: 0.05)
                - require_building_sentiment: Only alert on BUILDING sentiment (default: True)
        """
        defaults = {
            'use_zscore_detection': True,
            'zscore_min': -0.10,
            'zscore_max': -0.20,
            'fallback_min_pct': -1.5,
            'fallback_max_pct': -3.5,
            'rv_cap': 0.12,
            'min_rv_for_zscore': 0.05,
            'require_building_sentiment': True
        }

        dip_params = self.flow_monitor_config.get('dip_detection', {})
        defaults.update(dip_params)

        return defaults



# Quick Test
if __name__ == "__main__":
    # Test configuration loading
    logging.basicConfig(level=logging.INFO)

    try:
        config = FMConfig()
        print("✅ Configuration loaded successfully")
        print("   Database path: {}".format(config.database_path))
        print("   Alerts DB path: {}".format(config.alerts_db_path))
        print("   Dip thresholds: {}".format(config.get_dip_thresholds()))

        # Test Tradier client
        client = config.tradier_client
        print("✅ Tradier client accessible")

    except Exception as e:
        print("❌ Configuration test failed: {}".format(e))
        sys.exit(1)
