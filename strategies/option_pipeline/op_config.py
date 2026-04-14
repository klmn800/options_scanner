#!/usr/bin/env python3
"""
Open Interest Delta Configuration (oid_config.py)
------------------------------------------------
Configuration loader for Open Interest Delta operations.
Provides OID-specific settings and initializes the Tradier client.

Handles:
- Configuration loading from root config.json
- Tradier client initialization (immediate, not lazy)
- Database path resolution (uses data/datalake.db)
- OID collection timing and universe parameters
- Storage and retention settings

No complex logic - just reliable configuration management for OID operations.

Author: Ben (with assistance from Claude)
Date: 2025-07-29
"""

import json
import logging
import os
import sys
from pathlib import Path
import threading

# Global shutdown event for graceful shutdown
shutdown_event = threading.Event()

class OIDConfig:
    def __init__(self, config_path=None):
        """Initialize configuration and Tradier client
        
        Args:
            config_path: Optional path to config.json. If None, uses default root location.
        """
        self.config_path = config_path or self._find_root_config()
        self.config = self._load_config()
        self.oid_config = self.config.get('open_interest_delta', {})
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
            required_sections = ['tradier', 'open_interest_delta']
            for section in required_sections:
                if section not in config:
                    raise ValueError("Missing required configuration section: {}".format(section))
            
            # Validate required Tradier fields
            tradier_config = config['tradier']
            if 'api_key' not in tradier_config:
                raise ValueError("Missing required field: tradier.api_key")
            
            # Validate OID is enabled
            if not config['open_interest_delta'].get('enabled', False):
                raise ValueError("Open Interest Delta module is disabled in configuration")
            
            logging.debug("Configuration loaded from: {}".format(self.config_path))
            return config
            
        except FileNotFoundError:
            logging.error("Configuration file not found: {}".format(self.config_path))
            raise
        except json.JSONDecodeError as e:
            logging.error("Invalid JSON in configuration file: {}".format(e))
            raise
        except Exception as e:
            logging.error("Failed to load OID configuration: {}".format(e))
            raise
    
    def _create_tradier_client(self):
        """Initialize Tradier API client directly"""
        # Get core directory using relative path
        current_file = os.path.abspath(__file__)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        core_dir = os.path.join(project_root, 'core')
        tools_dir = os.path.join(project_root, 'tools')

        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
            
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

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
        """Return path to datalake.db (consolidated database)"""
        root_dir = Path(self.config_path).parent
        return str(root_dir / 'data' / 'datalake.db')
             
    @property
    def collection_time(self):
        """Return scheduled collection time (e.g., '18:00' for 6 PM ET)"""
        return self.oid_config.get('collection_time', '18:00')
    
    @property
    def universe_size(self):
        """Return expected universe size for collection planning"""
        try:
            from core.symbols_klmn800 import get_specialty_list
            return len(get_specialty_list('klmn_800'))
        except ImportError:
            # Fallback if import fails
            return self.oid_config.get('universe_size', 741)  # Approximate KLMN 800 count
    
    def get_collection_params(self):
        """Return OID collection parameters as dictionary"""
        defaults = {
            'max_dte': 60,
            'min_dte': 0,
            'strike_range_percent': 20,
            'batch_size': 100,               # Collection buffer batch size
            'rollup_batch_size': 100,        # Symbol rollup processing batch size  
            'analysis_batch_size': 50,       # Gap analysis batch size (memory intensive)
            'momentum_batch_size': 1000,     # Momentum calculation batch size
            'storage_batch_size': 5000,      # Database bulk insert batch size
            'update_batch_size': 1000,       # Database update batch size
            'rate_limit_per_minute': 120
        }
        
        # Override with config values if present
        collection_params = self.oid_config.get('collection_params', {})
        defaults.update(collection_params)
        
        return defaults
    
    def get_storage_params(self):
        """Return storage and retention parameters"""
        defaults = {
            'retention_days': 365,
            'compression_after_days': 30
        }
        
        storage_params = self.oid_config.get('storage', {})
        defaults.update(storage_params)
        
        return defaults
    
    @property
    def is_enabled(self):
        """Return whether OID module is enabled"""
        return self.oid_config.get('enabled', False)


# Quick Test
if __name__ == "__main__":
    # Test configuration loading
    logging.basicConfig(level=logging.INFO)
    
    try:
        config = OIDConfig()
        print("✅ OID Configuration loaded successfully")
        print("   Database path: {}".format(config.database_path))
        print("   Collection time: {}".format(config.collection_time))
        print("   Universe size: {}".format(config.universe_size))
        print("   Enabled: {}".format(config.is_enabled))
        print("   Collection params: {}".format(config.get_collection_params()))
        print("   Storage params: {}".format(config.get_storage_params()))
        
        # Test Tradier client
        client = config.tradier_client
        print("✅ OID Tradier client accessible")
        
    except Exception as e:
        print("❌ OID Configuration test failed: {}".format(e))
        sys.exit(1)

