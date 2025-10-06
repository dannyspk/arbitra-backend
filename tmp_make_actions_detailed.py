import pandas as pd

actions_fn = 'var/bear_verbose_actions_with_tradeinfo.csv'
trades_fn = 'var/bear_verbose_trades.csv'
out_fn = 'var/bear_verbose_actions_detailed.csv'

acts = pd.read_csv(actions_fn, parse_dates=['timestamp_dt','trade_entry_time','trade_exit_time'], keep_default_na=False)
trd = pd.read_csv(trades_fn, parse_dates=['entry_time','exit_time'], keep_default_na=False)

# Ensure numeric types
for c in ['entry','exit','size','pnl']:
    if c in trd.columns:
        trd[c] = pd.to_numeric(trd[c], errors='coerce')

# Prepare cumulative equity starting at 10000
start_equity = 10000.0
cum = start_equity
rows = []

# Normalize matching by ISO format strings
trd['exit_time_str'] = trd['exit_time'].astype(str)

for _, row in acts.iterrows():
    newrow = row.to_dict()
    newrow['exit_price'] = ''
    newrow['gross_pnl'] = ''
    newrow['entry_fee'] = ''
    newrow['exit_fee'] = ''
    newrow['net_pnl'] = ''
    newrow['cum_equity'] = round(cum,8)

    tet = row.get('trade_exit_time')
    if pd.notna(tet) and str(tet) != '':
        # find matching trade
        mask = trd['exit_time_str'] == str(tet)
        if mask.any():
            t = trd[mask].iloc[0]
            try:
                entry_price = float(t['entry'])
                exit_price = float(t['exit'])
                size = float(t['size'])
                net_pnl = float(t['pnl'])
            except Exception:
                # skip if parsing fails
                rows.append(newrow)
                continue
            side = str(t['side']).strip().lower() if 'side' in t else str(row.get('pos_side')).strip().lower()
            if side == 'long':
                gross = (exit_price - entry_price) * size
            else:
                gross = (entry_price - exit_price) * size
            fees_total = gross - net_pnl
            # If fees_total is nonsensical (e.g., negative due to rounding), still split proportionally
            entry_fee = fees_total / 2.0
            exit_fee = fees_total - entry_fee
            cum += net_pnl
            newrow['exit_price'] = exit_price
            newrow['gross_pnl'] = round(gross,8)
            newrow['entry_fee'] = round(entry_fee,8)
            newrow['exit_fee'] = round(exit_fee,8)
            newrow['net_pnl'] = round(net_pnl,8)
            newrow['cum_equity'] = round(cum,8)
    rows.append(newrow)

out = pd.DataFrame(rows)
# Reorder columns to put key new cols at the end
cols = [c for c in out.columns if c not in ('open_price','exit_price','gross_pnl','entry_fee','exit_fee','net_pnl','cum_equity')]
cols += ['open_price','exit_price','gross_pnl','entry_fee','exit_fee','net_pnl','cum_equity']

out = out[cols]
out.to_csv(out_fn, index=False)
print('Wrote', out_fn)
