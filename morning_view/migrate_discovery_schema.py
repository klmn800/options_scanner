#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate discovery_analysis table to improved schema

Changes:
1. Remove redundant cache_key, use trade_date as PRIMARY KEY
2. Fix created_at timestamp format (remove microseconds, use space separator)
3. Add top-level cost tracking columns
4. Separate market context into proper columns
5. Extract analysis_text for readability
6. Keep optional structured fields (recommendations_json, raw_response)
"""

import sys
import sqlite3
import json
import os
from datetime import datetime

# Fix Windows console encoding for emojis
sys.stdout.reconfigure(encoding='utf-8')


def migrate_discovery_analysis():
    """Migrate discovery_analysis to new schema"""

    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'analysis_cache.db')

    print(f"Migrating discovery_analysis in {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Get existing data
    print("Reading existing data...")
    cursor.execute("SELECT * FROM discovery_analysis")
    old_rows = cursor.fetchall()
    print(f"Found {len(old_rows)} existing analyses")

    # 2. Create new table with improved schema
    print("Creating new table schema...")
    cursor.execute("DROP TABLE IF EXISTS discovery_analysis_new")
    cursor.execute("""
        CREATE TABLE discovery_analysis_new (
            trade_date TEXT PRIMARY KEY,

            -- Core analysis (clean text like symbol_ai_council)
            analysis_text TEXT NOT NULL,

            -- Metadata
            total_analyzed INTEGER NOT NULL,
            market_direction TEXT,
            market_regime TEXT,

            -- Cost tracking (top-level for easy queries)
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,

            -- Optional: Full structured data
            recommendations_json TEXT,
            raw_response TEXT,

            -- Timestamp at end
            created_at TEXT NOT NULL
        )
    """)

    # 3. Transform and insert old data
    print("Transforming data to new schema...")
    for row in old_rows:
        # Parse old analysis_json
        analysis_data = json.loads(row['analysis_json'])

        # Extract components
        trade_date = row['trade_date']
        total_analyzed = row['total_analyzed']

        # Fix timestamp format
        old_timestamp = row['created_at']
        if 'T' in old_timestamp:
            # Convert ISO format to standard: "2025-10-21T17:39:43.419189" -> "2025-10-21 17:39:43"
            dt = datetime.fromisoformat(old_timestamp)
            created_at = dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            created_at = old_timestamp

        # Extract market context
        market_ctx = analysis_data.get('market_context', {})
        market_direction = market_ctx.get('market_direction')
        market_regime = market_ctx.get('market_regime')

        # Extract cost data
        usage = analysis_data.get('usage', {})
        input_tokens = usage.get('input_tokens')
        output_tokens = usage.get('output_tokens')
        cost_usd = usage.get('cost_usd')

        # Build clean analysis_text (formatted prose like symbol_ai_council)
        recommendations = analysis_data.get('recommendations', [])
        analysis_text_parts = []

        for rec in recommendations:
            symbol = rec.get('symbol', 'N/A')
            rank = rec.get('rank', '?')
            reasoning = rec.get('reasoning', '')
            key_factors = rec.get('key_factors', [])
            risk_note = rec.get('risk_note', '')

            text_block = f"{rank}. {symbol}\n{reasoning}\n"
            if key_factors:
                text_block += f"Key Factors: {', '.join(key_factors)}\n"
            if risk_note:
                text_block += f"Risk: {risk_note}\n"

            analysis_text_parts.append(text_block)

        analysis_text = "\n".join(analysis_text_parts) if analysis_text_parts else "No recommendations"

        # Keep structured recommendations for programmatic access
        recommendations_json = json.dumps(recommendations) if recommendations else None

        # Keep raw response for debugging
        raw_response = analysis_data.get('raw_analysis')

        # Insert transformed data
        cursor.execute("""
            INSERT INTO discovery_analysis_new (
                trade_date, analysis_text, total_analyzed,
                market_direction, market_regime,
                input_tokens, output_tokens, cost_usd,
                recommendations_json, raw_response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_date, analysis_text, total_analyzed,
            market_direction, market_regime,
            input_tokens, output_tokens, cost_usd,
            recommendations_json, raw_response, created_at
        ))

    # 4. Replace old table
    print("Replacing old table...")
    cursor.execute("DROP TABLE discovery_analysis")
    cursor.execute("ALTER TABLE discovery_analysis_new RENAME TO discovery_analysis")

    # 5. Create index on trade_date for fast lookups
    cursor.execute("CREATE INDEX idx_discovery_date ON discovery_analysis(trade_date DESC)")

    conn.commit()

    # 6. Verify migration
    cursor.execute("SELECT COUNT(*) as count FROM discovery_analysis")
    new_count = cursor.fetchone()['count']

    print(f"\n✅ Migration complete!")
    print(f"   Migrated {new_count} rows")
    print(f"   Schema updated successfully")

    # Show sample
    cursor.execute("SELECT trade_date, total_analyzed, cost_usd, created_at FROM discovery_analysis ORDER BY trade_date DESC LIMIT 1")
    sample = cursor.fetchone()
    if sample:
        print(f"\n📊 Sample row:")
        print(f"   Date: {sample['trade_date']}")
        print(f"   Symbols analyzed: {sample['total_analyzed']}")
        print(f"   Cost: ${sample['cost_usd']:.4f}" if sample['cost_usd'] else "   Cost: N/A")
        print(f"   Created: {sample['created_at']}")

    conn.close()

    return True


if __name__ == "__main__":
    try:
        migrate_discovery_analysis()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
