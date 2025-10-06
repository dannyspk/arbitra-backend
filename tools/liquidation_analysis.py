"""Liquidation analysis for ALPINE/USDT around 2025-09-30 16:40-16:50 UTC.

Actions:
 - Query Binance Futures forced-liquidation endpoint for ALPINEUSDT in the window.
 - Load local Binance trade CSV (if present) and flag large trades using a simple heuristic.
 - Save results to tools/ccxt_out/liquidations_binance.json and large_trades.csv
"""
from datetime import datetime, timezone
import requests, json, os
import pandas as pd
import numpy as np

# Parameters
SYMBOL = 'ALPINEUSDT'  # Binance futures symbol
START = datetime(2025,9,30,16,40, tzinfo=timezone.utc)
END = datetime(2025,9,30,16,50, tzinfo=timezone.utc)
START_MS = int(START.timestamp() * 1000)
END_MS = int(END.timestamp() * 1000)
OUT_DIR = 'tools/ccxt_out'
TRADE_CSV = os.path.join(OUT_DIR, 'binance_ALPINEUSDT_trades.csv')
FORCE_OUT = os.path.join(OUT_DIR, 'liquidations_binance.json')
LARGE_TRADES_OUT = os.path.join(OUT_DIR, 'binance_large_trades.csv')

os.makedirs(OUT_DIR, exist_ok=True)

# 1) Query Binance Futures forced liquidations
print('Querying Binance Futures force-orders endpoint for', SYMBOL)
force_url = 'https://fapi.binance.com/fapi/v1/allForceOrders'
try:
    r = requests.get(force_url, params={'symbol': SYMBOL, 'startTime': START_MS, 'endTime': END_MS}, timeout=10)
    if r.status_code == 200:
        js = r.json()
        with open(FORCE_OUT, 'w', encoding='utf-8') as fh:
            json.dump(js, fh, indent=2)
        print('Saved forced orders to', FORCE_OUT, 'count=', len(js) if isinstance(js, list) else 0)
    else:
        print('Force-orders request failed', r.status_code, r.text[:400])
        js = None
except Exception as e:
    print('Request error', e)
    js = None

# 2) Heuristic scan of trade CSV
if not os.path.exists(TRADE_CSV):
    print('Trade CSV not found at', TRADE_CSV, '- skipping local trades scan')
else:
    print('Loading trade CSV', TRADE_CSV)
    try:
        df = pd.read_csv(TRADE_CSV)
    except Exception as e:
        print('Failed to read trade CSV:', e)
        df = None

    if df is not None and not df.empty:
        # normalize timestamp column
        ts_col = None
        for c in ['timestamp','ts','time','date','datetime']:
            if c in df.columns:
                ts_col = c
                break
        if ts_col is None:
            # try infer
            if 'dt' in df.columns:
                df['dt'] = pd.to_datetime(df['dt'])
                df.set_index('dt', inplace=True)
            else:
                print('No timestamp column found; try opening CSV manually')
        else:
            # convert
            try:
                df['dt'] = pd.to_datetime(df[ts_col], unit='ms', utc=True)
            except Exception:
                try:
                    df['dt'] = pd.to_datetime(df[ts_col], utc=True)
                except Exception:
                    df['dt'] = pd.to_datetime(df[ts_col], errors='coerce')
            df.set_index('dt', inplace=True)

        # focus on target window
        try:
            window_df = df.loc[START:END].copy()
        except Exception:
            window_df = df[(df.index >= START) & (df.index <= END)].copy()

        if window_df.empty:
            print('No trades in the target window in local CSV')
        else:
            # identify price and amount columns
            price_col = None
            amt_col = None
            for c in ['price','Price','p','close','trade_price']:
                if c in window_df.columns:
                    price_col = c
                    break
            for c in ['size','qty','quantity','amount','Amount','vol','volume']:
                if c in window_df.columns:
                    amt_col = c
                    break
            if price_col is None or amt_col is None:
                print('Could not find price/amount columns; columns found:', list(window_df.columns))
            else:
                # compute median size and mark large trades
                sizes = window_df[amt_col].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
                if sizes.empty:
                    print('No numeric trade sizes to analyze')
                else:
                    med = sizes.median()
                    p99 = sizes.quantile(0.99)
                    thresh = max(med * 5.0, p99)
                    print('Median size:', med, '99pct:', p99, 'threshold chosen:', thresh)
                    window_df['size'] = window_df[amt_col].astype(float)
                    window_df['price_val'] = window_df[price_col].astype(float)
                    large = window_df[window_df['size'] >= thresh].copy()
                    # also mark large price impacts: price change vs previous minute > 0.5%
                    window_df['prev_price'] = window_df['price_val'].shift(1)
                    window_df['price_move_pct'] = (window_df['price_val'] - window_df['prev_price']) / window_df['prev_price'].abs() * 100.0
                    impact = window_df[window_df['price_move_pct'].abs() >= 0.5]
                    # combine
                    flagged = pd.concat([large, impact]).drop_duplicates()
                    if flagged.empty:
                        print('No large/impact trades found by heuristic in window')
                    else:
                        print('Flagged trades count:', len(flagged))
                        # save flagged subset
                        out_cols = [c for c in ['ts','timestamp','price','price_val',amt_col,'size','price_move_pct'] if c in flagged.columns]
                        flagged.to_csv(LARGE_TRADES_OUT, columns=out_cols if out_cols else None)
                        print('Saved flagged trades to', LARGE_TRADES_OUT)

print('\nDone')
