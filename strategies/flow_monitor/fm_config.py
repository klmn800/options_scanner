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
import time
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
                err = ConnectionError("Tradier API connection test failed")
                # Network-class failures (DNS, refused, timeout) during the probe, as opposed
                # to auth/HTTP errors. create_with_network_wait() uses this to decide whether
                # the failure is worth waiting out.
                err.network_errors = getattr(self._tradier_client.api, 'connection_errors', 0)
                raise err
                
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

    def get_roll_detection_config(self):
        """Return roll detection configuration for identifying position rolls

        Detects when an alert's volume pattern matches a position roll
        (closing one strike, opening another). Tags alerts with context
        rather than suppressing them.

        Returns:
            dict: Roll detection configuration with keys:
                - enabled: Enable roll detection (default: True)
                - vol_match_threshold: Min volume match ratio to flag as roll (default: 0.85)
                - voi_closing_threshold: V/OI below this indicates closing leg (default: 1.5)
                - expiration_window_days: Max days between expirations for cross-exp rolls (default: 30)
        """
        defaults = {
            'enabled': True,
            'vol_match_threshold': 0.85,
            'voi_closing_threshold': 1.5,
            'expiration_window_days': 30,
        }

        roll_params = self.flow_monitor_config.get('roll_detection', {})
        defaults.update(roll_params)

        return defaults


def create_with_network_wait(factory, label, max_wait_seconds=600, retry_interval=15, stop_event=None):
    """Call factory() (FMConfig, FMCollector, ...), waiting out network outages at startup.

    test_connection() already retries for ~45s, which covers Tradier gateway blips but not
    ISP/DNS drops: on 2026-10-06 api.tradier.com stopped resolving for 1-2 minutes at a time,
    FM init at 9:15 raised, and the whole main.py run died until a manual restart.

    Only a ConnectionError whose probe hit network-class errors (DNS, refused, timeout) is
    retried, for up to max_wait_seconds. Auth/HTTP/config failures re-raise immediately.
    """
    deadline = time.time() + max_wait_seconds
    round_num = 0
    while True:
        try:
            result = factory()
            if round_num > 0:
                logging.warning("{} initialized after network outage ({} retry rounds)".format(label, round_num))
            return result
        except ConnectionError as e:
            if getattr(e, 'network_errors', 0) <= 0:
                raise
            if stop_event is not None and stop_event.is_set():
                raise
            if time.time() >= deadline:
                logging.error("{} init: network still unreachable after {}s - giving up".format(
                    label, max_wait_seconds))
                raise
            round_num += 1
            logging.warning("{} init: Tradier unreachable (network error) - retrying in {}s "
                            "(round {}, up to {}s total)".format(label, retry_interval, round_num, max_wait_seconds))
            if stop_event is not None:
                if stop_event.wait(retry_interval):
                    raise
            else:
                time.sleep(retry_interval)


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
