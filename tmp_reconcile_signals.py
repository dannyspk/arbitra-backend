import pandas as pd

# Files
signals_fn = 'var/bear_verbose_signals.csv'
trades_fn = 'var/bear_verbose_trades.csv'
actions_fn = 'var/bear_verbose_actions_detailed.csv'
eq_fn = 'var/bear_verbose_equity.csv'
out_fn = 'var/bear_verbose_signals_reconciled.csv'

# Read
sig = pd.read_csv(signals_fn, parse_dates=['timestamp'])
tr = pd.read_csv(trades_fn, parse_dates=['entry_time','exit_time'])
act = pd.read_csv(actions_fn, parse_dates=['timestamp_dt','trade_entry_time','trade_exit_time'])
eq = pd.read_csv(eq_fn, parse_dates=['timestamp'])

# Normalize timestamp formats for matching
sig['ts_str'] = sig['timestamp'].astype(str)
act['ts_str'] = act['timestamp_dt'].astype(str)
tr['exit_time_str'] = tr['exit_time'].astype(str)

def find_trade_by_exit(ts_str):
    matches = tr[tr['exit_time_str'] == ts_str]
    return matches.iloc[0] if len(matches) > 0 else None

# Map equity history by timestamp string
eq_map = {str(r['timestamp']): r['equity'] for _, r in eq.iterrows()}

rows = []
for _, r in sig.iterrows():
    row = r.to_dict()
    ts = r['ts_str']
    # fill equity from eq_history if available
    row['equity_reconciled'] = eq_map.get(ts, row.get('equity', None))
    # link to action
    act_match = act[act['ts_str'] == ts]
    if len(act_match) > 0:
        a = act_match.iloc[0]
        row['action_desc'] = a.get('action_desc', '')
        row['open_price'] = a.get('open_price', '')
        # trade metadata if present
        row['trade_pnl'] = a.get('trade_pnl', '')
        row['trade_entry_time'] = str(a.get('trade_entry_time',''))
        row['trade_exit_time'] = str(a.get('trade_exit_time',''))
        row['trade_duration_min'] = a.get('trade_duration_min','')
    else:
        row['action_desc'] = ''
        row['open_price'] = ''
        row['trade_pnl'] = ''
        row['trade_entry_time'] = ''
        row['trade_exit_time'] = ''
        row['trade_duration_min'] = ''
    # for close actions, try matching trade to get gross/fees
    if str(row.get('action','')).startswith('close') and row['trade_exit_time']:
        t = find_trade_by_exit(row['trade_exit_time'])
        if t is not None:
            row['trade_entry'] = t.get('entry','')
            row['trade_exit'] = t.get('exit','')
            # keep any gross/fee columns that exist
            row['gross_pnl'] = t.get('gross_pnl','') if 'gross_pnl' in t else ''
            row['entry_fee'] = t.get('entry_fee','') if 'entry_fee' in t else ''
            row['exit_fee'] = t.get('exit_fee','') if 'exit_fee' in t else ''
            row['net_pnl'] = t.get('pnl','')
    rows.append(row)

out = pd.DataFrame(rows)
# reorder to put reconciled columns near the end
cols = [c for c in out.columns if c not in ('equity_reconciled','open_price','trade_entry','trade_exit','gross_pnl','entry_fee','exit_fee','net_pnl','trade_pnl','trade_entry_time','trade_exit_time','trade_duration_min','action_desc')]
cols += ['action_desc','open_price','trade_entry','trade_exit','gross_pnl','entry_fee','exit_fee','net_pnl','trade_pnl','trade_entry_time','trade_exit_time','trade_duration_min','equity_reconciled']

out = out[cols]
out.to_csv(out_fn, index=False)
print('Wrote', out_fn)
