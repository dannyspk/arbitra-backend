import pandas as pd
from datetime import datetime

trades_fp = 'var/beartrend_trades.csv'
df_fp = 'var/myx_15m.csv'

trades = pd.read_csv(trades_fp)
df = pd.read_csv(df_fp)

df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)

df = df[df['timestamp'] >= pd.Timestamp('2025-09-30T00:00:00Z')].reset_index(drop=True)

if trades.empty:
    print('No closed trades to inspect')
    raise SystemExit()

for i, t in trades.iterrows():
    entry_time = pd.to_datetime(t['entry_time'])
    entry_price = float(t['entry'])
    side = t['side']
    # find nearest bar index
    idx = df.index[df['timestamp'] == entry_time]
    if len(idx)==0:
        # try matching by timestamp string
        idx = df.index[df['timestamp'].astype(str).str.startswith(entry_time.isoformat())]
    if len(idx)==0:
        # fallback: find closest
        idx = (df['timestamp'] - entry_time).abs().idxmin()
    else:
        idx = idx[0]
    print('\nTrade', i+1, 'side=', side)
    print(' entry_time:', df.at[idx,'timestamp'])
    print(' entry_price:', entry_price)
    print(' close at exit_time:', t['exit_time'], 'exit_price:', t['exit'])
    # compute pct changes
    def pct(n):
        if idx-n < 0:
            return None
        prev = df.at[idx-n,'close']
        if prev==0:
            return None
        cur = df.at[idx,'close']
        return (cur - prev)/prev*100.0
    p15 = pct(1)
    p30 = pct(2)
    p60 = pct(4)
    print(' pct_15:', p15, ' pct_30:', p30, ' pct_60:', p60)
    # show a small window
    start = max(0, idx-5)
    end = min(len(df)-1, idx+2)
    print('\nNearby bars (index, timestamp, close):')
    for j in range(start, end+1):
        mark = 'ENTRY' if j==idx else ''
        print(j, df.at[j,'timestamp'], df.at[j,'close'], mark)
    
print('\nDone')
