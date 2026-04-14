-- Master Migration Script
-- Earnings Intelligence System - Complete Database Schema
-- Runs all table creation scripts in dependency order
-- Part of: Earnings Intelligence System
-- Author: Ben (with Claude)
-- Date: 2025-10-10 (Updated)
--
-- Changes from original design:
-- - Merged earnings_notes into earnings_events (notes, tags, note_type, sentiment columns)
-- - Moved correlation_strength + sample_size together in sector_effects (analyst clarity)
-- - 5 tables total (down from 6)
--
-- Usage:
--   sqlite3 data/datalake.db < strategies/earnings_intel/000_run_all_migrations.sql
--
-- Or via Python:
--   import sqlite3
--   with open('strategies/earnings_intel/000_run_all_migrations.sql') as f:
--       conn.execute(f.read())

-- ==============================================================================
-- TABLE 1: earnings_events (Foundation + Trading Journal)
-- ==============================================================================
-- Immutable archive of all earnings events - never delete, only insert
-- Includes human insights (notes, tags) merged into same table

CREATE TABLE IF NOT EXISTS earnings_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    estimated_eps REAL,
    actual_eps REAL,
    eps_surprise_pct REAL,
    earnings_time TEXT,
    source TEXT,
    is_backfilled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Human Insights (Trading Journal)
    notes TEXT,
    tags TEXT,
    note_type TEXT,
    sentiment TEXT,

    UNIQUE(symbol, earnings_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_events_symbol ON earnings_events(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_events_date ON earnings_events(earnings_date);
CREATE INDEX IF NOT EXISTS idx_earnings_events_symbol_date ON earnings_events(symbol, earnings_date);
CREATE INDEX IF NOT EXISTS idx_earnings_events_fiscal ON earnings_events(fiscal_year, fiscal_quarter);

-- ==============================================================================
-- TABLE 2: earnings_snapshots (Time Series Data)
-- ==============================================================================
-- Point-in-time IV and price observations around earnings (7 days before, 3 after)

CREATE TABLE IF NOT EXISTS earnings_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES earnings_events(event_id),
    symbol TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    days_from_earnings INTEGER,
    snapshot_type TEXT,
    close_price REAL,
    volume INTEGER,
    iv_30dte REAL,
    iv_front_month REAL,
    iv_45dte REAL,
    total_open_interest INTEGER,
    put_call_ratio REAL,
    is_primary_symbol BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, symbol, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_event ON earnings_snapshots(event_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol ON earnings_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_date ON earnings_snapshots(symbol, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_days_from ON earnings_snapshots(days_from_earnings);
CREATE INDEX IF NOT EXISTS idx_snapshots_type ON earnings_snapshots(snapshot_type);

-- ==============================================================================
-- TABLE 3: earnings_moves (Derived Metrics)
-- ==============================================================================
-- Calculated price moves and IV changes - can be regenerated anytime

CREATE TABLE IF NOT EXISTS earnings_moves (
    move_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES earnings_events(event_id),
    symbol TEXT NOT NULL,
    move_1day_pct REAL,
    move_2day_pct REAL,
    move_3day_pct REAL,
    move_5day_pct REAL,
    max_intraday_move_pct REAL,
    move_direction TEXT,
    iv_buildup_pct REAL,
    iv_collapse_pct REAL,
    iv_recovery_pct REAL,
    iv_crush_severity TEXT,
    expected_move_pct REAL,
    move_vs_expected_pct REAL,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_moves_event ON earnings_moves(event_id);
CREATE INDEX IF NOT EXISTS idx_moves_symbol ON earnings_moves(symbol);
CREATE INDEX IF NOT EXISTS idx_moves_direction ON earnings_moves(move_direction);
CREATE INDEX IF NOT EXISTS idx_moves_crush_severity ON earnings_moves(iv_crush_severity);

-- ==============================================================================
-- TABLE 4: industry_peer_mappings (Peer Relationships)
-- ==============================================================================
-- Defines who moves together - industry-based groupings with manual leader assignment

CREATE TABLE IF NOT EXISTS industry_peer_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry TEXT NOT NULL,
    symbol TEXT NOT NULL,
    is_industry_leader BOOLEAN DEFAULT FALSE,
    peer_type TEXT,
    weight REAL DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(industry, symbol)
);

CREATE INDEX IF NOT EXISTS idx_peer_mappings_industry ON industry_peer_mappings(industry);
CREATE INDEX IF NOT EXISTS idx_peer_mappings_symbol ON industry_peer_mappings(symbol);
CREATE INDEX IF NOT EXISTS idx_peer_mappings_leader ON industry_peer_mappings(is_industry_leader);
CREATE INDEX IF NOT EXISTS idx_peer_mappings_active ON industry_peer_mappings(is_active);

-- ==============================================================================
-- TABLE 5: earnings_sector_effects (The Arbitrage Signal)
-- ==============================================================================
-- Captures sector sympathy and IV arbitrage opportunities

CREATE TABLE IF NOT EXISTS earnings_sector_effects (
    effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_event_id INTEGER NOT NULL REFERENCES earnings_events(event_id),
    primary_symbol TEXT NOT NULL,
    peer_symbol TEXT NOT NULL,
    industry TEXT,
    primary_iv_buildup_pct REAL,
    peer_iv_buildup_pct REAL,
    iv_arbitrage_delta REAL,
    primary_move_pct REAL,
    peer_move_pct REAL,

    -- CORRELATION METRICS (ANALYSTS: Always check sample_size with correlation_strength!)
    correlation_strength REAL,
    sample_size INTEGER,

    expected_peer_move_pct REAL,
    actual_vs_expected_diff REAL,
    arbitrage_quality TEXT,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(primary_event_id, peer_symbol)
);

CREATE INDEX IF NOT EXISTS idx_sector_effects_primary ON earnings_sector_effects(primary_symbol);
CREATE INDEX IF NOT EXISTS idx_sector_effects_peer ON earnings_sector_effects(peer_symbol);
CREATE INDEX IF NOT EXISTS idx_sector_effects_industry ON earnings_sector_effects(industry);
CREATE INDEX IF NOT EXISTS idx_sector_effects_quality ON earnings_sector_effects(arbitrage_quality);
CREATE INDEX IF NOT EXISTS idx_sector_effects_event ON earnings_sector_effects(primary_event_id);

-- ==============================================================================
-- MIGRATION COMPLETE
-- ==============================================================================
-- All 5 tables created successfully
-- Note: earnings_notes merged into earnings_events (notes/tags columns)
--
-- Next steps:
-- 1. Populate industry_peer_mappings from symbol_metadata
-- 2. Backfill earnings_events from earnings_historical or yfinance
-- 3. Start daily snapshot collection
