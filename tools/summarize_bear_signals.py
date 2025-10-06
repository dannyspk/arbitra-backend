#!/usr/bin/env python3
"""Summarize the human-readable signals file into an actions-only CSV and print a short table.
Writes: var/bear_verbose_actions.csv
Also prints counts and first 20 actions.
"""
import pandas as pd
import os

IN = 'var/bear_verbose_signals_readable.csv'
OUT = 'var/bear_verbose_actions.csv'

if not os.path.exists(IN):
    raise SystemExit('Input missing: ' + IN)

df = pd.read_csv(IN)
# ensure pct strings exist
for c in ['pct15_pct_str','pct30_pct_str','pct60_pct_str']:
    if c not in df.columns:
        df[c] = ''

# action rows
act = df[df['action'].fillna('') != ''].copy()
if act.empty:
    print('No actions found in', IN)
else:
    # compute a human reason
    def reason(row):
        a = row['action'] if pd.notna(row['action']) else ''
        if a == 'open_long':
            return f"Deep drop: {row.get('pct15_pct_str','')} / {row.get('pct30_pct_str','')} / {row.get('pct60_pct_str','')}"
        if a == 'open_short':
            return f"Quick rise: {row.get('pct15_pct_str','')}"
        if a == 'close_long_sl':
            return 'Long SL hit'
        if a == 'close_long_tp':
            return 'Long TP hit'
        return a

    act['reason'] = act.apply(reason, axis=1)

    # select friendly columns
    cols = ['human_utc','timestamp','close','pct15_pct_str','pct30_pct_str','pct60_pct_str',
            'action','action_desc','reason','pos_side','pos_entry','pos_size','pos_notional','equity_fmt']
    cols = [c for c in cols if c in act.columns]
    outdf = act[cols]
    os.makedirs('var', exist_ok=True)
    outdf.to_csv(OUT, index=False)
    print('Wrote', OUT)

    # print quick table
    display = outdf.copy()
    if 'pos_notional' in display.columns:
        display['pos_notional'] = display['pos_notional'].apply(lambda v: f"{v:.2f}" if pd.notna(v) and v!='' else '')
    print('\nActions count:', len(display))
    print(display.head(20).to_string(index=False))
