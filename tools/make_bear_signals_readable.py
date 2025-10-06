#!/usr/bin/env python3
"""Create a human-friendly version of bear_verbose_signals.csv.
Writes: var/bear_verbose_signals_readable.csv

Columns added/changed:
- human_utc: YYYY-MM-DD HH:MM:SS UTC
- pct15/pct30/pct60 formatted as percentages with sign
- action_description: human text for action codes
- pos_notional: pos_entry * pos_size (USD notional of current position)
- equity rounded
- Keep original numeric columns as raw_* if needed
"""
import pandas as pd
import os

IN = 'var/bear_verbose_signals.csv'
OUT = 'var/bear_verbose_signals_readable.csv'

if not os.path.exists(IN):
    raise SystemExit('Input not found: ' + IN)

df = pd.read_csv(IN)
# parse timestamp
if 'timestamp' in df.columns:
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['human_utc'] = df['timestamp'].dt.tz_convert('UTC').dt.strftime('%Y-%m-%d %H:%M:%S %Z')
else:
    df['human_utc'] = ''

# format pct columns
for c in ['pct15','pct30','pct60']:
    if c in df.columns:
        df[c+'_pct_str'] = df[c].apply(lambda v: (f"{v:+.2f}%") if pd.notna(v) else '')
    else:
        df[c+'_pct_str'] = ''

# action description mapping
action_map = {
    '': '',
    'open_long': 'Open LONG (signal: deep drop)',
    'open_short': 'Open SHORT (quick rise)',
    'close_long_sl': 'Close LONG (SL hit)',
    'close_long_tp': 'Close LONG (TP hit)',
}

def map_action(a):
    return action_map.get(a, a)

df['action_desc'] = df['action'].fillna('').apply(map_action)

# position notional
def compute_notional(row):
    try:
        if pd.isna(row.get('pos_entry')) or pd.isna(row.get('pos_size')):
            return ''
        return float(row['pos_entry']) * float(row['pos_size'])
    except Exception:
        return ''

if 'pos_entry' in df.columns and 'pos_size' in df.columns:
    df['pos_notional'] = df.apply(compute_notional, axis=1)
else:
    df['pos_notional'] = ''

# nicer equity format
if 'equity' in df.columns:
    df['equity_fmt'] = df['equity'].apply(lambda v: f"${v:,.2f}")
else:
    df['equity_fmt'] = ''

# select and order columns for readability
cols = ['human_utc','timestamp','close','pct15_pct_str','pct30_pct_str','pct60_pct_str',
        'long_signal','short_quick','action','action_desc','pos_side','pos_entry','pos_size','pos_notional','equity_fmt']
# include only existing columns
cols = [c for c in cols if c in df.columns]
readable = df[cols]
# write
os.makedirs('var', exist_ok=True)
readable.to_csv(OUT, index=False)
print('Wrote', OUT)
