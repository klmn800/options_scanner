# Plan: Paper Trading Platform — State B (Engine-Managed Exits)

> **Status:** IMPLEMENTED + acceptance tested 2026-05-19. Engine submitted closes for two test positions (`underlying_target_below` + `max_hold_days`), status state machine `open → closing → closed` verified, instance guard verified, unmonitored positions correctly ignored. Three of ten acceptance criteria (option DTE protection, take-profit-pct trip, market-closed gate) verified by code inspection rather than live trigger due to market-hours and contract-availability constraints.
> **Companion docs:** [`README.md`](README.md) (operational ref), [`DESIGN.md`](DESIGN.md) (source of truth), [`PHASE_1_PLAN.md`](PHASE_1_PLAN.md) (State A reference)

## Context

State A (shipped 2026-05-18, acceptance-tested 2026-05-19) gave us a manual paper-trading CLI. State B turns *closing* into infrastructure: positions carry their own close-conditions thesis, a standalone engine evaluates them on a fixed cadence and fires closing orders when conditions trip. Opens stay manual until State C ships the first auto-open consumer.

The platform should not bake in any specific signal (FM alerts, earnings, etc.). Close conditions are **declarative data**, not strategy code. The engine knows only how to read those conditions and act on them.

Full design context: `docs/paper_trading/DESIGN.md`. This plan turns the State B end-state into concrete code-level steps.

---

## Architecture decisions (grounded in exploration + State A learnings)

1. **`paper_close_engine.py` is a standalone runnable script**, not an integration into Flow Monitor or main.py. It's the whole loop in one file: read open positions → fetch fresh Tradier quotes → evaluate each position's conditions → submit closes for any that trip. Scheduled separately via Windows Task Scheduler, every 2 minutes during market hours.
2. **Tradier quotes direct, no piggybacking on `flow_options_scans`.** Sandbox feed is 15-min delayed but updates minute-by-minute. Decouples engine reliability from FM cycle state and avoids the lock contention that bit us in State A's acceptance test (confirmed FM concurrent writes to `datalake.db` were the cause).
3. **Paper tables move to `data/paper.db`.** Pre-emptively eliminates the contention before the engine starts hammering writes every cycle. One-shot migration ships as part of B; State A's existing rows preserved.
4. **Close conditions are NULL by default.** Manual `--open` without explicit condition flags creates an *unmonitored* position. The engine ignores positions with empty `close_conditions_json`. This is intentional — explicit > implicit. Auto-consumers in C+ will always pass conditions; the `paper_trading.default_close_conditions` config block exists for them to reference programmatically, not for the CLI to silently apply.
5. **3-state status machine: `open` → `closing` → `closed`.** The intermediate `closing` state prevents the engine from re-submitting close orders for a position whose previous close is still pending fill. `paper_poll.py` is the only thing that flips `closing → closed`.
6. **Six-condition vocabulary, all stateless.** No trailing stops, no peak-since-open tracking — those need state and add a layer we don't need yet. Anything stateful gets its own design pass when a real use case demands it.
7. **`--dry-run` ships with the engine.** Critical for validating condition logic without burning sandbox state.
8. **Instance guard via psutil**, mirroring `main.py:is_main_already_running()`. Same idiom Ben already trusts.

---

## ⚠️ Critical default-state assertion (read this before opening positions)

**Manually-opened paper positions are NOT auto-monitored unless you explicitly pass close-condition flags.**

```bash
# UNMONITORED — engine will never touch this position. You close it manually.
python tools/paper_trade.py --open --instrument stock --symbol SPY --side buy --qty 10 --type market

# MONITORED — engine auto-closes per these conditions.
python tools/paper_trade.py --open --instrument stock --symbol SPY --side buy --qty 10 --type market \
    --tp 25 --sl -30 --max-hold 5
```

This is the deliberate design call. Don't assume the config defaults apply automatically — they don't. Reason: the platform shouldn't silently take exit decisions you didn't ask for. Auto-consumers in C+ supply conditions explicitly; the CLI treats the human user as an adult.

To retrofit conditions onto an existing position: `paper_trade.py --update-conditions --position-id N --tp 25 --sl -30 --max-hold 5`. To remove conditions: `--update-conditions --position-id N --clear`.

---

## The condition vocabulary (v1)

`close_conditions_json` shape:

```json
{
  "schema_version": 1,
  "take_profit_pct": 25.0,
  "stop_loss_pct": -30.0,
  "max_hold_days": 5,
  "expire_before_dte": null,
  "underlying_target_above": null,
  "underlying_target_below": null
}
```

`null` = condition inactive. Engine fires a close on the **first** condition that trips (any-of, not all-of).

| Field | Meaning | Trip rule | Applies to |
|---|---|---|---|
| `take_profit_pct` | Float, positive | Close when `current_pnl_pct >= value` | All |
| `stop_loss_pct` | Float, negative | Close when `current_pnl_pct <= value` | All |
| `max_hold_days` | Int | Close when `now - opened_at >= value` calendar days | All |
| `expire_before_dte` | Int | Close option when DTE drops below value (default 1 → avoid auto-exercise) | Options only |
| `underlying_target_above` | Float | Close when underlying price ≥ value | All (options use underlying price, not option mid) |
| `underlying_target_below` | Float | Close when underlying price ≤ value | All |

Deferred to later phases: trailing stops, alert-resolution-based exits, IV-collapse-based exits. All can be added as new vocabulary entries without changing engine shape.

---

## Files to create

### `tools/paper_close_engine.py` (new — the engine)
Main loop:
1. Acquire instance lock via psutil scan; exit if another `paper_close_engine.py` is running.
2. Check market hours via existing utility (probably `core/tradier_api.py:get_market_clock()` or similar). Skip price-based evaluation if closed; still evaluate time-based conditions. **Configurable via `--ignore-market-hours` for manual testing.**
3. Open `data/paper.db`. Query all `paper_positions WHERE status = 'open' AND close_conditions_json IS NOT NULL`.
4. Batch-fetch quotes: collect distinct symbols (underlyings for everything, option symbols for option positions). Single `markets/quotes` call per batch where possible.
5. For each position, evaluate each non-null condition. First trip wins. Log the evaluation regardless of trip.
6. For tripped positions: submit close order via `TradierPaperBroker`, update `paper_positions.status = 'closing'`, record `close_reason = '<condition_name>'` and `closing_submitted_at = now()`.
7. `--dry-run` short-circuits step 6 — prints the trip but does not submit.

CLI flags:
- `--dry-run` — evaluate, log, don't submit
- `--ignore-market-hours` — run evaluation even when market closed
- `--position-id N` — evaluate only one position (testing)
- `--verbose` — log every position's evaluation, not just trips

Logging: writes to `data/paper_close_engine.log` (rotating, optional) and stdout. Each cycle prints summary: `N evaluated, M tripped, K orders submitted, L errors`.

### `tools/paper_migrate_to_paper_db.py` (new — one-shot)
- Creates `data/paper.db` with full paper_* schema via `_ensure_schema()`.
- Copies all rows from `data/datalake.db` paper_executions / paper_positions / paper_account_snapshots → `data/paper.db`.
- Verifies row counts match.
- Drops the three tables from `data/datalake.db` (with `--drop-source` flag; default = leave source intact for one cycle).
- Single-run, idempotent (re-running on already-migrated DB no-ops).

### `scheduled_tasks/start_paper_engine.bat` (new)
Standard `.bat` wrapper analogous to `start_main.bat`. Invokes `python tools/paper_close_engine.py`. Task Scheduler triggers every 2 minutes during market hours (6:30 AM – 1:15 PM PT, M-F).

---

## Files to modify

### `tools/paper_trading.py`
- Change `DATALAKE_DB_PATH` → `PAPER_DB_PATH = os.path.join(..., 'data', 'paper.db')`.
- Add `CLOSING` to allowed status values; `_ensure_schema()` updates the column check (or rely on convention if no constraint).
- New helper `parse_close_conditions(json_str) -> dict` — handles null/empty/malformed; returns dict with all 6 fields keyed null where absent.
- New helper `build_close_conditions(tp=None, sl=None, max_hold=None, ...) -> str` — produces JSON string, returns `None` if all args are None (= NULL in DB).
- Add `closing_submitted_at DATETIME` column to `paper_positions` schema (ALTER for existing DB on first run).

### `tools/paper_trade.py`
- `--open` gains: `--tp`, `--sl`, `--max-hold`, `--expire-before-dte`, `--target-above`, `--target-below`. All optional. If any provided, `close_conditions_json` is populated. If none, stays NULL.
- New `--update-conditions --position-id N [conditions...]` — updates an existing open position. `--clear` zeroes everything to NULL.
- `--close` (manual) — sets status to `closing` (not `closed` directly) and records `close_reason = 'manual'`. Status flip to `closed` still happens in `paper_poll.py`.
- `--positions` output gains a "Conditions" column showing a terse summary (e.g., `TP+25/SL-30/5d` or `unmonitored`).

### `tools/paper_poll.py`
- Adjust the close-order handling path: a fill on an order that was a `sell_to_close` / `sell` (for a previously `closing` position) flips status `closing → closed`. Today it flips `open → closed`; we need both transitions valid.
- No other behavior change.

### `core/tradier_paper.py`
- Verify `get_option_quote` returns option mid (or bid/ask we can mid). If not, add `get_option_chain_quote(option_symbol)` that pulls the chain row.
- Add `get_market_clock()` if it doesn't exist in `tradier_api.py` already — engine needs to know if market is open. (Check first; likely already exists.)

### `docs/paper_trading/README.md`
- New section: "Close Conditions Vocabulary" — the table above + null-default warning.
- New section: "Close Engine — Cadence and Behavior" — Task Scheduler cadence, market-hours-only default, status state machine, dry-run usage.
- Update flow diagrams: open → (manual flag) → engine cycle → trip → close order → poll → closed.

### `docs/paper_trading/DESIGN.md`
- Section 2.B updated to reflect "NULL default" + "6-condition vocabulary" decisions.
- Change Log entry on completion.

### `CLAUDE.md` Paper Trading block
- Add: `python tools/paper_close_engine.py --dry-run`, `--position-id N`.
- Add: `python tools/paper_trade.py --update-conditions --position-id N --tp 25 --sl -30 --max-hold 5`.
- Add: `--open ... --tp 25 --sl -30 --max-hold 5` to the equity/option example.

---

## Implementation sequence

1. **Migration first.** Build + run `paper_migrate_to_paper_db.py`. Verify all State A rows in `data/paper.db`. Don't drop from `datalake.db` yet — keep a safety copy for one trading day.
2. **`paper_trading.py` rewrites** — DB path, schema additions, helpers. CLI still works against new DB.
3. **`paper_trade.py` extensions** — add `--tp/--sl/--max-hold/...` to `--open`; build `--update-conditions`. Status logic stays valid (manual close still ends in `closed` after poll).
4. **`paper_poll.py` transition fix** — handle `closing → closed`.
5. **Engine v1** — read positions, fetch quotes, evaluate, log. `--dry-run` only. No actual order submission yet.
6. **Engine v2** — wire up real close-order submission. Test against a deliberately-opened SPY position with `--tp 1` to force a trip on the first cycle.
7. **`start_paper_engine.bat` + Task Scheduler entry**. Run for one trading day in `--dry-run` mode to validate condition evaluation against real market data. Switch to live submissions next day.
8. **Drop paper tables from `datalake.db`** once a full day of clean operation against `paper.db` is confirmed.
9. **Docs pass** — README, CLAUDE.md, DESIGN.md change log.

---

## Critical files to read before editing

- `tools/paper_trading.py` — current schema, `_ensure_schema()` pattern
- `tools/paper_trade.py` — `cmd_open`, `cmd_close` for status transition logic
- `tools/paper_poll.py` — fill processing, `_recorded_qty` idempotency
- `core/tradier_paper.py` — broker order/quote methods
- `core/tradier_api.py` — market clock helper (if exists), rate limiter
- `main.py:106` — `is_main_already_running()` pattern to mirror
- `scheduled_tasks/start_main.bat` — `.bat` wrapper pattern

---

## Verification (end-to-end)

1. **Migration:** `paper.db` exists, row counts match `datalake.db` originals.
2. **Unmonitored open:** Open SPY 10 shares with no conditions. Engine runs, ignores the position. Status stays `open` indefinitely.
3. **Monitored open:** Open SPY 10 shares with `--tp 1 --sl -10`. Engine fires close on next cycle (TP almost certain to trip with delayed quote drift). Status flows `open → closing → closed`. `close_reason = 'take_profit_pct'`.
4. **Time-based:** Open with `--max-hold 0` (= 1 calendar day). Run engine on next-day's cycle. Closes regardless of market hours setting (time-based path always evaluates).
5. **Option DTE protection:** Open an option position with `--expire-before-dte 2`. Advance time (or set a contract <= 2 DTE). Engine closes it.
6. **Underlying targets:** Open SPY $740C with `--target-above 750`. Engine closes when SPY underlying ≥ 750.
7. **Update conditions:** Manually update an open position's conditions. Engine respects the new conditions on next cycle.
8. **Dry-run:** `--dry-run` on a tripped position prints the trip but submits nothing; status unchanged.
9. **Instance guard:** Launch two engines simultaneously. Second exits cleanly with "already running" message.
10. **Market closed:** Engine run after 1:15 PM PT skips price-based eval, still evaluates time-based. `--ignore-market-hours` overrides.

---

## Risks / open items

- **Market clock helper.** Need to confirm whether one exists in `core/tradier_api.py`. If not, write one (Tradier `/markets/clock` endpoint). Low complexity, blocker-level if missed.
- **Option quote mid vs option chain row.** `get_option_quote(occ_symbol)` should return bid/ask; we compute mid. Need to verify against actual sandbox response. If the endpoint is different, add a small helper.
- **Stuck-in-closing state.** If a close order is rejected by Tradier (sandbox glitch, contract expired, etc.), the position stays in `closing` forever. v1: log warning, leave state, manual intervention via direct SQL or a new `--unstick` CLI command. v2 (deferred): auto-revert to `open` after N failed retries.
- **Quote batching efficiency.** With multiple open positions, single `markets/quotes` call per cycle for all underlyings is ideal. Option quotes may need one call per option. Acceptable until position count > 50.
- **Rate-limit interaction.** `tradier_limiter` already exists in `core/tradier_api.py`. Engine inherits it via `TradierAPI`. No special handling needed.
- **Time-based eval and DST.** "5 calendar days" math should use naive UTC or eastern; pick one and document. Lean toward eastern since market clock is eastern.
- **First-cycle dry-run safety net.** Strong convention: ship with engine in `--dry-run` mode for the first deployment day. Switch to live submissions only after one day of clean logs.
