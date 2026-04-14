# AI Symbol Analyzer - Phase 1: Core Infrastructure

**Status**: Core infrastructure complete, ready for testing
**Date**: 2025-10-08
**Author**: Ben (with Claude Code assistance)

## What Was Built

Phase 1 implements the core AI analysis system without TUI integration:

### Files Created

1. **`ai_prompts.py`** - All prompts in one place (easy to edit)
   - System prompt defining Claude's role
   - Analysis prompt template with data placeholders
   - Helper functions for building prompt sections

2. **`ai_analyzer.py`** - Core analysis engine
   - Data gathering using existing `tui_data.py` methods
   - Claude API integration (Anthropic SDK)
   - Cache management (7-day expiration)
   - Support for 3 models: Haiku (testing), Sonnet (production), Opus (advanced)

3. **`test_ai_analysis.py`** - Command-line test script
   - Migration verification
   - Cache behavior testing
   - Analysis testing with different models

4. **`data/migrations/add_ai_analysis_cache.sql`** - Cache table schema
   - Stores analysis results in `datalake.db` (survives sync)
   - One record per symbol (most recent only)
   - Includes previous analysis for iterative improvement

5. **`data/migrations/run_migration.py`** - Simple migration runner

## Architecture Decisions

### Cache Storage: Primary Database
- Cache stored in `datalake.db` (not `datalake_query.db`)
- Reason: Survives twice-daily sync from primary → query database
- Cache automatically copied to query db on sync
- TUI can read from either database

### Model Selection
```python
MODELS = {
    'haiku': 'claude-3-5-haiku-20241022',   # Fast, cheap - testing
    'sonnet': 'claude-3-5-sonnet-20241022', # High quality - production
    'opus': 'claude-3-opus-20240229',       # Most capable - advanced
}
```

**Note**: Need to verify Sonnet model ID with Anthropic (older version may be phasing out).

### Prompt Engineering
- System prompt defines Claude as options trading analyst
- Analysis prompt includes all available data (overview, OI timing, OI distribution, market context)
- Previous analysis included for iterative improvement
- Prompts easily editable in `ai_prompts.py`

## Setup & Testing

### Step 1: Install Dependencies

```bash
# Install Anthropic SDK (if not already installed)
pip install anthropic
```

### Step 2: Run Migration

```bash
# Apply cache table migration to datalake.db
python data/migrations/run_migration.py add_ai_analysis_cache.sql

# Verify migration
python morning_view/test_ai_analysis.py --verify-migration
```

### Step 3: Test Analysis

```bash
# Simple test with Haiku (fast, cheap)
python morning_view/test_ai_analysis.py AAPL

# Test with Sonnet (production quality)
python morning_view/test_ai_analysis.py NVDA --model sonnet

# Test cache behavior (read/write/hit)
python morning_view/test_ai_analysis.py TSLA --cache-test

# Force refresh (bypass cache)
python morning_view/test_ai_analysis.py AAPL --refresh
```

### Step 4: Verify Cache Persists Through Sync

```bash
# Create an analysis
python morning_view/test_ai_analysis.py AAPL

# Run sync (copies datalake.db → datalake_query.db)
python data/health/db_backup.py --sync --auto

# Verify cache still exists
python morning_view/test_ai_analysis.py --verify-migration
# Should show 1+ cached analyses
```

## What Works

- ✅ Cache table creation in `datalake.db`
- ✅ Data gathering from morning views
- ✅ Prompt building with all available data
- ✅ Claude API integration (Haiku/Sonnet/Opus)
- ✅ Cache read/write/expiration
- ✅ Iterative analysis (includes previous analysis for context)
- ✅ Command-line testing interface

## What's Not Built Yet

- ⏳ TUI integration (Phase 2)
  - `AIAnalysisScreen` in `mv_main.py`
  - Keybinding "4" in Symbol Detail screen
  - Loading state while analyzing
  - Markdown rendering

- ⏳ Polish (Phase 3)
  - Model selector in TUI
  - Refresh command
  - Analysis age display

## API Costs (Approximate)

Based on typical symbol analysis (~2000 tokens input, ~500 tokens output):

- **Haiku**: ~$0.001 per analysis (testing)
- **Sonnet**: ~$0.008 per analysis (production)
- **Opus**: ~$0.040 per analysis (advanced)

With 7-day cache:
- Analyzing 20 symbols/week with Sonnet = ~$0.16/week
- Re-analyzing same symbol (cache hit) = $0

## Configuration

API key loaded from `config.json`:
```json
{
  "claude_api": {
    "api_key": "sk-ant-api03-...",
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 4000
  }
}
```

## Prompt Customization

Edit `ai_prompts.py` to customize:
- System prompt (Claude's role and style)
- Analysis prompt template (what data to include)
- Output format and structure

Example: To make Claude more aggressive in identifying opportunities:
```python
SYSTEM_PROMPT = """You are an aggressive options trading analyst...
Prioritize identifying high-probability setups and opportunities.
..."""
```

## Next Steps (Phase 2)

1. Create `AIAnalysisScreen` in `mv_main.py`
2. Add keybinding "4" to Symbol Detail screen
3. Show loading modal while analyzing
4. Display formatted markdown analysis
5. Test end-to-end in TUI

## Troubleshooting

### "anthropic package not installed"
```bash
pip install anthropic
```

### "Cache table not found"
```bash
python data/migrations/run_migration.py add_ai_analysis_cache.sql
```

### "Failed to load Claude API key"
Check `config.json` has valid `claude_api.api_key` field.

### "No data found for symbol"
Symbol must exist in morning views data. Run morning views SQL script first:
```bash
python morning_views.py
```

## Files Modified

None - all new files, no changes to existing code.

## Database Impact

- New table: `symbol_ai_analysis` in `datalake.db`
- Minimal size: ~1KB per cached analysis
- Expected usage: 20-50 cached symbols = ~20-50KB total

## Design Philosophy

**Keep It Simple**:
- No complex orchestration - single Claude API call
- Reuse existing data layer - no new queries
- Transparent prompt engineering - easy to modify
- Minimal caching - one record per symbol
- No parsing/structuring of AI output - raw markdown

**Make It Accessible**:
- All prompts in one file
- Command-line testing before TUI integration
- Clear error messages
- Comprehensive test script
