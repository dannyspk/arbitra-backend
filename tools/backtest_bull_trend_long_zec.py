#!/usr/bin/env python3
"""Run bull-trend long backtest on ZECUSDT 15m CSV (wrapper around backtest_bull_trend_long.py logic but using ZEC file)."""
from datetime import datetime
import pandas as pd
import os

CSV = 'var/zecusdt_15m.csv'
OUT_TRADES = 'var/bulltrend_trades_zec.csv'
OUT_EQ = 'var/bulltrend_equity_zec.csv'

if not os.path.exists(CSV):
    raise SystemExit('CSV not found: ' + CSV)

# We'll reuse the logic from backtest_bull_trend_long.py by loading it here inline for simplicity
# (copy-paste code path to keep the script self-contained)

df = pd.read_csv(CSV)
df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)
for c in ['open','high','low','close','volume']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
start_dt = pd.Timestamp('2025-09-30T00:00:00Z')
df = df[df['timestamp'] >= start_dt].reset_index(drop=True)

# params
equity = 10000.0
risk_pct = 0.10
short_sl_pct = 0.01
short_tp_pct = 0.02

trades = []
eq_history = []
position = None

# helpers

def close_position(ts, price):
    global equity, position, trades
    if position is None:
        return
    side = position['side']
    size = position['size']
    entry = position['entry_price']
    if side == 'long':
        gross = (price - entry) * size
    else:
        gross = (entry - price) * size
    pnl = gross
    equity += pnl
    trades.append({'side': side,'entry_time': position['entry_time'].isoformat(),'entry': entry,'size': size,'exit_time': ts.isoformat(),'exit': price,'gross_pnl': gross,'pnl': pnl,'equity': equity})
    position = None


def open_position(side, ts, price):
    global position, equity
    if position is not None:
        close_position(ts, price)
    amount = equity * risk_pct
    size = amount / price if price>0 else 0
    position = {'side': side, 'entry_price': price, 'size': size, 'entry_time': ts, 'amount': amount}

for idx, row in df.iterrows():
    ts = row['timestamp']
    price = float(row['close'])
    unreal = 0.0
    if position is not None:
        if position['side']=='long':
            unreal = (price - position['entry_price']) * position['size']
        else:
            unreal = (position['entry_price'] - price) * position['size']
    eq_history.append({'timestamp': ts.isoformat(), 'equity': equity + unreal})

    def pct_change_bars(n):
        if idx - n < 0:
            return None
        prev = df.at[idx-n, 'close']
        if prev==0 or pd.isna(prev):
            return None
        return (price - prev)/prev*100.0

    pct_15 = pct_change_bars(1)
    pct_30 = pct_change_bars(2)
    pct_60 = pct_change_bars(4)

    short_signal = False
    if pct_15 is not None and pct_30 is not None and pct_60 is not None:
        if (pct_15 >= 7.0) and (pct_30 >= 12.0) and (pct_60 >= 15.0):
            short_signal = True

    long_quick_signal = False
    if pct_15 is not None and pct_15 <= -5.0:
        long_quick_signal = True

    if short_signal:
        if position is None or position['side'] != 'short':
            open_position('short', ts, price)
            position['sl_price'] = position['entry_price'] * (1 + short_sl_pct)
            position['tp_price'] = position['entry_price'] * (1 - short_tp_pct)
        continue

    if position is not None and position['side']=='short':
        if price >= position.get('sl_price', 1e-12):
            close_position(ts, price)
            continue
        if price <= position.get('tp_price', -1e12):
            close_position(ts, price)
            continue

    if long_quick_signal:
        if position is None or position['side'] != 'long':
            open_position('long', ts, price)
        continue

if position is not None:
    close_position(df.iloc[-1]['timestamp'], float(df.iloc[-1]['close']))

os.makedirs('var', exist_ok=True)
trades_df = pd.DataFrame(trades)
if not trades_df.empty:
    trades_df.to_csv(OUT_TRADES, index=False)
else:
    pd.DataFrame(columns=['side','entry_time','entry','size','exit_time','exit','gross_pnl','pnl','equity']).to_csv(OUT_TRADES, index=False)

eq_df = pd.DataFrame(eq_history)
eq_df.to_csv(OUT_EQ, index=False)

print('wrote', OUT_TRADES, OUT_EQ)
