# Trade Ingest Pipeline — Brainstorm & Design Notes

> **Status:** Phase 1 COMPLETE (2026-04-21). `trade_executions` table + email parser live.
> **Date:** 2026-04-21
> **Participants:** Ben, Claude (dev), Trading Advisor agent

---

## Concept

Automatically ingest Ben's Robinhood trade executions into the scanner database by parsing confirmation emails from Gmail. No unofficial API usage — just email parsing through the existing Gmail API integration (`tools/email_reader.py`).

### Email Flow
1. Robinhood sends trade confirmation to account holder's personal email (account-holder@example.com)
2. Auto-forwarded to `klmn800alerts@gmail.com` (confirmed working 2026-04-21)
3. `tools/trade_ingest.py` queries Gmail API for Robinhood execution emails
4. Parses trade details from forwarded message body, writes to `trade_executions` table
5. Marks emails as read to avoid reprocessing

### Forwarded Email Structure
Emails arrive from `[account holder] <account-holder@example.com>` with subjects like `Fwd: Option order executed`. The body contains a `---------- Forwarded message ---------` block wrapping the original Robinhood email. The parser must extract from inside this forwarded wrapper. The greeting says "Hi [account holder]" (account holder name), not "Hi Ben".

---

## Phase 1: Trade Executions (Build First)

### Table: `trade_executions`

One row per fill. Immutable log (insert-only from parser). `notes`, `trade_call_ref`, and `review_status` are freely editable post-insert — no constraints, no triggers, no ON CONFLICT clauses that would block UPDATE on those columns.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Autoincrement |
| `execution_timestamp` | DATETIME | When the fill happened (from email) |
| `action` | TEXT | `buy`, `sell`, `expired`, `assigned`, `exercised` |
| `instrument_type` | TEXT | `stock`, `option` |
| `symbol` | TEXT | Underlying ticker. Joins to everything. |
| `quantity` | INTEGER | Contracts (options) or shares (stock). Filled qty, not order qty. |
| `fill_price` | REAL | Per-share price ($0.55, not $55.00 per contract). Matches `option_contracts.last_price` convention. |
| `total_cost` | REAL | Computed: qty x fill_price x multiplier (100 for options, 1 for stock). Stored to avoid decimal-math bugs. |
| `option_type` | TEXT | `call` / `put`. NULL for stock. Lowercase, matches `flow_alerts.option_type`. |
| `strike` | REAL | NULL for stock. |
| `expiration_date` | DATE | NULL for stock. |
| `position_key` | TEXT | Generated: `ERIC\|option\|call\|12.0\|2026-05-15` or `RNMBY\|stock`. Solves NULL-composite-PK problem for positions_daily joins. |
| `broker` | TEXT | Default `robinhood`. Future-proofs for additional brokers. |
| `email_message_id` | TEXT UNIQUE | Gmail message ID. Primary dedup key. NULL for manual entries. |
| `robinhood_order_id` | TEXT | Extracted from "View order" link in email (e.g., `69dfc5fa-068c-44d6-bdf8-b5e7afde104a`). Groups partial fills from same order. |
| `source` | TEXT | `email` / `manual`. Tracks provenance and trust level. |
| `notes` | TEXT | Free-form, editable anytime. Trade thesis, exit reason, etc. |
| `trade_call_ref` | TEXT | Nullable. Links to trade_calls.md entry (e.g., `CC-2026-04-21`). |
| `review_status` | TEXT | Nullable. `unreviewed`, `claude_call`, `ben_decision`. For advisor workflow. |
| `underlying_price_at_fill` | REAL | Nullable. Enriched later from `historical_prices` or `flow_options_scans`. |
| `iv_at_fill` | REAL | Nullable. Options only. Enriched later. |
| `created_at` | TIMESTAMP | Row creation time. |

**Key constraints:**
- PK: `id` (autoincrement)
- UNIQUE: `email_message_id` (dedup — INSERT OR IGNORE on re-runs)
- No constraints on `notes`, `trade_call_ref`, `review_status` — freely updatable

### Email Formats to Parse (Phase 1)

All formats verified against real emails received 2026-04-21 in klmn800alerts@gmail.com inbox.

**1. Option order executed** (Subject: `Fwd: Option order executed`)
```
Your limit order to buy 1 contract of NKE $45.00 Call 5/15 in your
individual (•••1763) account executed at an average price of $180.00 per
contract on April 2, 2026 at 3:16 PM ET.
```
Parse: action=buy, qty=1, symbol=NKE, strike=45.00, option_type=call, expiry=5/15→2026-05-15, fill_price=1.80 ($180/100)

**Also verified with:** WFC $84.00 Call 4/17, 2 contracts, $123.00/contract → fill_price=1.23

**2. Stock order executed** (Subject: `Fwd: Your order has been executed`)
```
Your order to buy 2 shares of RNMBY through your individual (•••1763)
account was executed at an average price of $316.75 on March 27, 2026 at
2:51 PM ET.
```
Parse: action=buy, qty=2, symbol=RNMBY, fill_price=316.75

**Note:** Stock email body text appears TWICE — once in a preview/snippet area, once in the main body. Parser must deduplicate or only match the primary occurrence.

**3. Option order partially executed** (Subject: `Fwd: Option order partially executed`)
```
Your limit order to buy 2 contracts of ERIC $12.00 Put 5/15 in your
individual (•••1763) account executed on April 15, 2026 at 2:35 PM ET. So
far, 1 of 2 contracts were filled for an average price of $65.00 per
contract.
```
Parse: action=buy, qty=1 (filled, not ordered 2), symbol=ERIC, strike=12.00, option_type=put, expiry=5/15→2026-05-15, fill_price=0.65 ($65/100)

**4. Assignment / Expiration / Exercise** (email samples TBD — Ben generating more samples)
- `expired`: option expired worthless. qty→0, no cash event.
- `assigned`: short option assigned, option position closes, stock position opens.
- `exercised`: long option exercised into stock (rare for Ben's style).

### Robinhood Order ID Extraction
The "View order" link in option emails contains a Robinhood order UUID:
```
https://applink.robinhood.com/orders?id=69dfc5fa-068c-44d6-bdf8-b5e7afde104a&type=option
```
Extracted into `robinhood_order_id`. Useful for grouping partial fills from the same order.

### Gmail Search Query
```
from:account-holder@example.com subject:(Fwd: option order OR Fwd: your order)
```
Or broader: search for forwarded Robinhood emails by scanning body for `noreply@robinhood.com`.

### Partial Fill Handling
- Each partial fill email = one row in `trade_executions`
- Quantity is the **filled portion**, not the total order
- Dedup by `email_message_id` — each partial fill email has a unique Gmail ID
- Second fill on the same order = second email = second row
- `robinhood_order_id` groups them if needed (same order UUID in both)

### Price Convention: Per-Contract vs Per-Share
Robinhood emails report option prices "per contract" (e.g., "$55.00 per contract" = $0.55/share × 100 multiplier). We store **per-share** to match `option_contracts.last_price` convention:
- `fill_price` = email_price / 100 for options
- `fill_price` = email_price as-is for stock
- `total_cost` = quantity × fill_price × multiplier (100 for options, 1 for stock)

### Tool: `tools/trade_ingest.py`

```bash
# Check for new Robinhood emails and ingest
python tools/trade_ingest.py

# Dry run — show what would be ingested without writing
python tools/trade_ingest.py --dry-run

# Manual entry (no email)
python tools/trade_ingest.py --manual --symbol ERIC --action buy --type option \
    --strike 12 --expiry 2026-05-15 --option-type call --qty 1 --price 0.55

# Show recent executions
python tools/trade_ingest.py --recent
python tools/trade_ingest.py --recent --symbol ERIC
```

### Orchestrator Integration

**Morning — Step 1.4 (new), before sync:**
```
1.1 Morning Option Pipeline
1.2 Earnings Intelligence
1.3 Metadata Collection
1.4 Trade Ingest              ← NEW (catches overnight/pre-market fills)
1.5 Query Database Sync       (was 1.4)
1.6 Morning Views             (was 1.5)
```

**Post-Market — Step 3.1 (new), first thing after FM ends:**
```
3.1 Trade Ingest              ← NEW (catches all intraday fills)
3.2 Evening Option Pipeline   (was 3.1)
3.3 Airline Play              (was 3.2)
3.4 Query Database Sync       (was 3.3)
```

Both run before their respective syncs so trades land in the query DB immediately. Trade ingest is fast (Gmail search + parse a few emails) — negligible impact on schedule.

**Later (Phase 2+):** Add trade ingest to FM market hours cycle for near-real-time capture.

**Pipeline state:** Key `last_trade_ingest_at` in `daily_state.json`.

---

## Phase 2: Positions Daily (Build After ~1 Week of Data)

### Table: `positions_daily`

One row per (trade_date, position). Computed from `trade_executions` + EOD prices. Rebuilt each evening after Phase 3 (needs `option_contracts.last_price` and `historical_prices.close_price`).

| Column | Type | Notes |
|--------|------|-------|
| `trade_date` | DATE | The as-of date |
| `position_key` | TEXT | From `trade_executions.position_key`. PK with trade_date. |
| `symbol` | TEXT | |
| `instrument_type` | TEXT | |
| `option_type` | TEXT | NULL for stock |
| `strike` | REAL | NULL for stock |
| `expiration_date` | DATE | NULL for stock |
| `quantity_held` | INTEGER | Net position. Positive=long, negative=short. |
| `avg_entry_price` | REAL | Cost basis per share/contract |
| `total_cost_basis` | REAL | Total $ in currently held portion |
| `mark_price` | REAL | EOD close from `option_contracts` or `historical_prices` |
| `mark_value` | REAL | quantity_held x mark_price x multiplier |
| `unrealized_pnl_dollars` | REAL | mark_value - total_cost_basis |
| `unrealized_pnl_pct` | REAL | As percentage |
| `days_held` | INTEGER | From earliest still-held fill |
| `days_to_expiration` | INTEGER | Options only |
| `days_to_earnings` | INTEGER | Nullable. From `earnings_upcoming`. |

**PK:** `(trade_date, position_key)`

### Computation Logic
- Aggregate `trade_executions` by `position_key`: sum buys, subtract sells → net qty
- Weighted average entry price across buy fills
- Mark price from `option_contracts.last_price` (options) or `historical_prices.close_price` (stock)
- Runs after Phase 3 evening pipeline (after evening OP provides fresh `option_contracts` data)

---

## Phase 3: Position Lifecycles (Build After positions_daily Is Stable)

### Table: `position_lifecycles`

One row per opened-and-eventually-closed position. Must be a **table, not a view** — SQLite views aren't writable, and `outcome_grade` and `notes` need to be editable post-creation.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `position_key` | TEXT | Links to executions and positions_daily |
| `symbol` | TEXT | |
| `instrument_type` | TEXT | |
| `option_type` | TEXT | NULL for stock |
| `strike` | REAL | NULL for stock |
| `expiration_date` | DATE | NULL for stock |
| `open_date` | DATE | First buy fill |
| `close_date` | DATE | Last sell/expiry/assignment. NULL while open. |
| `status` | TEXT | `open`, `closed`, `expired_worthless`, `assigned`, `exercised` |
| `total_quantity_bought` | INTEGER | |
| `total_quantity_sold` | INTEGER | |
| `avg_entry_price` | REAL | Weighted across buys |
| `avg_exit_price` | REAL | Weighted across sells. NULL while open. |
| `realized_pnl_dollars` | REAL | NULL while open |
| `realized_pnl_pct` | REAL | NULL while open |
| `max_mfe_pct` | REAL | Max favorable excursion from daily marks (from positions_daily) |
| `max_mae_pct` | REAL | Max adverse excursion |
| `trade_call_ref` | TEXT | Inherited from executions |
| `outcome_grade` | TEXT | Advisor's post-mortem assessment |
| `notes` | TEXT | Free-form |

### MFE/MAE Computation
- Requires `positions_daily` history for the position
- Updated each EOD while position is open
- Answers "could we have exited better?" and "how much heat did you take?"

---

## What This Unlocks

Once the system knows Ben's actual positions:
- **Cross-reference FM alerts** against held positions (is this alert for something you already own?)
- **Track P&L on earnings plays** vs the system's signal quality
- **Expiry/earnings proximity warnings** ("you're holding ERIC 5/15 calls, 3 DTE, earnings in 2 days")
- **Advisor self-grading loop** — join trade_calls → position_lifecycles on trade_call_ref
- **Morning brief enrichment** — "your ERIC calls are +23%, IV has dropped 15% since entry"

---

## Decisions Log

| Decision | Rationale | Date |
|----------|-----------|------|
| Gmail email parsing, not Robinhood API | Unofficial API violates TOS, risk of account lock | 2026-04-21 |
| `email_message_id` as dedup key, not `order_id` | Robinhood emails don't contain order IDs in body text | 2026-04-21 |
| `fill_price` stored per-share, not per-contract | Matches `option_contracts.last_price` convention for clean joins | 2026-04-21 |
| `total_cost` stored despite being computed | Avoids decimal-math bugs downstream | 2026-04-21 |
| `position_key` column for composite key | SQLite NULL != NULL in UNIQUE constraints breaks composite PKs with NULLs | 2026-04-21 |
| `position_lifecycles` as table, not view | SQLite views aren't writable; `outcome_grade`/`notes` must be editable | 2026-04-21 |
| Phase 1→2→3 build order | Execution log is foundation; positions/lifecycles derive from it | 2026-04-21 |
| Metadata columns in Phase 1 from day one | `notes`/`trade_call_ref`/`review_status` needed for advisor workflow before Phases 2-3 exist | 2026-04-21 |
| `robinhood_order_id` extracted from email links | Groups partial fills; bonus data at no extra cost | 2026-04-21 |

---

## Open Questions
- [ ] Get email samples for assignment, expiration, and exercise notifications (Ben generating more samples)
- [ ] Enrichment pipeline for `underlying_price_at_fill` and `iv_at_fill` — timestamp-based lookup design
- [ ] Expiry year inference: email says "5/15" not "2026-05-15" — need logic to infer year (assume current year, or next year if month is in the past)
- [ ] Stock email body duplication — confirm parser handles the preview snippet that appears before the main body
