import pandas as pd

in_fn = 'var/bear_verbose_signals_reconciled.csv'
out_fn = 'var/bear_verbose_signals_reconciled_filtered.csv'

df = pd.read_csv(in_fn, dtype=str)
# Robust boolean parse for 'long_signal' and 'short_quick'
def truthy(x):
    if pd.isna(x):
        return False
    s = str(x).strip().lower()
    if s in ('true','1','t','yes','y'):
        return True
    try:
        # numeric non-zero considered True
        return float(s) != 0.0
    except Exception:
        return False

keep_mask = df.get('long_signal').apply(truthy) | df.get('short_quick').apply(truthy)
filtered = df[keep_mask].copy()
filtered.to_csv(out_fn, index=False)
print('Wrote', out_fn, 'rows_kept=', len(filtered), 'rows_total=', len(df))
