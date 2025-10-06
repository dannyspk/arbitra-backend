import pandas as pd

fn = 'var/bear_verbose_trades.csv'

df = pd.read_csv(fn)
# parse and normalize timestamps to UTC if possible
for col in ('entry_time','exit_time'):
    if col in df.columns:
        try:
            dt = pd.to_datetime(df[col], utc=True, errors='coerce')
            # Format as human-readable UTC string
            df[col] = dt.dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception as e:
            # fallback: leave as-is
            print(f'Warning: failed to parse {col}:', e)

# write back
df.to_csv(fn, index=False)
print('Rewrote', fn)
print(df.head().to_string(index=False))
