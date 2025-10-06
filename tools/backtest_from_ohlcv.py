"""Backtest using minute OHLCV CSVs produced earlier.

Loads:
 - tools/ccxt_out/binance_ALPINEUSDT_1m.csv
 - tools/ccxt_out/gate_ALPINEUSDT_trades.csv

Computes per-minute features:
 - pct_diff (binance - gate) / gate * 100
 - volume_zscore (5-period rolling z-score of volume, using prior periods)
 - ewma_return (returns EWMA)

Alert rule: abs(pct_diff) >= 0.5 and (vol_zscore_binance >= 1 or vol_zscore_gate >= 1)

Saves features to tools/ccxt_out/features_ALPINEUSDT_20250930T1640.csv
"""
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import os

IN_BIN = 'tools/ccxt_out/binance_ALPINEUSDT_1m.csv'
IN_GATE = 'tools/ccxt_out/gate_ALPINEUSDT_trades.csv'
OUT = 'tools/ccxt_out/features_ALPINEUSDT_20250930T1640.csv'

if not os.path.exists(IN_BIN) or not os.path.exists(IN_GATE):
    print('Missing input CSVs. Expected:', IN_BIN, 'and', IN_GATE)
    raise SystemExit(1)

# read
bin_df = pd.read_csv(IN_BIN, parse_dates=['dt'])
gate_df = pd.read_csv(IN_GATE, parse_dates=['dt'])

# normalize index
bin_df.set_index('dt', inplace=True)
gate_df.set_index('dt', inplace=True)

# align on intersection of the user's window (16:40-16:50)
start = datetime(2025,9,30,16,40, tzinfo=timezone.utc)
end = datetime(2025,9,30,16,50, tzinfo=timezone.utc)

bin_slice = bin_df.loc[start:end].copy()
gate_slice = gate_df.loc[start:end].copy()

# ensure 'close' exists
if 'close' not in bin_slice.columns and 'price' in bin_slice.columns:
    bin_slice['close'] = bin_slice['price']
if 'close' not in gate_slice.columns and 'price' in gate_slice.columns:
    gate_slice['close'] = gate_slice['price']

# combine
idx = sorted(set(bin_slice.index).union(set(gate_slice.index)))
feat = pd.DataFrame(index=idx)
feat['bin_close'] = bin_slice['close'].reindex(idx).ffill()
feat['gate_close'] = gate_slice['close'].reindex(idx).ffill()
feat['bin_vol'] = bin_slice['volume'].reindex(idx).fillna(0)
feat['gate_vol'] = gate_slice['volume'].reindex(idx).fillna(0)

# percent diff (use gate as denom when present)
feat['pct_diff'] = (feat['bin_close'] - feat['gate_close']) / feat['gate_close'] * 100.0

# returns and EWMA returns
feat['bin_ret'] = feat['bin_close'].pct_change()
feat['gate_ret'] = feat['gate_close'].pct_change()
# EWMA with span=5 minutes
feat['bin_ewma_ret'] = feat['bin_ret'].ewm(span=5, adjust=False).mean()
feat['gate_ewma_ret'] = feat['gate_ret'].ewm(span=5, adjust=False).mean()

# volume z-score using prior 5-minute window (drop current)
window = 5
feat['bin_vol_mean'] = feat['bin_vol'].shift(1).rolling(window).mean()
feat['bin_vol_std'] = feat['bin_vol'].shift(1).rolling(window).std(ddof=0)
feat['gate_vol_mean'] = feat['gate_vol'].shift(1).rolling(window).mean()
feat['gate_vol_std'] = feat['gate_vol'].shift(1).rolling(window).std(ddof=0)

def zscore(val, mean, std):
    if pd.isna(val) or pd.isna(mean) or pd.isna(std) or std == 0:
        return 0.0
    return (val - mean) / std

feat['bin_vol_z'] = feat.apply(lambda r: zscore(r['bin_vol'], r['bin_vol_mean'], r['bin_vol_std']), axis=1)
feat['gate_vol_z'] = feat.apply(lambda r: zscore(r['gate_vol'], r['gate_vol_mean'], r['gate_vol_std']), axis=1)

# Alert rule: abs pct diff >= 0.5 and (vol z >= 1 on either)
thr = 0.5
feat['alert_pct'] = feat['pct_diff'].abs() >= thr
feat['alert_vol'] = (feat['bin_vol_z'] >= 1.0) | (feat['gate_vol_z'] >= 1.0)
feat['alert'] = feat['alert_pct'] & feat['alert_vol']

# Save features
os.makedirs(os.path.dirname(OUT), exist_ok=True)
feat.to_csv(OUT, float_format='%.6f')

# Print alerts
alerts = feat[feat['alert']]
print('Total minutes in window:', len(feat))
print('Alerts found:', len(alerts))
if not alerts.empty:
    print('\nAlerts:')
    print(alerts[['bin_close','gate_close','pct_diff','bin_vol','gate_vol','bin_vol_z','gate_vol_z']].to_string())
else:
    print('No alerts by the rule (pct>=0.5% and vol_z>=1)')

print('\nFeatures saved to', OUT)
