#!/usr/bin/env python3
"""Grid runner for the bear-trend-short strategy with fee/slippage modeling.
Saves results to var/myx_bear_grid_results.json and var/myx_bear_grid_results_summary.csv

Grid dimensions:
- long_threshold_set: three variants (original + 2 relaxed)
- sl_pct: [0.01, 0.02, 0.03]
- tp_pct: [0.02, 0.05]
- risk_pct: [0.05, 0.10, 0.20]
- fee_pct: single value 0.0007 (0.07%) by default
- slippage_pct: single value 0.0005 (0.05%) by default

This script is intentionally self-contained and prints progress.
"""
import os, json, math
import pandas as pd
from datetime import datetime

CSV = 'var/myx_15m.csv'
OUT_JSON = 'var/myx_bear_grid_results.json'
OUT_SUM = 'var/myx_bear_grid_results_summary.csv'

if not os.path.exists(CSV):
    raise SystemExit('CSV not found: ' + CSV)

# Load and filter data
df = pd.read_csv(CSV)
df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)
for c in ['open','high','low','close','volume']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
start_dt = pd.Timestamp('2025-09-30T00:00:00Z')
df = df[df['timestamp'] >= start_dt].reset_index(drop=True)
if df.empty:
    raise SystemExit('No data after 2025-09-30 in ' + CSV)

# Grid params
threshold_sets = [
    {'name': 'orig', 'p15': 7.0, 'p30': 12.0, 'p60': 15.0},
    {'name': 'relaxed', 'p15': 5.0, 'p30': 10.0, 'p60': 12.0},
    {'name': 'more_relaxed', 'p15': 3.0, 'p30': 7.0, 'p60': 10.0},
]
sl_vals = [0.01, 0.02, 0.03]
tp_vals = [0.02, 0.05]
risk_vals = [0.05, 0.10, 0.20]
fee_pct = 0.0007  # per trade notional fee
slippage_pct = 0.0005

results = []

# Backtest function (same core as earlier, with fee/slippage)
def run_bt(p15_thresh, p30_thresh, p60_thresh, sl_pct, tp_pct, risk_pct, fee_pct, slip_pct):
    equity = 10000.0
    trades = []
    eq_history = []
    position = None

    def apply_entry_price(price, side):
        # slippage: assume adverse entry: buy at price*(1+slip), sell(short) at price*(1-slip)
        if side == 'long':
            return price * (1.0 + slip_pct)
        else:
            return price * (1.0 - slip_pct)

    def apply_exit_price(price, side):
        # exiting reverses slippage
        if side == 'long':
            return price * (1.0 - slip_pct)
        else:
            return price * (1.0 + slip_pct)

    def charge_fee(notional):
        return notional * fee_pct

    def close_position(ts, price):
        nonlocal equity, position, trades
        if position is None:
            return
        side = position['side']
        entry_price = position['entry_price']
        size = position['size']
        entry_notional = entry_price * size
        # apply exit slippage
        exit_price = apply_exit_price(price, side)
        if side == 'long':
            pnl = (exit_price - entry_price) * size
        else:
            pnl = (entry_price - exit_price) * size
        # fees on entry and exit
        fee = charge_fee(entry_notional) + charge_fee(abs(exit_price * size))
        equity += pnl - fee
        trades.append({
            'side': side,
            'entry_time': position['entry_time'].isoformat(),
            'entry': entry_price,
            'size': size,
            'exit_time': ts.isoformat(),
            'exit': exit_price,
            'pnl': pnl - fee,
            'equity': equity,
        })
        position = None

    def open_position(side, ts, raw_price):
        nonlocal position, equity
        # entry price with slippage
        entry_price = apply_entry_price(raw_price, side)
        amount = equity * risk_pct
        size = amount / entry_price if entry_price > 0 else 0
        # charge entry fee
        fee = charge_fee(entry_price * size)
        equity -= fee
        # close existing
        if position is not None:
            close_position(ts, raw_price)
        position = {'side': side, 'entry_price': entry_price, 'size': size, 'entry_time': ts, 'amount': amount}

    # iterate
    for idx, row in df.iterrows():
        ts = row['timestamp']
        price = float(row['close'])
        # unrealized
        unreal = 0.0
        if position is not None:
            if position['side'] == 'long':
                unreal = (price - position['entry_price']) * position['size']
            else:
                unreal = (position['entry_price'] - price) * position['size']
        eq_history.append({'timestamp': ts.isoformat(), 'equity': equity + unreal})

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

        long_signal = False
        if pct_15 is not None and pct_30 is not None and pct_60 is not None:
            if (pct_15 <= -p15_thresh) and (pct_30 <= -p30_thresh) and (pct_60 <= -p60_thresh):
                long_signal = True

        short_quick_signal = False
        if pct_15 is not None and pct_15 >= 5.0:
            short_quick_signal = True

        # If long signal: close short and open long
        if long_signal:
            open_position('long', ts, price)
            position['sl_price'] = position['entry_price'] * (1 - sl_pct)
            position['tp_price'] = position['entry_price'] * (1 + tp_pct)
            continue

        # check long SL/TP
        if position is not None and position['side'] == 'long':
            # compare raw price to sl/tp
            if price <= position.get('sl_price', -1):
                close_position(ts, price)
                continue
            if price >= position.get('tp_price', 1e12):
                close_position(ts, price)
                continue

        # short quick
        if short_quick_signal:
            if position is None or position['side'] != 'short':
                open_position('short', ts, price)
            continue


    # close any open
    if position is not None:
        close_position(df.iloc[-1]['timestamp'], float(df.iloc[-1]['close']))

    # summarize
    trades_df = pd.DataFrame(trades)
    total_pnl = trades_df['pnl'].sum() if not trades_df.empty else 0.0
    closed_trades = len(trades_df)
    wins = (trades_df['pnl'] > 0).sum() if not trades_df.empty else 0
    losses = (trades_df['pnl'] <= 0).sum() if not trades_df.empty else 0
    final_equity = equity
    max_dd = 0.0
    # simple drawdown from eq_history
    eqs = [e['equity'] for e in eq_history]
    peak = -1e9
    for v in eqs:
        if v > peak:
            peak = v
        dd = (peak - v)
        if dd > max_dd:
            max_dd = dd
    return {
        'trades': closed_trades,
        'total_pnl': total_pnl,
        'wins': int(wins),
        'losses': int(losses),
        'final_equity': final_equity,
        'max_drawdown': max_dd,
    }

# run grid
count = 0
total = len(threshold_sets) * len(sl_vals) * len(tp_vals) * len(risk_vals)
for tset in threshold_sets:
    for sl in sl_vals:
        for tp in tp_vals:
            for r in risk_vals:
                count += 1
                print(f'Running {count}/{total} t={tset["name"]} sl={sl} tp={tp} risk={r}')
                out = run_bt(tset['p15'], tset['p30'], tset['p60'], sl, tp, r, fee_pct, slippage_pct)
                results.append({
                    'threshold_set': tset['name'],
                    'p15': tset['p15'], 'p30': tset['p30'], 'p60': tset['p60'],
                    'sl_pct': sl, 'tp_pct': tp, 'risk_pct': r,
                    'fee_pct': fee_pct, 'slip_pct': slippage_pct,
                    **out,
                })

# write outputs
os.makedirs('var', exist_ok=True)
with open(OUT_JSON, 'w', encoding='utf8') as f:
    json.dump({'symbol': 'MYX/USDT', 'results': results}, f, indent=2)

# summary CSV
sum_df = pd.DataFrame(results)
sum_df = sum_df.sort_values(by=['final_equity','total_pnl'], ascending=False)
sum_df.to_csv(OUT_SUM, index=False)

print('Wrote', OUT_JSON, 'and', OUT_SUM)
