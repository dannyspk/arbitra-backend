#!/usr/bin/env python3
"""Run the bear-trend strategy for the chosen top combo and dump per-bar signals.
Top combo used: threshold_set 'relaxed' (p15=5, p30=10, p60=12), sl=0.01, tp=0.02, risk=0.2
Writes:
- var/bear_verbose_signals.csv (per-bar signals and position state)
- var/bear_verbose_trades.csv (closed trades)
- var/bear_verbose_equity.csv (equity timeline)
"""
import os
import pandas as pd
import argparse
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--csv', help='Input CSV file (15m OHLCV).', default='var/myx_15m.csv')
parser.add_argument('--out-prefix', help='Output file prefix under var/', default='bear_verbose')
parser.add_argument('--mode', help='Strategy mode: bear (default) or bull (flipped rules)', choices=['bear','bull'], default='bear')
args = parser.parse_args()

CSV = args.csv
OUT_SIGNALS = f'var/{args.out_prefix}_signals.csv'
OUT_TRADES = f'var/{args.out_prefix}_trades.csv'
OUT_EQ = f'var/{args.out_prefix}_equity.csv'
MODE = args.mode

if not os.path.exists(CSV):
    raise SystemExit('CSV not found: ' + CSV)

# params from top combo
p15_thresh = 5.0
p30_thresh = 10.0
p60_thresh = 12.0
sl_pct = 0.01
tp_pct = 0.02
risk_pct = 0.2
fee_pct = 0.0007
slip_pct = 0.0005

# load data
p = pd.read_csv(CSV)
p['timestamp'] = pd.to_datetime(p['timestamp'].astype(int), unit='ms', utc=True)
for c in ['open','high','low','close','volume']:
    p[c] = pd.to_numeric(p[c], errors='coerce')
start_dt = pd.Timestamp('2025-09-30T00:00:00Z')
df = p[p['timestamp'] >= start_dt].reset_index(drop=True)

# state
equity = 10000.0
position = None
trades = []
eq_history = []
rows = []

# helpers
def apply_entry_price(price, side):
    return price * (1.0 + slip_pct) if side == 'long' else price * (1.0 - slip_pct)

def apply_exit_price(price, side):
    return price * (1.0 - slip_pct) if side == 'long' else price * (1.0 + slip_pct)

def fee(notional):
    return notional * fee_pct

def open_pos(side, ts, raw_price, reason=''):
    global position, equity
    entry_price = apply_entry_price(raw_price, side)
    amount = equity * risk_pct
    size = amount / entry_price if entry_price>0 else 0
    # close existing (mark close as replaced)
    if position is not None:
        close_pos(ts, raw_price, action_desc=f'Close (replaced by {side})', close_reason='replaced')
    # record entry fee for later (do not subtract here to avoid double-counting)
    entry_fee = fee(entry_price * size)
    position = {'side': side, 'entry_price': entry_price, 'size': size, 'entry_time': ts, 'amount': amount, 'entry_fee': entry_fee, 'entry_reason': reason}
    return position

def close_pos(ts, raw_price, action_desc='', close_reason=''):
    global position, equity, trades
    if position is None:
        return
    side = position['side']
    entry_price = position['entry_price']
    size = position['size']
    exit_price = apply_exit_price(raw_price, side)
    # compute gross pnl (price move * size)
    gross = (exit_price - entry_price) * size if side=='long' else (entry_price - exit_price) * size
    entry_fee = float(position.get('entry_fee', 0.0))
    exit_fee = fee(abs(exit_price * size))
    net = gross - (entry_fee + exit_fee)
    # apply net pnl to equity (entry_fee wasn't subtracted at open to keep accounting at close)
    equity += net
    pos_notional = float(position.get('amount', entry_price * size))
    # format times as human-readable UTC strings
    entry_time_str = position['entry_time'].strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(position['entry_time'], 'strftime') else str(position['entry_time'])
    exit_time_str = ts.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(ts, 'strftime') else str(ts)
    trades.append({'side': side, 'entry_time': entry_time_str, 'entry': entry_price,
                   'size': size, 'pos_notional': pos_notional,
                   'exit_time': exit_time_str, 'exit': exit_price,
                   'gross_pnl': gross, 'entry_fee': entry_fee, 'exit_fee': exit_fee, 'pnl': net, 'equity': equity,
                   'entry_reason': position.get('entry_reason', ''), 'close_reason': close_reason, 'action_desc': action_desc})
    position = None

# run
for idx, r in df.iterrows():
    ts = r['timestamp']
    price = float(r['close'])
    # compute pct changes
    def pct(n):
        if idx-n < 0:
            return None
        prev = df.at[idx-n,'close']
        if prev==0 or pd.isna(prev):
            return None
        return (price - prev)/prev*100.0
    pct15 = pct(1)
    pct30 = pct(2)
    pct60 = pct(4)

    # signals depend on mode
    # initialize all signal vars so rows always contain same columns
    long_signal = False
    short_quick = False
    short_signal = False
    long_quick = False
    if MODE == 'bear':
        long_signal = False
        if pct15 is not None and pct30 is not None and pct60 is not None:
            if (pct15 <= -p15_thresh) and (pct30 <= -p30_thresh) and (pct60 <= -p60_thresh):
                long_signal = True
        short_quick = True if (pct15 is not None and pct15 >= 5.0) else False
    else:  # MODE == 'bull' (flipped rules)
        short_signal = False
        if pct15 is not None and pct30 is not None and pct60 is not None:
            if (pct15 >= p15_thresh) and (pct30 >= p30_thresh) and (pct60 >= p60_thresh):
                short_signal = True
        long_quick = True if (pct15 is not None and pct15 <= -5.0) else False

    # check SL/TP for both sides
    long_sl_hit = False
    long_tp_hit = False
    short_sl_hit = False
    short_tp_hit = False
    if position is not None:
        if position['side'] == 'long':
            if price <= position.get('sl_price', -1):
                long_sl_hit = True
            if price >= position.get('tp_price', 1e12):
                long_tp_hit = True
        else:
            if price >= position.get('sl_price', 1e12):
                short_sl_hit = True
            if price <= position.get('tp_price', -1e12):
                short_tp_hit = True

    action = ''
    # process signals for bear mode
    if MODE == 'bear':
        if long_signal:
            if position is None or position['side'] != 'long':
                action = 'open_long'
                open_pos('long', ts, price, reason='long_signal')
                position['sl_price'] = position['entry_price'] * (1 - sl_pct)
                position['tp_price'] = position['entry_price'] * (1 + tp_pct)
        elif long_sl_hit:
            action = 'close_long_sl'
            close_pos(ts, price, action_desc='Close LONG (SL hit)', close_reason='SL')
        elif long_tp_hit:
            action = 'close_long_tp'
            close_pos(ts, price, action_desc='Close LONG (TP hit)', close_reason='TP')
        elif short_quick:
            if position is None or position['side'] != 'short':
                action = 'open_short'
                if position is not None and position['side'] == 'long':
                    close_pos(ts, price, action_desc='Close LONG (switch to short)', close_reason='replaced')
                open_pos('short', ts, price, reason='short_quick')
    else:
        # MODE == 'bull'
        if short_signal:
            if position is None or position['side'] != 'short':
                action = 'open_short'
                if position is not None and position['side'] == 'long':
                    close_pos(ts, price, action_desc='Close LONG (switch to short)', close_reason='replaced')
                open_pos('short', ts, price, reason='short_signal')
                position['sl_price'] = position['entry_price'] * (1 + sl_pct)
                position['tp_price'] = position['entry_price'] * (1 - tp_pct)
        elif short_sl_hit:
            action = 'close_short_sl'
            close_pos(ts, price, action_desc='Close SHORT (SL hit)', close_reason='SL')
        elif short_tp_hit:
            action = 'close_short_tp'
            close_pos(ts, price, action_desc='Close SHORT (TP hit)', close_reason='TP')
        elif long_quick:
            if position is None or position['side'] != 'long':
                action = 'open_long'
                if position is not None and position['side'] == 'short':
                    close_pos(ts, price, action_desc='Close SHORT (switch to long)', close_reason='replaced')
                open_pos('long', ts, price, reason='long_quick')
    # record row
    pos_side = position['side'] if position is not None else None
    pos_entry = position['entry_price'] if position is not None else None
    pos_size = position['size'] if position is not None else None
    ts_str = ts.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(ts, 'strftime') else str(ts)
    rows.append({'timestamp': ts_str, 'close': price, 'pct15': pct15, 'pct30': pct30, 'pct60': pct60,
                 'long_signal': long_signal, 'short_quick': short_quick, 'action': action,
                 'pos_side': pos_side, 'pos_entry': pos_entry, 'pos_size': pos_size, 'equity': equity})
    # record equity
    unreal = 0.0
    if position is not None:
        if position['side']=='long':
            unreal = (price - position['entry_price']) * position['size']
        else:
            unreal = (position['entry_price'] - price) * position['size']
    eq_history.append({'timestamp': ts_str, 'equity': equity + unreal})

# close open at end
if position is not None:
    # final close: ensure formatted timestamp passed
    last_ts = df.iloc[-1]['timestamp']
    close_pos(last_ts, float(df.iloc[-1]['close']), close_reason='end')

# save
os.makedirs('var', exist_ok=True)
pd.DataFrame(rows).to_csv(OUT_SIGNALS, index=False)
if trades:
    pd.DataFrame(trades).to_csv(OUT_TRADES, index=False)
else:
    pd.DataFrame(columns=['side','entry_time','entry','size','exit_time','exit','pnl','equity']).to_csv(OUT_TRADES, index=False)
pd.DataFrame(eq_history).to_csv(OUT_EQ, index=False)

print('Wrote', OUT_SIGNALS, OUT_TRADES, OUT_EQ)
