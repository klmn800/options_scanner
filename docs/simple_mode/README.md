# Simple Mode

Headless, collection-only daily cycle (PRD 0014, built 2026-10-19).

The scanner's lasting value is the intraday option-chain snapshots in `flow_options_scans`, which no affordable
historical source provides. Simple Mode keeps that collection running every trading day with no window, no
email and as few moving parts as possible. Analysis can be done later from the stored data.

Simple Mode is an option, not a replacement. Without `--simple-mode`, `main.py` behaves exactly as before.

## Switching modes

Which mode runs is decided by what the Task Scheduler task `\!main.py` (6:35 AM weekdays) launches:

| Mode | Task action | What you see |
|------|-------------|--------------|
| Full | `E:\options_scanner\scheduled_tasks\start_main.bat` | Windows Terminal tab "Options Scanner" |
| Simple | `wscript.exe "E:\options_scanner\scheduled_tasks\start_main_simple.vbs"` | Nothing (tray dot only) |

To switch, edit the task's action in Task Scheduler. Nothing else changes. The change takes effect at the next 6:35 run.

Manual runs:

```bash
python main.py --simple-mode                    # visible, in the current terminal
wscript scheduled_tasks\start_main_simple.vbs   # headless
```

## What runs

| Step | Full | Simple |
|------|:----:|:------:|
| 1.1 Morning OP, 1.2 EI, 1.3 Metadata, 1.4 Trade Ingest, 1.5 Query Sync | yes | - |
| 2 FM pre-market (alert resolution, sentiment, pre-market sync) | yes | - |
| 2.2 Trading Advisor launch | yes | - |
| 2 FM market hours: collector (9:15 pre-open scan, cycles, closing scan) | yes | yes |
| 2 FM market hours: analyzer, alerts, email, X posting, watchlist, news, dip detection, earnings signals, trade ingest, quick sync | yes | - |
| 2 FM 60s break between cycles | yes | after failed cycles only |
| 2 FM post-market: historical price backfill | yes | yes |
| 2 FM post-market: regime summary, symbol rollup, daily aggregate, evaluation, watchlist cleanup | yes | - |
| 3.1 Trade Ingest, 3.4 Final Query Sync | yes | - |
| 3.2 Evening Option Pipeline (EOD OI + volume, full universe) | yes | yes |
| 4.1 Daily Backup, 4.2 Autofix Review | yes | yes |
| 5.1 Weekly Backup, 5.4 Sector Archive (Fridays) | yes | yes |
| 5.2 FM Baseline, 5.3 Earnings Refresh (Fridays) | yes | - |
| 6.1 Performance Collection | yes | yes |
| 6.2 Symbol Health Check | yes | - |

Each FM cycle in Simple Mode still records session stats, the health report, the diagnostic log and the one-call
SPY/QQQ/VIX market snapshot (the only `market_daily_summary` writer left in Simple Mode).

Failed cycles keep the 60s break so a fast-failing outage cannot loop tightly. The existing 10-minute
connectivity tolerance before Autofix escalation is unchanged.

The skip list is fixed in code: `tools/simple_mode.py` (`SIMPLE_MODE_SKIPS`). Each skipped step logs one
`Skipped (simple mode): <step>` line.

## What that means for the data

- `flow_options_scans` gets the same rows as in full mode, but the analyzer columns (`significance_score`,
  `volume_change`, `underlying_change`, `premium_value`, `alert_reason`, ...) stay NULL on Simple Mode days. They are
  derived from snapshot differences and baselines, so they can be recomputed later.
- No `flow_alerts`, `flow_watchlist_daily`, `flow_symbol_summary` or `flow_daily_aggregates` rows on Simple
  Mode days. Switching back does not backfill them. (`option_symbol_summary` still updates: the evening Option
  Pipeline writes it.)
- `option_contracts` comes from the evening Option Pipeline only. The morning run was redundant: the evening
  run overwrites it (same `trade_date`, `INSERT OR REPLACE`), and OI matched FM's 9:15 scan on 2,216/2,216
  contracts checked.
- **`datalake_query.db` is frozen** at the last full-mode sync. Morning View, `tools/direct_db_query.py` (which
  defaults to the query DB) and anything else reading it see stale data. Before analyzing, either query
  `data/datalake.db` read-only (`--db data/datalake.db`) or run one full sync after hours (with approval;
  see CLAUDE.md).
- `symbol_baselines` stops refreshing (Friday step 5.2). Only the analyzer uses it.

## Tray heartbeat

`tools/simple_mode_tray.py` shows a dot in the system tray. It starts at sign-in through the Startup-folder
shortcut `Options Scanner Tray.lnk`, and it works in either mode.

| Dot | Meaning |
|-----|---------|
| Green | Trading day, collection window, a cycle completed in the last 30 min |
| Gray | Idle: before the open, after a healthy day, weekend or market holiday |
| Red | No completed cycle for 30 min during the collection window (or never started), or the day's collection stopped early. Stays red until a cycle completes. |

Entering red raises **one** Windows toast per incident. Nothing else pops up.

- Hover: one-line summary (state, cycles done, last cycle time, average cycle time).
- Left-click: health window. **Today**: state, cycles done/failed, last cycle, cycle times, last scan size,
  symbols with data, errors, rows today. **Last 5 trading days**: cycles, rows, average cycle,
  evening OP and daily backup result.
- Right-click: Health, Open today's log, Quit.

The tray only reads: `logs/daily_state.json`, the cached Tradier calendar
(`cache/market_calendar_calendar_2m.json`, refreshed by `main.py` every morning, so holidays and early closes
are handled), and `data/performance.db` (read-only). It never opens `datalake.db`. Its own errors go to
`logs/simple_mode_tray.log`.

```bash
python tools/simple_mode_tray.py --status                      # print state + panels, no GUI
python tools/simple_mode_tray.py --status --at "2026-10-20 11:20"  # evaluate at a given ET time
```

"Errors" in the Today panel counts only option-chain fetches that raised an exception to the collector.
Timeouts and HTTP errors handled inside the Tradier client show up as symbols without data instead.

## Logs

Everything the hidden console would show also goes to `logs/orchestrator_YYYY-MM-DD.log` (FM runs in-process,
so its cycle lines are there). "Open today's log" in the tray opens that file.

## Autofix

Autofix works the same in both modes, including its escalation email (Ben chose to keep it). Fix sessions open
visibly in Windows Terminal even though the scanner itself is hidden (verified 2026-10-19).

Each run records `run_mode` (`simple` or `full`) in `logs/daily_state.json`. The restart instructions in
`autofix/instructions/AUTO_FIX_INSTRUCTIONS.md` read it and restart the same mode:
`wscript scheduled_tasks\start_main_simple.vbs` for simple, `start python main.py` for full.

## Files

| File | Role |
|------|------|
| `tools/simple_mode.py` | `--simple-mode` state + fixed skip list |
| `main.py`, `main_runners.py` | Orchestrator skips; `--simple-mode` flag |
| `strategies/flow_monitor/fm_main.py` | FM cycle/post-market skips via `check_task_disabled()`; also accepts `--simple-mode` |
| `main_ui.py` | `daily_state.json`: `run_mode`, trading-day pinning, restart-safe |
| `scheduled_tasks/start_main_simple.vbs` | Headless launcher |
| `tools/simple_mode_tray.py` | Tray heartbeat + health window |
| `tasks/0014-prd-simple-mode.md`, `tasks/tasks-0014-prd-simple-mode.md` | PRD and task list (local only; `tasks/` is gitignored) |

## Fixes that shipped with it (both modes)

- A mid-day restart (Autofix) no longer wipes `daily_state.json`, so the morning's FM cycles stay in the
  session stats and in `performance.db` (10-13 had recorded 10 of 16 cycles).
- `daily_state.json` belongs to the cycle's trading day, so Friday runs that finish after midnight record
  Friday's FM cycles in `performance.db` instead of an empty Saturday row.
