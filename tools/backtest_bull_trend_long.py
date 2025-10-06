#!/usr/bin/env python3
"""Simple backtest for a bull-trend-first strategy on 15m MYX data.
This flips the rules from backtest_bear_trend_short.py:
- Use only data from 2025-09-30 onwards.
- Default: maintain a long bias (logic mirrors the bear script but inverted).
- Short entry: if price has risen >7% in 15m AND >12% in 30m AND >15% in 60m -> open a short, close any long.
  - Shorts have a tight SL and TP (SL=1% above entry, TP=2% below entry).
- Long quick wins: if price has fallen >5% in 15m -> open a long (no SL).
- Position size: 10% of equity for each new position.
- No leverage; pnl = price diff * size.

Outputs:
- var/bulltrend_trades.csv (one row per closed trade)
- var/bulltrend_equity.csv (equity per bar)
"""
from datetime import datetime, timezone
import pandas as pd
import os

CSV = 'var/myx_15m.csv'
OUT_TRADES = 'var/bulltrend_trades.csv'
OUT_EQ = 'var/bulltrend_equity.csv'

if not os.path.exists(CSV):
    raise SystemExit('CSV not found: ' + CSV)

# Load
df = pd.read_csv(CSV)
# timestamp in ms
df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)
# ensure numeric
for c in ['open','high','low','close','volume']:
    df[c] = pd.to_numeric(df[c], errors='coerce')

# Filter from 2025-09-30 00:00:00 UTC
start_dt = pd.Timestamp('2025-09-30T00:00:00Z')
df = df[df['timestamp'] >= start_dt].reset_index(drop=True)
if df.empty:
    raise SystemExit('No data after 2025-09-30 in ' + CSV)

# Strategy params
equity = 10000.0
risk_pct = 0.10  # position size = 10% of equity
short_sl_pct = 0.01
short_tp_pct = 0.02

trades = []  # list of dicts for closed trades
eq_history = []

position = None  # None / dict with keys side, entry_price, size, entry_time, amount

# Helper to close position
def close_position(ts, price):
    global equity, position, trades
    if position is None:
        return
    side = position['side']
    size = position['size']
    entry = position['entry_price']
    amount = position['amount']
    if side == 'long':
        gross = (price - entry) * size
    else:
        gross = (entry - price) * size
    pnl = gross
    equity += pnl
    trades.append({
        'side': side,
        'entry_time': position['entry_time'].isoformat(),
        'entry': entry,
        'size': size,
        'exit_time': ts.isoformat(),
        'exit': price,
        'gross_pnl': gross,
        'pnl': pnl,
        'equity': equity,
    })
    position = None

# Helper to open position (closes existing first)
def open_position(side, ts, price):
    global position, equity
    if position is not None:
        # close existing at current price
        close_position(ts, price)
    amount = equity * risk_pct
    size = amount / price if price > 0 else 0
    position = {'side': side, 'entry_price': price, 'size': size, 'entry_time': ts, 'amount': amount}

# Iterate bars
for idx, row in df.iterrows():
    ts = row['timestamp']
    price = float(row['close'])

    # record eq with unrealized PnL if position exists
    unreal = 0.0
    if position is not None:
        if position['side'] == 'long':
            unreal = (price - position['entry_price']) * position['size']
        else:
            unreal = (position['entry_price'] - price) * position['size']
    eq_history.append({'timestamp': ts.isoformat(), 'equity': equity + unreal})

    # compute percent changes against previous bars if available
    def pct_change_bars(n):
        if idx - n < 0:
            return None
        prev = df.at[idx - n, 'close']
        if prev == 0 or pd.isna(prev):
            return None
        return (price - prev) / prev * 100.0

    pct_15 = pct_change_bars(1)
    pct_30 = pct_change_bars(2)
    pct_60 = pct_change_bars(4)

    # Short condition (flipped): risen >7% (15m) AND >12% (30m) AND >15% (60m)
    short_signal = False
    if pct_15 is not None and pct_30 is not None and pct_60 is not None:
        if (pct_15 >= 7.0) and (pct_30 >= 12.0) and (pct_60 >= 15.0):
            short_signal = True

    # Long quick condition (flipped): fallen >5% in 15m
    long_quick_signal = False
    if pct_15 is not None and pct_15 <= -5.0:
        long_quick_signal = True

    # If short signal: close long and open short
    if short_signal:
        # only open a short if not already short (avoid replacing existing short positions)
        if position is None or position['side'] != 'short':
            # close any long and open short
            open_position('short', ts, price)
            # set short's SL/TP inside position dict (SL above entry, TP below)
            position['sl_price'] = position['entry_price'] * (1 + short_sl_pct)
            position['tp_price'] = position['entry_price'] * (1 - short_tp_pct)
        continue

    # If currently short, check SL/TP
    if position is not None and position['side'] == 'short':
        if price >= position.get('sl_price', 1e-12):
            close_position(ts, price)
            continue
        if price <= position.get('tp_price', -1e12):
            close_position(ts, price)
            continue

    # Long quick: if signal and not currently long, open long
    if long_quick_signal:
        if position is None or position['side'] != 'long':
            open_position('long', ts, price)
        # no SL for longs as requested
        continue


# End of data: close any open position
if position is not None:
    close_position(df.iloc[-1]['timestamp'], float(df.iloc[-1]['close']))

# Write trades and equity
os.makedirs('var', exist_ok=True)
trades_df = pd.DataFrame(trades)
if not trades_df.empty:
    trades_df.to_csv(OUT_TRADES, index=False)
else:
    # write header
    pd.DataFrame(columns=['side','entry_time','entry','size','exit_time','exit','gross_pnl','pnl','equity']).to_csv(OUT_TRADES, index=False)

eq_df = pd.DataFrame(eq_history)
eq_df.to_csv(OUT_EQ, index=False)

# Print summary
total_pnl = trades_df['pnl'].sum() if not trades_df.empty else 0.0
closed_trades = len(trades_df)
wins = (trades_df['pnl'] > 0).sum() if not trades_df.empty else 0
losses = (trades_df['pnl'] <= 0).sum() if not trades_df.empty else 0
final_equity = equity
print('bars=', len(df))
print('trades=', closed_trades)
print('final_equity=', round(final_equity,2))
print('total_pnl=', round(total_pnl,2))
print('wins=', wins, 'losses=', losses)
print('w%=', round(100.0 * wins / closed_trades, 2) if closed_trades>0 else 0.0)
print('wrote', OUT_TRADES, 'and', OUT_EQ)
