"""Three-way earnings date comparison: Robinhood vs Finnhub vs yfinance"""
import json
import sqlite3
import yfinance as yf

# Robinhood data (source of truth)
rh_data = [
  {"symbol": "HPE", "date": "2026-03-09", "timing": "pm", "verified": True},
  {"symbol": "MTN", "date": "2026-03-09", "timing": "pm", "verified": True},
  {"symbol": "ORCL", "date": "2026-03-10", "timing": "pm", "verified": True},
  {"symbol": "CPB", "date": "2026-03-11", "timing": "am", "verified": True},
  {"symbol": "ADBE", "date": "2026-03-12", "timing": "pm", "verified": True},
  {"symbol": "DG", "date": "2026-03-12", "timing": "am", "verified": True},
  {"symbol": "JBL", "date": "2026-03-18", "timing": "am", "verified": True},
  {"symbol": "DLTR", "date": "2026-03-16", "timing": "am", "verified": True},
  {"symbol": "DOCU", "date": "2026-03-17", "timing": "pm", "verified": True},
  {"symbol": "GIS", "date": "2026-03-18", "timing": "am", "verified": True},
  {"symbol": "FIVE", "date": "2026-03-18", "timing": "pm", "verified": True},
  {"symbol": "LEN", "date": "2026-03-12", "timing": "pm", "verified": True},
  {"symbol": "MU", "date": "2026-03-18", "timing": "pm", "verified": True},
  {"symbol": "NKE", "date": "2026-03-31", "timing": "pm", "verified": True},
  {"symbol": "UEC", "date": "2026-03-10", "timing": "am", "verified": True},
  {"symbol": "ACN", "date": "2026-03-19", "timing": "am", "verified": True},
  {"symbol": "CCL", "date": "2026-03-20", "timing": "am", "verified": False},
  {"symbol": "DRI", "date": "2026-03-19", "timing": "am", "verified": True},
  {"symbol": "FDS", "date": "2026-03-31", "timing": "am", "verified": True},
  {"symbol": "FDX", "date": "2026-03-19", "timing": "pm", "verified": True},
  {"symbol": "MKC", "date": "2026-03-24", "timing": "am", "verified": False},
  {"symbol": "CNM", "date": "2026-03-24", "timing": "am", "verified": False},
  {"symbol": "CNXC", "date": "2026-03-24", "timing": "am", "verified": True},
  {"symbol": "CTAS", "date": "2026-03-25", "timing": "am", "verified": False},
  {"symbol": "GME", "date": "2026-03-24", "timing": "pm", "verified": False},
  {"symbol": "JEF", "date": "2026-03-25", "timing": "pm", "verified": False},
  {"symbol": "PAYX", "date": "2026-03-25", "timing": "am", "verified": False},
  {"symbol": "PII", "date": "2026-04-28", "timing": "am", "verified": False},
  {"symbol": "LULU", "date": "2026-03-17", "timing": "pm", "verified": True},
  {"symbol": "PVH", "date": "2026-03-30", "timing": "pm", "verified": False},
  {"symbol": "AES", "date": "2026-05-01", "timing": "am", "verified": False},
  {"symbol": "CAG", "date": "2026-04-01", "timing": "am", "verified": True},
  {"symbol": "LW", "date": "2026-04-01", "timing": "am", "verified": True},
  {"symbol": "XOM", "date": "2026-04-02", "timing": "pm", "verified": False},
]

rh_map = {r['symbol']: r for r in rh_data}

# Finnhub data from DB
conn = sqlite3.connect('data/datalake_query.db')
conn.row_factory = sqlite3.Row
fh_rows = conn.execute(
    'SELECT symbol, earnings_date, earnings_time FROM earnings_upcoming WHERE symbol IN ({})'.format(
        ','.join('?' * len(rh_map))), list(rh_map.keys())
).fetchall()
conn.close()
fh_map = {r['symbol']: {'date': r['earnings_date'], 'timing': r['earnings_time']} for r in fh_rows}

# yfinance data
yf_map = {}
for sym in rh_map:
    try:
        t = yf.Ticker(sym)
        cal = t.calendar
        if cal and 'Earnings Date' in cal and cal['Earnings Date']:
            yf_map[sym] = str(cal['Earnings Date'][0])
        else:
            yf_map[sym] = None
    except:
        yf_map[sym] = None

# Three-way comparison
print('{:6s} {:10s} {:5s} {:10s} {:4s} {:10s} {:4s}'.format(
    'SYM', 'RH Date', 'Ver', 'FH Date', 'FH?', 'YF Date', 'YF?'))
print('-' * 65)

fh_correct = 0
yf_correct = 0
both_correct = 0
neither = 0
total = len(rh_map)

for sym in sorted(rh_map.keys(), key=lambda s: rh_map[s]['date']):
    rh = rh_map[sym]
    fh = fh_map.get(sym, {})
    yf_date = yf_map.get(sym)

    rh_date = rh['date']
    fh_date = fh.get('date', '?')

    fh_match = 'OK' if fh_date == rh_date else 'MISS'
    yf_match = 'OK' if yf_date == rh_date else 'MISS'

    if fh_date == rh_date:
        fh_correct += 1
    if yf_date == rh_date:
        yf_correct += 1
    if fh_date == rh_date and yf_date == rh_date:
        both_correct += 1
    if fh_date != rh_date and yf_date != rh_date:
        neither += 1

    ver = 'YES' if rh['verified'] else 'no'
    print('{:6s} {:10s} {:5s} {:10s} {:4s} {:10s} {:4s}'.format(
        sym, rh_date, ver, fh_date, fh_match, str(yf_date), yf_match))

print()
print('=== ACCURACY vs ROBINHOOD (n={}) ==='.format(total))
print('Finnhub:  {}/{} ({:.0f}%)'.format(fh_correct, total, fh_correct * 100 / total))
print('yfinance: {}/{} ({:.0f}%)'.format(yf_correct, total, yf_correct * 100 / total))
print('Both right: {}  |  Neither right: {}'.format(both_correct, neither))
