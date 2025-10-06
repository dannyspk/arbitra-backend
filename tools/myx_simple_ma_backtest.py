#!/usr/bin/env python3
"""Simple SMA crossover backtest on MYX 15m data filtered from 2025-09-30.
- Inputs: var/myx_15m.csv
- Filters rows from 2025-09-30 00:00:00 UTC onwards
- Strategy: long-only SMA short (20) crosses above SMA long (50). Exit on cross down.
- Position sizing: fixed $1,000 notional per trade
- Entry/exit executed at next bar open (to avoid lookahead); if next open not available, skip.
- Outputs:
  - var/myx_simple_ma_trades.csv
  - var/myx_simple_ma_equity.csv
  - var/myx_simple_ma_summary.json
"""
from datetime import datetime, timezone
import pandas as pd
import os
import json

INPUT = 'var/myx_15m.csv'
START_DATE = '2025-09-30T00:00:00+00:00'
SHORT = 20
LONG = 50
NOTIONAL = 1000.0

os.makedirs('var', exist_ok=True)

def rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.ewm(com=(period-1), adjust=False).mean()
    ma_down = down.ewm(com=(period-1), adjust=False).mean()
    rs = ma_up / (ma_down.replace(0, 1e-12))
    return 100 - (100 / (1 + rs))

# Load
df = pd.read_csv(INPUT)
# convert timestamp ms to UTC datetime
if df['timestamp'].dtype.kind in ('i','f'):
    df['dt'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)
else:
    # in case it's string
    df['dt'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)

# keep only from start date
start_ts = pd.to_datetime(START_DATE, utc=True)
df = df[df['dt'] >= start_ts].reset_index(drop=True)
if df.empty:
    print('No rows after', START_DATE)
    raise SystemExit(1)

# convert numeric columns
for c in ['open','high','low','close','volume']:
    df[c] = pd.to_numeric(df[c], errors='coerce')

# indicators
df['sma_short'] = df['close'].rolling(SHORT, min_periods=1).mean()
df['sma_long'] = df['close'].rolling(LONG, min_periods=1).mean()
df['rsi'] = rsi(df['close'], period=14)

# backtest
cash = 10000.0
position = 0.0  # size in base asset
entry_price = None
entry_time = None
trades = []
equity = []

n = len(df)
for i in range(n-1):
    # evaluate crossover using previous vs current on sma values
    prev_short = df.loc[i, 'sma_short']
    prev_long = df.loc[i, 'sma_long']
    cur_short = df.loc[i+1, 'sma_short']
    cur_long = df.loc[i+1, 'sma_long']

    # record equity at current bar (use close)
    cur_price = df.loc[i, 'close']
    cur_equity = cash + (position * cur_price)
    equity.append({'dt': df.loc[i, 'dt'].isoformat(), 'equity': cur_equity})

    # generate entry signal: short crosses above long between i and i+1
    enter = (prev_short <= prev_long) and (cur_short > cur_long)
    exit = (position > 0) and (prev_short >= prev_long) and (cur_short < cur_long)

    # execute entry at next bar open (i+1 open) if available
    if enter and position == 0:
        # entry at bar i+1 open
        entry_idx = i+1
        if entry_idx+0 < n:
            entry_price = df.loc[entry_idx, 'open']
            size = NOTIONAL / entry_price
            position = size
            entry_time = df.loc[entry_idx, 'dt']
        else:
            # cannot execute (no next open)
            continue

    # execute exit at next bar open (i+1 open) if exit condition true
    if exit and position > 0:
        exit_idx = i+1
        if exit_idx+0 < n:
            exit_price = df.loc[exit_idx, 'open']
            pnl = (exit_price - entry_price) * position
            cash += pnl
            trades.append({
                'entry_time': entry_time.isoformat(),
                'entry_price': float(entry_price),
                'exit_time': df.loc[exit_idx, 'dt'].isoformat(),
                'exit_price': float(exit_price),
                'size': float(position),
                'pnl': float(pnl)
            })
            # reset
            position = 0.0
            entry_price = None
            entry_time = None
        else:
            continue

# final equity record at last bar
final_price = df.loc[n-1, 'close']
final_equity = cash + (position * final_price)
equity.append({'dt': df.loc[n-1, 'dt'].isoformat(), 'equity': final_equity})

# write trades
trades_df = pd.DataFrame(trades)
trades_df.to_csv('var/myx_simple_ma_trades.csv', index=False)
# write equity
eq_df = pd.DataFrame(equity)
eq_df.to_csv('var/myx_simple_ma_equity.csv', index=False)

# summary
total_pnl = sum(t['pnl'] for t in trades)
wins = [t['pnl'] for t in trades if t['pnl'] > 0]
losses = [t['pnl'] for t in trades if t['pnl'] <= 0]
win_rate = (len(wins) / len(trades)) if trades else 0.0
avg_pnl = (sum(t['pnl'] for t in trades) / len(trades)) if trades else 0.0
max_drawdown = 0.0
# compute drawdown from equity series
eq_vals = [e['equity'] for e in equity]
peak = -1e12
for v in eq_vals:
    if v > peak:
        peak = v
    dd = (peak - v)
    if dd > max_drawdown:
        max_drawdown = dd

summary = {
    'start': df.loc[0, 'dt'].isoformat(),
    'end': df.loc[n-1, 'dt'].isoformat(),
    'bars': n,
    'trades': len(trades),
    'total_pnl': total_pnl,
    'final_equity': final_equity,
    'win_rate': win_rate,
    'avg_pnl': avg_pnl,
    'max_drawdown': max_drawdown
}
with open('var/myx_simple_ma_summary.json', 'w', encoding='utf8') as f:
    json.dump(summary, f, indent=2)

print('Done. Summary:')
print(json.dumps(summary, indent=2))
