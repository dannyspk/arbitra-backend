#!/usr/bin/env python3
"""Augment actions CSV with opening price, trade pnl and duration when available.
Writes: var/bear_verbose_actions_with_tradeinfo.csv
"""
import pandas as pd
import os
from datetime import datetime

IN_ACT = 'var/bear_verbose_actions.csv'
IN_TR = 'var/bear_verbose_trades.csv'
OUT = 'var/bear_verbose_actions_with_tradeinfo.csv'

if not os.path.exists(IN_ACT):
    raise SystemExit('Actions file missing: ' + IN_ACT)
if not os.path.exists(IN_TR):
    raise SystemExit('Trades file missing: ' + IN_TR)

act = pd.read_csv(IN_ACT)
tr = pd.read_csv(IN_TR)

# parse timestamps
act['timestamp_dt'] = pd.to_datetime(act['timestamp'])
tr['entry_time_dt'] = pd.to_datetime(tr['entry_time'])
tr['exit_time_dt'] = pd.to_datetime(tr['exit_time'])

# prepare columns
act['open_price'] = ''
act['trade_pnl'] = ''
act['trade_entry_time'] = ''
act['trade_exit_time'] = ''
act['trade_duration_min'] = ''

# helper: find trade by matching exit_time
for i, row in act.iterrows():
    a_ts = row['timestamp_dt']
    action = str(row.get('action',''))
    if action.startswith('open_'):
        # opening price available in pos_entry column
        if 'pos_entry' in act.columns and pd.notna(row.get('pos_entry')):
            act.at[i,'open_price'] = row['pos_entry']
    elif action.startswith('close'):
        # find trade with matching exit_time
        candidates = tr[tr['exit_time_dt'] == a_ts]
        if candidates.empty:
            # allow small tolerance (match within 2 minutes)
            tol = pd.Timedelta(minutes=2)
            diff = (tr['exit_time_dt'] - a_ts).abs()
            idx = diff[diff <= tol].index
            if len(idx)>0:
                candidates = tr.loc[idx]
        if not candidates.empty:
            # if multiple, pick the first
            t = candidates.iloc[0]
            act.at[i,'open_price'] = t['entry']
            act.at[i,'trade_pnl'] = t['pnl']
            act.at[i,'trade_entry_time'] = t['entry_time']
            act.at[i,'trade_exit_time'] = t['exit_time']
            try:
                dt = pd.to_datetime(t['exit_time']) - pd.to_datetime(t['entry_time'])
                act.at[i,'trade_duration_min'] = int(dt.total_seconds()//60)
            except Exception:
                act.at[i,'trade_duration_min'] = ''
        else:
            act.at[i,'open_price'] = ''

# write
os.makedirs('var', exist_ok=True)
act.to_csv(OUT, index=False)
print('Wrote', OUT)
print('\nSample rows:')
print(act.head(20).to_string(index=False))
