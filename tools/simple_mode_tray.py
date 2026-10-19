#!/usr/bin/env python3
"""
Simple Mode tray heartbeat (PRD 0014)
-------------------------------------
A system-tray dot that shows whether Flow Monitor collection is healthy, plus a
small health window. It only READS files and never writes to any database or
state file, so it cannot affect collection. Its own errors go to
logs/simple_mode_tray.log.

States (evaluated every 60s):
    GREEN  trading day, collection window, a cycle completed in the last 30 min
    GRAY   idle: before the open, after a healthy day, weekend or market holiday
    RED    trading day with no completed cycle for 30 min during the collection
           window (or never started), or the day's collection stopped early.
           Entering red raises ONE Windows toast; it re-arms after recovery.

Sources:
    logs/daily_state.json            today's FM session (rewritten after every cycle)
    cache/market_calendar_*.json     trading days + close times (refreshed by main.py)
    data/performance.db (read-only)  daily history for the weekly panel
    data/datalake.db (read-only)     row-count cross-check, health window only

Usage:
    pythonw tools/simple_mode_tray.py                       # tray icon (start at login)
    python tools/simple_mode_tray.py --status               # print state + panels, no GUI
    python tools/simple_mode_tray.py --status --at "2026-10-19 15:10"   # evaluate at a given ET time
"""

import argparse
import json
import logging
import os
import queue
import sqlite3
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.timezone_utils import now_eastern  # noqa: E402

DAILY_STATE = os.path.join(ROOT, 'logs', 'daily_state.json')
CALENDAR_CACHE = os.path.join(ROOT, 'cache', 'market_calendar_calendar_2m.json')
PERFORMANCE_DB = os.path.join(ROOT, 'data', 'performance.db')
DATALAKE_DB = os.path.join(ROOT, 'data', 'datalake.db')
LOG_DIR = os.path.join(ROOT, 'logs')

STALE_MINUTES = 30          # red after this long without a completed cycle
CLOSE_GRACE_MINUTES = 25    # closing scan finishes ~10-15 min after the close
POLL_MS = 60 * 1000
COLORS = {'green': (46, 160, 67), 'gray': (140, 140, 140), 'red': (215, 58, 73)}


# ── Data loading (all read-only) ─────────────────────────────────────────

def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _connect_ro(path):
    return sqlite3.connect('file:{}?mode=ro'.format(path.replace('\\', '/')), uri=True, timeout=5)


def load_calendar():
    """Cached Tradier calendar written by main.py's holiday check: {date: day_info}."""
    cached = _read_json(CALENDAR_CACHE) or {}
    days = {}
    for month in (cached.get('data') or {}).get('months', {}).values():
        info = month.get('calendar', month) if isinstance(month, dict) else {}
        day_list = (info.get('days') or {}).get('day', []) if isinstance(info, dict) else []
        if isinstance(day_list, dict):
            day_list = [day_list]
        for day in day_list:
            if isinstance(day, dict) and day.get('date'):
                days[day['date']] = day
    return days


def trading_session(date, calendar):
    """(open, close) datetimes for a trading day, or None if the market is closed.

    Falls back to weekday 9:30-16:00 when the date is outside the cached calendar.
    """
    if date.weekday() >= 5:
        return None
    day = calendar.get(date.strftime('%Y-%m-%d'))
    if day is not None and day.get('status') != 'open':
        return None
    hours = (day or {}).get('open') or {}
    start = hours.get('start', '09:30')
    end = hours.get('end', '16:00')

    def _at(hhmm):
        h, m = (int(x) for x in hhmm.split(':'))
        return date.replace(hour=h, minute=m, second=0, microsecond=0)
    return _at(start), _at(end)


def load_fm_session(date_str):
    """Today's FM session from daily_state.json, or ({}, None) if it isn't today's."""
    state = _read_json(DAILY_STATE) or {}
    if state.get('date') != date_str:
        return {}, None
    return state.get('fm_session') or {}, state.get('run_mode')


def completed_cycles(fm, tz):
    """List of (start, end) datetimes for successful cycles."""
    cycles = []
    stamps = fm.get('scan_timestamps', [])
    times = fm.get('cycle_times', [])
    for i, ts in enumerate(stamps):
        if not ts or i >= len(times):
            continue
        try:
            start = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
        except ValueError:
            continue
        cycles.append((start, start + timedelta(seconds=times[i] or 0)))
    return cycles


# ── State ─────────────────────────────────────────────────────────────────

def evaluate(now, calendar=None):
    """Return the tray state for `now` (an aware ET datetime)."""
    calendar = load_calendar() if calendar is None else calendar
    date_str = now.strftime('%Y-%m-%d')
    fm, run_mode = load_fm_session(date_str)
    cycles = completed_cycles(fm, now.tzinfo)
    last_end = max((end for _, end in cycles), default=None)
    session = trading_session(now, calendar)

    st = {'now': now, 'fm': fm, 'run_mode': run_mode, 'cycles': cycles, 'last_end': last_end,
          'session': session, 'rows_today': sum(fm.get('contracts_collected', []) or [0])}

    def _set(state, headline):
        st['state'], st['headline'] = state, headline
        return st

    if session is None:
        return _set('gray', 'Idle - market closed today')
    open_t, close_t = session
    stale = timedelta(minutes=STALE_MINUTES)
    if now < open_t:
        if cycles:
            return _set('gray', 'Pre-open scan done - waiting for the open')
        return _set('gray', 'Idle - waiting for the open')
    if now <= close_t + timedelta(minutes=CLOSE_GRACE_MINUTES):
        ref = last_end or open_t
        if now - ref >= stale:
            if last_end is None:
                return _set('red', 'No cycles today - collection has not started')
            return _set('red', 'No completed cycle since {}'.format(last_end.strftime('%H:%M')))
        if last_end is None:
            return _set('green', 'Market open - first cycle running')
        return _set('green', 'Collecting')
    # After the collection window
    if last_end is None:
        return _set('red', 'No cycles today')
    if close_t - last_end > stale:
        return _set('red', 'Collection stopped at {}'.format(last_end.strftime('%H:%M')))
    return _set('gray', 'Done for today')


def _fmt_dur(seconds):
    seconds = int(round(seconds or 0))
    return '{}m{:02d}s'.format(seconds // 60, seconds % 60)


def tooltip(st):
    """One line, kept under Windows' 127-char tooltip limit."""
    parts = ['Options Scanner: ' + st['headline']]
    times = st['fm'].get('cycle_times') or []
    if st['cycles']:
        parts.append('{} cycles done'.format(len(st['cycles'])))
        parts.append('last {}'.format(st['last_end'].strftime('%H:%M')))
    if times:
        parts.append('avg {}'.format(_fmt_dur(sum(times) / len(times))))
    return ' · '.join(parts)[:127]


# ── Health panels ─────────────────────────────────────────────────────────

def today_panel(st, include_db_count=True):
    fm, now = st['fm'], st['now']
    lines = ['TODAY  {}'.format(now.strftime('%a %Y-%m-%d %H:%M ET')),
             '  State:          {} - {}'.format(st['state'].upper(), st['headline']),
             '  Run mode:       {}'.format(st['run_mode'] or 'unknown')]
    if not fm:
        lines.append('  No Flow Monitor cycles recorded today.')
        return lines
    times = fm.get('cycle_times') or []
    coll = fm.get('collection_times') or []
    lines.append('  Cycles:         {} completed, {} failed'.format(
        fm.get('successful_cycles', 0), fm.get('failed_cycles', 0)))
    if st['cycles']:
        start, end = max(st['cycles'], key=lambda c: c[1])
        ago = int((now - end).total_seconds() // 60)
        lines.append('  Last cycle:     started {}, finished {} ({} min ago)'.format(
            start.strftime('%H:%M:%S'), end.strftime('%H:%M:%S'), max(ago, 0)))
    if times:
        lines.append('  Cycle time:     avg {} | fastest {} | slowest {}'.format(
            _fmt_dur(sum(times) / len(times)), _fmt_dur(min(times)), _fmt_dur(max(times))))
    if coll:
        lines.append('  Avg collection: {}'.format(_fmt_dur(sum(coll) / len(coll))))
    contracts = fm.get('contracts_collected') or []
    if contracts:
        lines.append('  Last scan:      {:,} contracts'.format(contracts[-1]))
    attempted = fm.get('symbols_attempted') or []
    with_data = fm.get('symbols_with_data') or []
    if attempted and with_data:
        lines.append('  Symbols:        {} with data / {} attempted'.format(with_data[-1], attempted[-1]))
    errors = {k: v for k, v in (fm.get('errors_by_type') or {}).items() if v}
    lines.append('  Errors:         {}'.format(
        ', '.join('{} {}'.format(v, k) for k, v in errors.items()) if errors else 'none'))
    rows_line = '  Rows today:     {:,}'.format(st['rows_today'])
    if include_db_count:
        rows_line += '  (database: {})'.format(_db_rows_today(now.strftime('%Y-%m-%d')))
    lines.append(rows_line)
    return lines


def _db_rows_today(date_str):
    try:
        conn = _connect_ro(DATALAKE_DB)
        try:
            n = conn.execute('SELECT COUNT(*) FROM flow_options_scans WHERE trade_date = ?',
                             (date_str,)).fetchone()[0]
        finally:
            conn.close()
        return '{:,}'.format(n)
    except sqlite3.Error as e:
        return 'unavailable ({})'.format(e)


def previous_trading_days(now, calendar, count=5):
    days, d = [], now
    while len(days) < count:
        d = d - timedelta(days=1)
        if trading_session(d, calendar) is not None:
            days.append(d.strftime('%Y-%m-%d'))
    return days


def week_panel(now, calendar):
    lines = ['LAST 5 TRADING DAYS',
             '  {:<14} {:>6} {:>11} {:>10}  {:<10} {:<6}'.format(
                 'Date', 'Cycles', 'Rows', 'Avg cycle', 'Evening OP', 'Backup')]
    try:
        conn = _connect_ro(PERFORMANCE_DB)
    except sqlite3.Error as e:
        return lines + ['  performance.db unavailable ({})'.format(e)]

    def _flag(sql, date_str):
        row = conn.execute(sql, (date_str,)).fetchone()
        return None if row is None else bool(row[0])

    legacy_friday = False
    try:
        for date_str in previous_trading_days(now, calendar):
            n, avg, rows = conn.execute(
                'SELECT COUNT(*), AVG(cycle_seconds), SUM(contracts_collected) '
                'FROM fm_cycle_performance WHERE trade_date = ?', (date_str,)).fetchone()
            op_sql = "SELECT success FROM op_pipeline_performance WHERE trade_date = ? AND run_type = 'evening'"
            bk_sql = "SELECT success FROM backup_performance WHERE trade_date = ? AND backup_type = 'daily'"
            op, bk = _flag(op_sql, date_str), _flag(bk_sql, date_str)
            if op is None and bk is None:
                # Before 2026-10-19, Friday runs ending after midnight were
                # recorded under Saturday's date (fixed in PRD 0014 task 3B)
                nxt = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                op, bk = _flag(op_sql, nxt), _flag(bk_sql, nxt)
                legacy_friday = legacy_friday or not n

            def _ok(v):
                return '-' if v is None else ('OK' if v else 'FAILED')
            day = datetime.strptime(date_str, '%Y-%m-%d').strftime('%a %m-%d')
            lines.append('  {:<14} {:>6} {:>11} {:>10}  {:<10} {:<6}'.format(
                day, n or '-', '{:,}'.format(rows) if rows else '-',
                _fmt_dur(avg) if avg else '-', _ok(op), _ok(bk)))
    finally:
        conn.close()
    if legacy_friday:
        lines.append('  (Fridays before 2026-10-19 have no cycle history: Phase 6 ran after midnight and missed it.)')
    return lines


def render(st, calendar, include_db_count=True):
    return '\n'.join(today_panel(st, include_db_count) + [''] + week_panel(st['now'], calendar))


# ── Tray GUI ──────────────────────────────────────────────────────────────

def _icon_image(state):
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((6, 6, 58, 58), fill=COLORS[state] + (255,), outline=(255, 255, 255, 255), width=3)
    return img


def _open_todays_log():
    path = os.path.join(LOG_DIR, 'orchestrator_{}.log'.format(now_eastern().strftime('%Y-%m-%d')))
    os.startfile(path if os.path.exists(path) else LOG_DIR)


def _single_instance():
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\OptionsScannerSimpleModeTray')
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def run_tray(at=None, poll_ms=POLL_MS):
    """Run the tray icon. `at` pins the evaluation time (testing only)."""
    import tkinter as tk
    import pystray

    def clock():
        return at or now_eastern()

    if not _single_instance():
        return 0

    events = queue.Queue()
    root = tk.Tk()
    root.withdraw()
    window = {'top': None, 'text': None}
    current = {'state': None}

    icon = pystray.Icon(
        'options_scanner', _icon_image('gray'), 'Options Scanner: starting',
        menu=pystray.Menu(
            pystray.MenuItem('Health', lambda: events.put('show'), default=True),
            pystray.MenuItem("Open today's log", lambda: events.put('log')),
            pystray.MenuItem('Quit', lambda: events.put('quit'))))

    def refresh_window():
        if window['top'] is None:
            return
        text = window['text']
        text.config(state='normal')
        text.delete('1.0', 'end')
        text.insert('1.0', render(evaluate(clock()), load_calendar()))
        text.config(state='disabled')

    def show_window():
        if window['top'] is not None:
            window['top'].deiconify()
            window['top'].lift()
            refresh_window()
            return
        top = tk.Toplevel(root)
        top.title('Options Scanner - Health')
        text = tk.Text(top, font=('Consolas', 10), width=92, height=26, padx=10, pady=8)
        text.pack(fill='both', expand=True)
        bar = tk.Frame(top)
        bar.pack(fill='x')
        tk.Button(bar, text='Refresh', command=refresh_window).pack(side='left', padx=6, pady=6)
        tk.Button(bar, text='Close', command=lambda: close_window()).pack(side='right', padx=6, pady=6)
        top.protocol('WM_DELETE_WINDOW', lambda: close_window())
        window['top'], window['text'] = top, text
        refresh_window()
        top.lift()
        top.focus_force()

    def close_window():
        if window['top'] is not None:
            window['top'].destroy()
            window['top'] = window['text'] = None

    def poll():
        try:
            st = evaluate(clock())
            icon.icon = _icon_image(st['state'])
            icon.title = tooltip(st)
            if st['state'] != current['state']:
                logging.info('State %s -> %s: %s', current['state'], st['state'], st['headline'])
            if st['state'] == 'red' and current['state'] != 'red':
                icon.notify(st['headline'], 'Options Scanner')
                logging.info('Toast: %s', st['headline'])
            current['state'] = st['state']
        except Exception:
            logging.exception('Tray poll failed')
        root.after(poll_ms, poll)

    def pump():
        try:
            while True:
                event = events.get_nowait()
                if event == 'show':
                    show_window()
                elif event == 'log':
                    _open_todays_log()
                elif event == 'quit':
                    icon.stop()
                    root.quit()
                    return
        except queue.Empty:
            pass
        except Exception:
            logging.exception('Tray event failed')
        root.after(200, pump)

    icon.run_detached()
    root.after(500, poll)
    root.after(200, pump)
    root.mainloop()
    return 0


def main():
    parser = argparse.ArgumentParser(description='Simple Mode tray heartbeat (PRD 0014)')
    parser.add_argument('--status', action='store_true', help='Print state and health panels, no GUI')
    parser.add_argument('--at', metavar='"YYYY-MM-DD HH:MM"', help='Evaluate at this ET time (testing)')
    parser.add_argument('--poll-seconds', type=int, default=POLL_MS // 1000, help='Poll interval (testing)')
    args = parser.parse_args()

    at = None
    if args.at:
        at = datetime.strptime(args.at, '%Y-%m-%d %H:%M').replace(tzinfo=now_eastern().tzinfo)

    if args.status:
        if sys.stdout:
            sys.stdout.reconfigure(encoding='utf-8')
        now = at or now_eastern()
        calendar = load_calendar()
        st = evaluate(now, calendar)
        print('Tooltip: ' + tooltip(st))
        print()
        print(render(st, calendar))
        return 0

    logging.basicConfig(filename=os.path.join(LOG_DIR, 'simple_mode_tray.log'), level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')
    logging.info('Tray started (pid %s)%s', os.getpid(), ' at=' + args.at if args.at else '')
    try:
        return run_tray(at, args.poll_seconds * 1000)
    except Exception:
        logging.exception('Tray crashed')
        return 1


if __name__ == '__main__':
    sys.exit(main())
