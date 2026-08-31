# Paper Trading Platform — Design Document

> **Status:** State A COMPLETE 2026-05-19. State B IMPLEMENTED 2026-05-19 (acceptance test pending). Source of truth across sessions — update when decisions change.
> **Current phase:** State B implementation complete. Next target: **State C (First Auto-Open Consumer — FM Alerts)**.
> **Date drafted:** 2026-05-18
> **Participants:** Ben, Claude

This is the durable design record. As we develop, update this file when decisions change — don't let it drift. Phase-specific build notes live alongside it (`PHASE_1_NOTES.md`, etc.) once we ship work.

---

## 1. Intention & Motivation

The scanner produces many signals (FM alert scoring v2, earnings underpricing tiers, OP delta scores, intraday signal upgrades/downgrades) but ground-truth feedback today is limited to a next-day OI resolution heuristic and Ben's manual Robinhood trades. Paper trading closes the loop:

1. **Signal validation.** Every FM alert (or earnings STRONG BUY, or OP candidate) auto-paper-traded produces real P&L data we can use to grade the signal — without waiting on hand-curated trades.
2. **Hypothetical journaling.** Trading Advisor (and Market Analyst) can pursue trades Ben didn't take, tracking outcomes via paper P&L instead of post-hoc what-if analysis.
3. **A/B experimentation.** "Follow alert immediately vs wait for dip," "v2 scorer vs v3 candidate," "straddle vs single-leg on STRONG BUY" — all run head-to-head against the same triggers, scored by tag.
4. **Pre-flight check.** Tradier's `preview=true` validates buying power, cost, margin impact before Ben places a real Robinhood order.

The platform is built once as infrastructure. New consumers (a new A/B test, a new agent capability) attach by calling the consumer API — they never touch auth, polling, or fill reconciliation.

---

## 2. End States

Each is a coherent stopping point. The work to reach each one has standalone value.

### A. Manual Paper Trading (Proof of Concept) — **SHIPPED 2026-05-18**
- CLI-driven buy/sell of paper equities and options.
- Submitted orders polled to completion; fills recorded in `paper_executions`.
- Open positions tracked in `paper_positions`.
- Daily account balance snapshot to `paper_account_snapshots`.
- P&L queryable by tag.
- **No automation, no consumers, no auto-close.** Ben (or an agent via CLI) drives every action.
- Useful standalone: structured trade journal for hypothetical positions.
- Operational reference: [`README.md`](README.md).

### B. Engine-Managed Exits
- Each `paper_positions` row optionally carries a `close_conditions` block. **NULL by default** — manual `--open` without explicit condition flags creates an unmonitored position the engine ignores. Auto-consumers in C+ supply conditions explicitly.
- Vocabulary (v1, all stateless): `take_profit_pct`, `stop_loss_pct`, `max_hold_days`, `expire_before_dte`, `underlying_target_above`, `underlying_target_below`. Trailing stops + signal-coupled exits deferred.
- A standalone engine (`tools/paper_close_engine.py`) reads positions, fetches Tradier quotes directly, evaluates conditions, fires closes for trippers. **Not integrated with FM** — separate Task Scheduler job every 2 min, market hours only by default.
- 3-state status machine: `open → closing → closed`. Prevents double-submit of close orders.
- Paper tables moved to `data/paper.db` to eliminate FM write-lock contention.
- **Open is still manual; close is automatic for monitored positions only.**
- Config defaults (`paper_trading.default_close_conditions`) exist for programmatic reference; they are NOT auto-applied to CLI opens.
- Detailed plan: `docs/_local/paper_trading/PHASE_B_PLAN.md` (parked).

### C. First Auto-Open Consumer — FM Alerts
- Every FM alert auto-opens a paper trade tagged with the scorer version (`fm_alert_v2`).
- Closed via engine-managed exits (state B).
- Performance flows into `performance.db` as a new `paper_experiment_daily` table.
- Closed-loop validation of alert scoring v2 — replaces vibes-based scoring review with data.

### D. Multi-Consumer Platform
- The paper API (`paper.open()` / `paper.close()` / `paper.positions()` / `paper.pnl()`) is stable.
- Concurrent consumers: FM alerts + earnings STRONG BUY straddles + TA journal — each with its own tag namespace.
- Single Tradier paper account; segregation is by tag.
- Trading Advisor gets the CLI in its write-guard allowlist.

### E. A/B Experiment Harness
- Formal framework for named strategy comparisons.
- A strategy is a Python script that subscribes to a trigger (FM alert event, earnings signal change, etc.), opens a paper trade with its own tag, optionally registers a close callback.
- The harness runs registered strategies against shared triggers and reports head-to-head.
- Use case: "follow alert immediately vs wait for 5% intraday dip on same alert."

### Out of scope (for now)
- *Simulated-only engine* (no Tradier roundtrip) — rejected. Tradier is authoritative; less code to maintain.
- *Multi-account / multi-wallet at broker level* — Tradier paper is one account. A/B is by tag.
- *Real-money order routing through this platform* — separate concern; real trades stay on Robinhood.

---

## 3. Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Consumers                                                   │
│   - CLI (tools/paper_trade.py)                              │
│   - FM auto-paper hook (fm_alerts.py)         [Phase C]     │
│   - TA journal CLI tool                       [Phase D]     │
│   - A/B harness                               [Phase E]     │
└──────────────────────────┬──────────────────────────────────┘
                           │ paper.open() / paper.close() / paper.positions() / paper.pnl()
┌──────────────────────────▼──────────────────────────────────┐
│ Consumer API (core/paper_trading.py)                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ Reconciliation Engine (tools/paper_poll.py)   [Phase A+B]   │
│   - Polls open Tradier orders → writes fills                │
│   - Updates paper_positions                                 │
│   - Evaluates close_conditions, submits closing orders      │
│   - Daily balance snapshot                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ Tradier Sandbox Client (core/tradier_paper.py)              │
│   - place_equity_order / place_option_order                 │
│   - get_order / cancel_order                                │
│   - get_positions / get_balances / get_quotes               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS, Bearer sandbox token
                  https://sandbox.tradier.com/v1/
```

**Persistence:** `data/datalake.db` — three new tables (`paper_executions`, `paper_positions`, `paper_account_snapshots`). Plus a `paper_experiment_daily` table in `performance.db` once Phase C lands.

---

## 4. Schema

Mirrors `trade_executions` / position tracking conventions where possible. Differences are deliberate and explained.

### `paper_executions`

One row per fill. Immutable log. `notes` is freely editable post-insert.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Autoincrement |
| `execution_timestamp` | DATETIME | When Tradier reported the fill |
| `action` | TEXT | `buy` / `sell` (for equity) or `buy_to_open` / `sell_to_open` / `buy_to_close` / `sell_to_close` (for option) |
| `instrument_type` | TEXT | `stock` or `option`. Matches `trade_executions.instrument_type`. |
| `symbol` | TEXT | Underlying ticker |
| `quantity` | INTEGER | Contracts (options) or shares (stock) |
| `fill_price` | REAL | Per-share price. $1.80 not $180.00 for a contract. Matches `trade_executions.fill_price`. |
| `total_cost` | REAL | `qty * fill_price * multiplier` (100 for options, 1 for stock). Stored to avoid decimal-math bugs. |
| `option_type` | TEXT | `call` / `put`. NULL for stock. Lowercase. |
| `strike` | REAL | NULL for stock |
| `expiration_date` | DATE | NULL for stock |
| `option_symbol` | TEXT | OCC format (e.g., `AAPL251017C00247500`). NULL for stock. |
| `position_key` | TEXT | Generated: `AAPL\|option\|call\|247.5\|2025-10-17` or `AAPL\|stock`. Same convention as `trade_executions`. |
| `tag` | TEXT | **The slice axis for A/B and consumer attribution.** Examples: `manual`, `fm_alert_v2`, `ei_strong_buy_straddle`, `advisor_journal`. |
| `source_event_id` | TEXT | Nullable. Idempotency key — e.g., `flow_alerts.id` for FM auto-paper. Prevents double-open on engine crash recovery. |
| `tradier_order_id` | TEXT | Returned by Tradier on order placement. Groups partial fills. |
| `broker` | TEXT | Default `tradier_sandbox`. Future-proofs for paper trading via other brokers. |
| `notes` | TEXT | Free-form, editable. Trade thesis, exit reason. |
| `created_at` | TIMESTAMP | Row creation time |

**Constraints:**
- PK: `id`
- UNIQUE: `(tag, source_event_id)` where `source_event_id IS NOT NULL` — prevents auto-consumers from double-opening on the same trigger.
- No constraint on `notes` — freely updatable.

### `paper_positions`

Current state of open paper positions. Closed positions retained for history.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Autoincrement |
| `position_key` | TEXT | Same convention as `paper_executions.position_key` |
| `tag` | TEXT | Inherited from opening execution |
| `instrument_type` | TEXT | `stock` / `option` |
| `symbol` | TEXT | Underlying |
| `option_symbol` | TEXT | NULL for stock |
| `option_type` | TEXT | NULL for stock |
| `strike` | REAL | NULL for stock |
| `expiration_date` | DATE | NULL for stock |
| `quantity` | INTEGER | Open contract/share count |
| `cost_basis_per_unit` | REAL | Avg fill price (per-share for options) |
| `total_cost` | REAL | `quantity * cost_basis_per_unit * multiplier` |
| `opened_at` | DATETIME | First fill timestamp |
| `opening_execution_id` | INTEGER | FK → `paper_executions.id` |
| `closed_at` | DATETIME | NULL while open |
| `closing_execution_id` | INTEGER | FK → `paper_executions.id`, NULL while open |
| `exit_price_per_unit` | REAL | NULL while open |
| `realized_pnl` | REAL | NULL while open. `(exit_price - cost_basis) * qty * multiplier` |
| `close_reason` | TEXT | NULL while open. `take_profit` / `stop_loss` / `max_hold` / `manual` / `signal_event` |
| `close_conditions_json` | TEXT | JSON blob — `{"take_profit_pct": 25, "stop_loss_pct": -30, "max_hold_days": 5}`. Nullable. |
| `status` | TEXT | `open` / `closed` |
| `updated_at` | TIMESTAMP | Last write |

**Constraints:**
- PK: `id`
- Index: `(status, symbol)` and `(tag, status)` for hot-path queries.

### `paper_account_snapshots`

Daily snapshot of Tradier paper account state. Tradier is authoritative — this table is the local time-series.

| Column | Type | Notes |
|---|---|---|
| `snapshot_date` | DATE PK | One row per day |
| `total_equity` | REAL | From Tradier `GET /v1/accounts/{id}/balances` |
| `cash` | REAL | |
| `long_market_value` | REAL | |
| `short_market_value` | REAL | |
| `open_pl` | REAL | Unrealized P&L (from Tradier) |
| `close_pl` | REAL | Realized P&L on the day (from Tradier) |
| `buying_power` | REAL | |
| `option_buying_power` | REAL | |
| `raw_response_json` | TEXT | Full Tradier balances response, for forensic recovery |
| `snapshotted_at` | TIMESTAMP | When we polled it |

### Why no `paper_orders` table

In real life (`trade_executions`), orders are not persisted because we only see fill confirmation emails — the order is invisible to us. With Tradier API, we *do* see the submitted order, but persisting it adds reconciliation complexity (status transitions, partial fills, rejections) for minimal analytical value. **Phase 1 logs rejections to console, persists only fills.** Revisit if order-level forensics become a need.

### Why no `paper_experiments` registry

The `tag` string on each execution row is the experiment record. A separate registry only earns its keep when experiments accumulate metadata (description, scoring config, status). Start with tag conventions documented in this file; promote to a table if needed.

---

## 5. Key Design Decisions

Each decision recorded here is durable — if we change one, update this section and explain why.

### 5.1 One paper account = one wallet; A/B is by tag, not by balance
Tradier paper accounts are single accounts with single cash balances. Trying to maintain "strategy A starts with $10k, strategy B starts with $10k" at the broker level is impossible. **A/B segregation lives in analysis** — every fill carries a `tag`, P&L is computed per tag. The single paper account holds the aggregate cash pool.

### 5.2 Tradier balances are authoritative; we snapshot daily
Don't maintain a local cash balance by simulating fills against our own model — it will diverge from Tradier and create reconciliation pain. Query `GET /balances` on demand for current state, snapshot once per day for the time-series. If we ever need higher resolution, snapshot per FM cycle.

### 5.3 Persist fills, not orders
Orders are transient state on the path to a fill. The reconciliation engine holds them in memory while polling. Rejections, partial fills, and cancellations are logged but not stored. Saves a table and a class of reconciliation bugs.

### 5.4 15-minute data delay caveat
Sandbox uses 15-min delayed quotes. Market orders fill against delayed quotes, so absolute paper P&L will diverge from "what real-time fills would have done." **Relative comparisons (A/B, signal validation) are unaffected — both sides see the same delay.** Limit orders sidestep most of it. Document loudly in CLI output and in any reporting where absolute P&L matters.

### 5.5 Default close conditions: +25% / -30% / 5d
Matches Ben's hand-traded heuristic. The defaults apply when a consumer doesn't override. Tunable per-consumer via the `close_conditions` parameter.

### 5.6 Equities and options from day one
Same endpoint (`POST /v1/accounts/{id}/orders`), same `paper_executions` schema (nullable option-specific columns), same consumer API. Only differences: side enum (`buy/sell` vs `buy_to_open/...`), P&L multiplier (1 vs 100), quote lookup path. Excluding equities now would leak "options-only" assumptions into the design.

### 5.7 Idempotency via `(tag, source_event_id)`
Auto-consumers (FM auto-paper) pass `source_event_id = flow_alerts.id`. The UNIQUE constraint blocks double-opens on engine crash recovery or re-runs. Manual CLI invocations don't pass `source_event_id` (NULL), so the constraint doesn't bite.

### 5.8 Tag naming convention
Free-text but with conventions:
- `manual` — ad-hoc human-driven trades
- `manual_<theme>` — themed manual trades, e.g., `manual_pdd_play`
- `fm_alert_<scorer_version>` — FM auto-paper, scorer-versioned (`fm_alert_v2`, `fm_alert_v3`)
- `fm_alert_<scorer_version>_<variant>` — A/B variants (`fm_alert_v2_immediate`, `fm_alert_v2_dip_wait`)
- `ei_<signal>_<structure>` — earnings auto-paper (`ei_strong_buy_straddle`, `ei_buy_call`)
- `advisor_journal` — Trading Advisor hypothetical trades
- `advisor_journal_<date>_<symbol>` — optional date/symbol suffix for the agent

Formalize into a registry table if patterns multiply.

---

## 6. Phase 1 Deliverable (End State A)

The proof-of-concept scope. No automation, no consumers — just a working manual paper trading interface.

### Code

- **`core/tradier_paper.py`** — sandbox-mode Tradier client:
  - `place_equity_order(symbol, side, qty, type, duration, price=None, preview=False)`
  - `place_option_order(symbol, option_symbol, side, qty, type, duration, price=None, preview=False)`
  - `get_order(order_id)`
  - `cancel_order(order_id)`
  - `get_positions()`
  - `get_balances()`
  - `get_quote(symbol)` and `get_option_quote(option_symbol)`

- **`tools/paper_trade.py`** — CLI:
  - `--open --instrument {stock|option} --symbol X [--option-symbol Y] --side ... --qty N --type {market|limit} [--price P] --tag TAG [--source-event-id ID]`
  - `--close --position-id N [--reason manual]`
  - `--cancel --order-id N`
  - `--status [--tag TAG]` — open positions
  - `--positions` — same as above, all open positions
  - `--balance` — current Tradier paper balance
  - `--pnl [--tag TAG] [--since DATE]` — realized P&L

- **`tools/paper_poll.py`** — standalone polling script:
  - Polls open Tradier orders (those we placed and haven't seen filled), writes fills to `paper_executions`, transitions `paper_positions` to OPEN.
  - For Phase 1: run by hand after placing orders. Not yet hooked into FM cycle.
  - Also takes a daily balance snapshot when invoked with `--snapshot`.

- **Schema migrations** — `paper_executions`, `paper_positions`, `paper_account_snapshots`. Idempotent `CREATE TABLE IF NOT EXISTS`.

### Config

- **`credentials.json`** — new `tradier_sandbox` block:
  ```json
  "tradier_sandbox": {
    "api_key": "...",
    "account_id": "..."
  }
  ```
- **`config.json`** — new `paper_trading` block:
  ```json
  "paper_trading": {
    "enabled": true,
    "polling_interval_seconds": 30,
    "default_close_conditions": {
      "take_profit_pct": 25,
      "stop_loss_pct": -30,
      "max_hold_days": 5
    }
  }
  ```
  (`default_close_conditions` is unused in Phase 1 — defined now so Phase B has a place to read from.)

### Acceptance criteria for Phase 1 "done"

1. `python tools/paper_trade.py --open --instrument option --symbol AAPL --option-symbol AAPL... --side buy_to_open --qty 1 --type market --tag manual_test` submits an order; CLI prints the Tradier order ID.
2. `python tools/paper_poll.py` polls the order, writes a row to `paper_executions`, creates a row in `paper_positions`.
3. `python tools/paper_trade.py --open --instrument stock --symbol AAPL --side buy --qty 10 --type market --tag manual_test` works end-to-end (equity path).
4. `python tools/paper_trade.py --positions` shows both open positions with current values.
5. `python tools/paper_trade.py --close --position-id N` submits a closing order; next `paper_poll.py` records the closing fill, updates `paper_positions` to CLOSED with realized P&L.
6. `python tools/paper_trade.py --pnl --tag manual_test` returns realized P&L for the day.
7. `python tools/paper_trade.py --balance` returns current cash, equity, buying power.
8. `python tools/paper_poll.py --snapshot` writes a row to `paper_account_snapshots`.

When all eight pass end-to-end, Phase 1 ships and we move to Phase B.

---

## 7. Open Questions / Deferred

Items we don't need to answer for Phase 1 but should track:

- **Sandbox account reset procedure.** Not documented publicly. Manual via WebUI? API call? Open a support ticket if/when paper buying power gets exhausted.
- **Sandbox rate limits.** Tradier says "loose enough." If the polling loop ever hits a 429, we'll back off and tune.
- **Multileg order support in sandbox.** Tradier docs imply yes (same endpoint, `class=multileg`, indexed leg params), but unverified. First straddle auto-paper attempt (Phase D earnings consumer) will confirm or surface an issue.
- **Polling cadence at scale.** With dozens of open positions, polling every 30s × multiple orders could chatter. May need to batch via `/v1/accounts/{id}/orders` (lists all orders in one call) rather than per-order polling.
- **Position reconciliation on restart.** If `paper_poll.py` dies mid-poll, on next run we should reconcile from Tradier's `GET /positions` rather than trusting only our local state. Phase 1 can ignore; flag for Phase B.
- **What if Tradier closes a position via expiration/assignment?** Options expiring ITM in the sandbox — does Tradier auto-exercise? Need to verify and decide how `paper_positions` reflects it. Likely handled by polling `GET /positions` and detecting the delta.
- **Preview support in the CLI.** Tradier's `preview=true` is valuable for sanity-checking. Phase 1 expose it as `--preview` flag on `--open`. Doesn't place, just prints estimated cost/commission/margin.
- **Cost of dual write to `performance.db`.** Phase C will need a metric write step; design when that consumer lands.

---

## 8. Risks

- **Quote-source ambiguity.** `paper_positions` value updates pull current quotes from Tradier. Equity and option quotes use the same `/markets/quotes` endpoint with different symbol formats. Verify both paths work in sandbox during Phase 1.
- **Decimal precision drift.** Follow CLAUDE.md decimal policy — `clean_database_row()` from `tools/decimal_formatter.py` before INSERT/UPDATE. Add `paper_*` text columns to the allowlist in `decimal_formatter.py` when we encounter the issue (per the precedent from `earnings_watchlist` `vol_balance_text`).
- **Sandbox data drift vs live.** A signal that paper-validates well at 15-min-delayed prices might not survive real-time slippage. Document the gap. Don't let "paper P&L looks great" make us complacent about real-trade execution risk.
- **Tag explosion.** Without convention discipline, tag namespace can become a wild west. The naming rules in §5.8 are the brake. If tags multiply past ~20 active, promote to a registry table.

---

## 9. Cross-References

- `core/` — existing Tradier client (live API). Paper client extends/wraps, doesn't replace.
- `docs/_local/trade_ingest/BRAINSTORM.md` — sibling schema (`trade_executions`) that `paper_executions` mirrors.
- `CLAUDE.md` — decimal policy, two-database workflow, console output design.
- `MEMORY.md` — once Phase 1 ships, write a topic file `paper_trading_2026-XX.md` and index it.
- Tradier API docs:
  - Sandbox base URL: <https://sandbox.tradier.com/v1/>
  - Endpoints overview: <https://docs.tradier.com/docs/endpoints>
  - Place order: <https://docs.tradier.com/reference/brokerage-api-trading-place-order>
  - Trading overview: <https://docs.tradier.com/docs/trading>

---

## 10. Change Log

| Date | Change | By |
|---|---|---|
| 2026-05-18 | Initial draft. End states A–E defined. Phase 1 (State A) scope set. | Ben + Claude |
| 2026-05-18 | **State A implementation shipped** — `core/tradier_paper.py`, `tools/paper_trading.py`, `tools/paper_trade.py`, `tools/paper_poll.py`, schema for `paper_executions` / `paper_positions` / `paper_account_snapshots`, decimal_formatter skip list extended. Partial-fill (delta tracking) and partial-close (qty decrement + running realized_pnl) verified by unit tests. Acceptance smoke test pending market open 2026-05-19. | Ben + Claude |
| 2026-05-19 | **State A acceptance test PASSED** end-to-end. Option order 30219623 (SPY 5/22 $740C) filled @ $3.14 at open, equity order 30266026 (10× SPY) filled @ $732.54; both closed manually (option @ $1.90, equity @ $732.25); realized P&L -$126.90 (tag=`manual-test`); balance snapshot for 2026-05-19 = $99,872.30. **Observed:** parallel close-order invocations triggered transient `database is locked` during market hours; reproducing with FM paused → no lock. **Confirmed root cause:** Flow Monitor concurrent writes to `data/datalake.db` exceed the 10s busy_timeout during peak scan bursts. Paper-trading code itself is correct. **Decision:** Phase B will move paper tables to a separate DB file (`data/paper.db`) to eliminate contention. State A keeps current location for now — known issue, loud failure mode, no auto-consumer running yet. | Ben + Claude |
| 2026-05-19 | **State B IMPLEMENTED.** New files: `tools/paper_close_engine.py` (standalone engine, Tradier-direct quotes, psutil instance guard, market-hours gating via Tradier clock, `--dry-run` mode), `tools/paper_migrate_to_paper_db.py` (one-shot migration), `scheduled_tasks/start_paper_engine.bat`. Schema additions: `paper_positions.closing_submitted_at` column, new `paper_pending_conditions` bridge table. State machine extended `open → closing → closed` (engine flips to `closing`, poller flips to `closed`). CLI gains `--update-conditions` subcommand + 6 condition flags (`--tp`/`--sl`/`--max-hold`/`--expire-before-dte`/`--target-above`/`--target-below`) on `--open` and `--update-conditions`. Paper tables migrated to `data/paper.db`; source rows preserved in `datalake.db` for one trading day before `--drop-source`. **Default-state assertion (deliberate):** manual `--open` without explicit condition flags creates an UNMONITORED position; engine ignores it. Config defaults exist for programmatic reference, not CLI auto-apply. | Ben + Claude |
