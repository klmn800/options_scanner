# Earnings Date Confirmation System — Execution Plan

**Created:** 2026-04-23
**Context:** Trading advisor discovered 15%+ error rate in `earnings_upcoming` dates. yfinance returns wrong future dates for some symbols, and the collector trusts it unconditionally. This plan adds date confirmation, a CLI tool, a lite daily refresh, and an autonomous research agent.

**Conversation context:** Ben and Claude Opus discussed this design extensively. Key decisions are documented below. Do not deviate from the design without asking Ben.

---

## Background & Root Cause

- yfinance is the primary date source. It returns wrong **future** dates for some symbols (e.g., GILD showed 04-23, actual was 05-07 — 14 days off).
- The collector's stale detection only catches **past** dates, not wrong future dates.
- Finnhub sometimes has the correct date but is ignored when yfinance has any date ("yfinance wins" policy).
- `earnings_time = 'Unknown'` correlates strongly with bad dates.
- Tradier's `/beta/markets/fundamentals/calendars` has a Confirmed/Estimated flag, but testing showed "Confirmed" is wrong 4/7 times vs Robinhood. Not reliable as a tiebreaker.
- **No single automated source is reliable.** The fix is: flag disputes, research via web search (IR pages), and lock confirmed dates.

---

## Build Order

Build in this exact order. Each phase is independently testable.

### Phase 1: Schema Changes

#### 1A. `earnings_upcoming` — add confirmation columns

Add via ALTER TABLE (same pattern as `_ensure_schema` in `ei_snapshot_collector.py`). Put the migration in the lite refresh function so it auto-runs on first use.

```sql
ALTER TABLE earnings_upcoming ADD COLUMN date_confirmed INTEGER DEFAULT 0;
ALTER TABLE earnings_upcoming ADD COLUMN date_confirmed_by TEXT;
ALTER TABLE earnings_upcoming ADD COLUMN date_confirmed_at TEXT;
```

**Important:** These columns die with the row when it's archived to `earnings_events` and a new row is created for next quarter. That's the desired behavior — confirmation expires naturally.

#### 1B. `symbol_metadata` — add IR URL cache

```sql
ALTER TABLE symbol_metadata ADD COLUMN ir_earnings_url TEXT;
ALTER TABLE symbol_metadata ADD COLUMN ir_url_last_verified TEXT;
```

This persists across quarters. The agent saves the IR page URL it used, so next quarter's lookup is faster.

#### 1C. `performance.db` — dispute tracking table

```sql
CREATE TABLE IF NOT EXISTS earnings_date_disputes (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    db_date TEXT,
    db_time TEXT,
    yfinance_date TEXT,
    finnhub_date TEXT,
    dispute_reason TEXT,        -- 'date_disagreement', 'unknown_time', 'both', 'confirmed_row_diverged'
    resolution TEXT,            -- 'confirmed_ben', 'confirmed_agent', 'unresolved', 'skipped'
    resolved_date TEXT,         -- the confirmed correct date
    resolved_time TEXT,         -- the confirmed correct time (bmo/amc)
    resolved_at TEXT,           -- timestamp of resolution
    research_url TEXT,          -- IR page used
    notes TEXT,
    PRIMARY KEY (trade_date, symbol)
);
```

---

### Phase 2: CLI Tool (`tools/earnings_confirm.py`)

**Purpose:** Let Ben manually confirm earnings dates. Writes directly to `datalake.db`.

**Commands:**
```bash
python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo
python tools/earnings_confirm.py --symbol VZ                    # confirm current date/time as-is
python tools/earnings_confirm.py --list                         # show all confirmed
python tools/earnings_confirm.py --list-unconfirmed             # unconfirmed within 21 days
python tools/earnings_confirm.py --bulk-file corrections.csv    # batch import (symbol,date,time per line)
```

**Behavior:**
- Updates `earnings_upcoming` SET `date_confirmed=1, date_confirmed_by='ben', date_confirmed_at=<now>`
- If `--date` and/or `--time` provided, also updates `earnings_date` and `earnings_time`
- If overwriting an existing agent confirmation with a **different date**, print a warning: `"WARNING: Overwriting agent confirmation (was {old_date}) with {new_date}"`
- If symbol not found in `earnings_upcoming`, print error and skip
- Use `clean_database_row()` before writes (standard pattern)
- Set timestamps AFTER `clean_database_row()` (known gotcha — it nullifies date fields)
- Use `datalake.db` directly (this is a production write tool, not a query)

**Console output example:**
```
VZ: confirmed 2026-04-27 bmo (was: 2026-04-27 Unknown) [date unchanged, time updated]
GILD: confirmed 2026-05-07 amc (was: 2026-04-23 Unknown) [date changed +14d, time updated]
```

**File structure:** Single file, no class needed. Follow pattern of `tools/news_sentiment.py` (argparse, direct DB access, console output).

---

### Phase 3: Lite Daily Refresh (new EI sub-step 1/8)

**File:** Add function to `strategies/earnings_intel/ei_main.py` OR create `strategies/earnings_intel/ei_lite_refresh.py` if it's cleaner.

**Runs as:** New Sub-step 1/8 in `run_daily_pipeline()`. Renumber existing steps to 2/8 through 8/8 (update both the `beautiful_log()` calls and any comments).

**Current step numbering (to be renumbered):**
1. Snapshot Collection (1/7) → becomes 2/8
2. Archive Past Earnings (2/7) → becomes 3/8
3. Post-Earnings Calculation (3/7) → becomes 4/8
4. Expected Moves Update (4/7) → becomes 5/8
5. Watchlist Population (5/7) → becomes 6/8
6. News Enrichment (6/7) → becomes 7/8
7. Arbitrage Scan (7/7) → becomes 8/8

**No dependency issues:** The lite refresh fetches from external APIs (yfinance, Finnhub). It doesn't need snapshot data or post-earnings calcs. Safe as Step 1.

**Scope:** Only symbols where:
- `earnings_date` is within 21 days of today AND
- `date_confirmed = 0` (not yet confirmed)

This is typically 30-80 symbols during peak earnings season, much less otherwise. Should take 2-5 minutes vs 15 minutes for the full 820-symbol refresh.

**Logic:**
1. Query `earnings_upcoming` for unconfirmed symbols within 21 days
2. For each symbol, fetch yfinance date + Finnhub date/timing (same code path as `ei_collector.py:_fetch_yfinance_data()` and Finnhub fetch — consider extracting shared helper)
3. If yfinance returns a different date than stored AND `date_confirmed = 0` → update
4. Flag disputes:
   - `earnings_time = 'Unknown'` → flag
   - yfinance vs Finnhub disagree by >1 day → flag
   - yfinance vs stored disagree by >3 days → flag (large shift = suspicious)
5. Write flagged symbols to `performance.db:earnings_date_disputes` table
6. If any disputes flagged → spawn earnings date agent (Phase 4)
7. Return results dict for pipeline tracking

**Schema migration:** Run the ALTER TABLE from Phase 1A here (idempotent, wrapped in try/except for "duplicate column" error).

**Console output:**
```
Lite Earnings Refresh (1/8)
  Scope: 47 unconfirmed symbols within 21 days
  Refreshed: 47 (3 dates updated, 44 unchanged)
  Disputes flagged: 8 (5 unknown_time, 2 date_disagreement, 1 both)
  Spawning earnings date agent for 8 symbols...
```

**Agent spawning:** At the end of this step, if disputes exist, spawn the agent as a background subprocess. Use the same pattern as `main_runners.py:_launch_trading_advisor()` — fire-and-forget, don't block the pipeline. The agent gets its own visible window (Ben wants to watch it work).

---

### Phase 4: Earnings Date Agent

#### 4A. Directory Structure

```
agents/earnings_researcher/
├── CLAUDE.md                     # Agent identity, role, constraints
├── .claude/
│   ├── settings.local.json       # Permissions
│   └── hooks/
│       └── inject_context.py     # Feed dispute list at session start
├── .git/                         # Own repo (git init, mandatory for isolation)
├── launcher.py                   # Python launcher (follows AGENT_PATTERN.md)
├── memory/
│   └── research_log.md           # Running log of confirmations + failures
├── reference/
│   └── ir_url_cache.md           # Backup of known IR URLs (human-readable)
└── analysis/                     # Session outputs
```

#### 4B. Agent CLAUDE.md

The agent's identity and instructions. Key points:
- You are an earnings date researcher. Your job: verify earnings dates for disputed symbols.
- You have a list of symbols to research (injected via hook or prompt file).
- For each symbol: web search for the IR press release or events page, extract the correct date + BMO/AMC timing.
- Write confirmations to `datalake.db` via the CLI tool: `python E:\options_scanner\tools\earnings_confirm.py --symbol X --date Y --time Z`
- Save IR URLs to `symbol_metadata` via: `python E:\options_scanner\tools\direct_db_query.py --db E:\options_scanner\data\datalake.db --sql "UPDATE symbol_metadata SET ir_earnings_url='...', ir_url_last_verified='...' WHERE symbol='...'"`
- If you can't find a reliable date, skip the symbol and log it. Don't guess.
- Log your work to `memory/research_log.md` with date, symbol, what you found, URL used.
- Update `performance.db:earnings_date_disputes` with resolution status.
- **NEVER overwrite a date confirmed by Ben** (`date_confirmed_by = 'ben'`). If you disagree, log it but don't change it.
- If overwriting your own previous confirmation, that's fine (you found better info).

#### 4C. Agent Permissions (`settings.local.json`)

```json
{
  "permissions": {
    "allow": [
      "Bash(python E:/options_scanner/tools/earnings_confirm.py *)",
      "Bash(python E:/options_scanner/tools/direct_db_query.py *)",
      "WebSearch",
      "WebFetch"
    ],
    "deny": [
      "Bash(sqlite3 *)",
      "Bash(python E:/options_scanner/main.py *)",
      "Bash(rm *)",
      "Bash(del *)"
    ]
  },
  "claudeMdExcludes": ["E:/options_scanner/CLAUDE.md"]
}
```

Key: agent can use the CLI tool (which writes to datalake.db), query the DB, and do web searches. Cannot run main.py, delete files, or use sqlite3 directly.

#### 4D. Write Guard (`.claude/hooks/earnings_researcher_write_guard.py`)

**Location:** `E:\options_scanner\.claude\hooks\earnings_researcher_write_guard.py`

Allows writes to:
- `agents/earnings_researcher/*` (own workspace)

Blocks writes to:
- All production code (`*.py` outside workspace)
- All databases (agent uses CLI tools instead)
- Other agent workspaces

#### 4E. Context Injection Hook (`inject_context.py`)

Fires on `UserPromptSubmit`. Queries `performance.db:earnings_date_disputes` for today's unresolved disputes and injects them:

```
<dispute-list>
Today's date: 2026-04-23

Symbols to research (8 disputes):
1. GILD — DB date: 2026-04-23, time: Unknown, reason: unknown_time
   Cached IR URL: None
2. VALE — DB date: 2026-04-23, time: Unknown, reason: date_disagreement+unknown_time
   yfinance: 2026-04-28, finnhub: 2026-04-28
   Cached IR URL: None
...
</dispute-list>
```

Also injects current date/time (standard pattern from other agents).

#### 4F. Launcher (`launcher.py`)

Follow the system analyst launcher pattern:
1. Check for unresolved disputes in `performance.db`
2. If none → exit early (nothing to do)
3. Write session prompt to `.session_prompt.md` (inject date, dispute count)
4. Spawn Claude Code:
   ```
   cd /d E:\options_scanner\agents\earnings_researcher
   claude --permission-mode auto @.session_prompt.md
   ```
5. Visible window (Ben wants to watch)
6. Timeout: 45 minutes

#### 4G. Session Prompt Template

```markdown
# Earnings Date Research Session

Today is {date}. You have {N} symbols to research.

Your dispute list has been injected via context hook. For each symbol:

1. Check if there's a cached IR URL in the dispute data. If so, try WebFetch on it first.
2. If no cached URL, WebSearch: "{company_name} Q1 2026 earnings date" or similar.
3. Look for the official IR press release or investor events page.
4. Extract: correct earnings date + BMO/AMC timing.
5. Confirm via CLI: python E:\options_scanner\tools\earnings_confirm.py --symbol {SYM} --date {DATE} --time {TIME}
6. Save the IR URL: python E:\options_scanner\tools\direct_db_query.py --db E:\options_scanner\data\datalake.db --sql "UPDATE symbol_metadata SET ir_earnings_url='{URL}', ir_url_last_verified='{TODAY}' WHERE symbol='{SYM}'"
7. Update dispute resolution: python E:\options_scanner\tools\direct_db_query.py --db E:\options_scanner\data\performance.db --sql "UPDATE earnings_date_disputes SET resolution='confirmed_agent', resolved_date='{DATE}', resolved_time='{TIME}', resolved_at='{NOW}', research_url='{URL}' WHERE trade_date='{TODAY}' AND symbol='{SYM}'"
8. If you can't find a reliable source, skip and log to memory/research_log.md.

When done, print a summary of your work.
```

**Important:** The prompt must NOT hardcode a quarter like "Q1 2026". The agent determines the quarter from the dispute data (the earnings_date tells it roughly what quarter).

---

### Phase 5: Collector Guard (Friday `ei_collector.py`)

**Change:** In `_fetch_and_upsert_earnings()` (line ~484), before the per-symbol loop:

1. Load confirmed symbols:
   ```python
   confirmed_symbols = set()
   try:
       conn = self._get_connection()
       for row in conn.execute("SELECT symbol FROM earnings_upcoming WHERE date_confirmed = 1"):
           confirmed_symbols.add(row[0])
       conn.close()
   except:
       pass
   ```

2. At the top of the loop, skip confirmed:
   ```python
   for i, symbol in enumerate(self.stock_symbols, 1):
       if symbol in confirmed_symbols:
           source_counts['confirmed_skip'] = source_counts.get('confirmed_skip', 0) + 1
           continue
   ```

3. Log the skip count in the completion summary.

---

### Phase 6: Pipeline Wiring (`main_runners.py`)

Add agent spawning to the EI phase. After `run_earnings_intel()` returns, check if disputes were flagged. If so, spawn the earnings researcher agent as a background subprocess (fire-and-forget).

**Pattern:** Same as `_launch_trading_advisor()` in `main_runners.py`. Spawn `agents/earnings_researcher/launcher.py` as a subprocess. Don't wait for it.

**Alternative:** The lite refresh (Phase 3) could spawn the agent directly at the end of its step, before returning. This is simpler and keeps the spawning logic close to the dispute detection. Preferred approach.

---

## Testing Plan

### Phase 1-2 (Schema + CLI):
```bash
# Verify columns exist
python tools/direct_db_query.py --schema earnings_upcoming | grep confirmed

# Confirm a symbol
python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo

# Verify it stuck
python tools/direct_db_query.py --sql "SELECT symbol, earnings_date, earnings_time, date_confirmed, date_confirmed_by FROM earnings_upcoming WHERE symbol='VZ'"

# List unconfirmed
python tools/earnings_confirm.py --list-unconfirmed
```

### Phase 3 (Lite Refresh):
```bash
# Run EI pipeline manually, verify new step 1/8 appears
python main.py --earnings-intel
```

### Phase 4 (Agent):
```bash
# Test agent standalone first (don't wait for pipeline integration)
cd agents/earnings_researcher
python launcher.py

# Watch it work in the visible window
# Verify confirmations landed:
python tools/earnings_confirm.py --list
```

### Phase 5 (Collector Guard):
```bash
# Confirm a symbol, then run collector, verify it was skipped
python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo
# Run collector (Friday only, or test with --dry-run if available)
# Check logs for "confirmed_skip" count
```

---

## Files Modified (Summary)

| File | Change |
|------|--------|
| `strategies/earnings_intel/ei_main.py` | Add lite refresh as Step 1/8, renumber 2-8 |
| `strategies/earnings_intel/ei_collector.py` | Add confirmed_symbols skip in main loop |
| `tools/earnings_confirm.py` | **NEW** — CLI tool |
| `agents/earnings_researcher/` | **NEW** — entire agent directory |
| `.claude/hooks/earnings_researcher_write_guard.py` | **NEW** — write guard |
| `main_runners.py` | Possibly: agent spawn after EI (or handled in ei_main.py) |
| `data/datalake.db` | Schema: 3 new columns on `earnings_upcoming`, 2 on `symbol_metadata` |
| `data/performance.db` | Schema: new `earnings_date_disputes` table |

---

## Design Decisions (from conversation with Ben)

These were explicitly discussed and agreed. Don't second-guess them:

1. **Agent confirms directly** — no staging/review queue. Ben can override with CLI.
2. **Agent must not overwrite Ben's confirmations.** If agent disagrees with Ben's date, log it but don't change.
3. **Agent can overwrite its own previous confirmations** (found better info).
4. **Warn on conflict** — if agent confirmation would change an existing confirmed date, print warning.
5. **Collector skips confirmed symbols entirely** — no fetch, no write, no logging of source disagreements.
6. **Lite refresh scope: 21 days, unconfirmed only.**
7. **Dispute triggers:** `earnings_time = 'Unknown'` OR yfinance/Finnhub disagree by >1 day.
8. **IR URLs persist on `symbol_metadata`** — survives quarter rollovers.
9. **Confirmation expires naturally** — row is archived, new row for next quarter starts unconfirmed.
10. **Agent runs in visible window** — Ben wants to watch it work.
11. **Agent spawns from end of lite refresh step** — rest of EI runs concurrently.
12. **Agent timeout: 45 minutes.**
13. **Full Friday collector still runs** for the 90-day horizon. Lite daily refresh only covers <=21 days.
14. **Trust levels equal** — Ben confirmation = agent confirmation. IR is gold standard.
15. **"Couldn't find it" = skip** — agent doesn't confirm, symbol gets re-flagged tomorrow.

---

## Implementation Notes

- Use `now_eastern()` from `tools/timezone_utils.py` for all timestamps
- Use `encoding='utf-8'` on all file handlers
- Follow `clean_database_row()` pattern for DB writes (but set timestamps AFTER calling it)
- Use `beautiful_log()` for console output in pipeline steps
- The agent's `settings.local.json` must exclude parent `CLAUDE.md` via `claudeMdExcludes`
- The agent needs its own `.git/` directory (mandatory for project root isolation)
- The write guard lives OUTSIDE the agent workspace at `.claude/hooks/`
