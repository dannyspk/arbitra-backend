#!/usr/bin/env python3
"""Run the dead-cat grid but use the 1d CSV as the primary timeframe.
This sets both the '15m' and '1d' inputs to the daily file so the external script
receives daily data for both timeframes (useful if you want to test daily-only behavior).
Saves results to var/myx_deadcat_grid_results_daily.json
"""
import sys
import os
import json
import inspect

script_dir = r'c:\cointistreact\public\assets\guidesgemin'
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    import binance_perps_deadcat_backtest as mod
except Exception as e:
    print('Failed to import external module:', e)
    sys.exit(1)

# same patch helper as before
def ensure_patch(mod):
    import inspect
    src = inspect.getsource(mod.run_backtest)
    old = """
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    trades_df = trades_df[['side','entry_time','entry','size','sl','tp','exit_time','exit','pnl','r_multiple','reason']]

    # Metrics
"""
    if old not in src:
        return
    new = """
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    expected_cols = ['side','entry_time','entry','size','sl','tp','exit_time','exit','pnl','r_multiple','reason']
    if trades_df.empty:
        trades_df = pd.DataFrame(columns=expected_cols)
    else:
        present = [c for c in expected_cols if c in trades_df.columns]
        trades_df = trades_df[present]

    # Metrics
"""
    patched = src.replace(old, new)
    g = mod.__dict__
    exec(patched, g)

csv_daily = 'var/myx_1d.csv'
if not os.path.exists(csv_daily):
    print('Daily CSV missing; run tools/fetch_myx_klines_csv.py first')
    sys.exit(1)

try:
    # load via module loader (some versions expect df inputs)
    df_daily = mod.load_csv(csv_daily)
except Exception as e:
    print('Failed to load CSV with module loader:', e)
    # fall back to reading as text
    import pandas as pd
    df_daily = pd.read_csv(csv_daily)

short_rsi_vals = [40, 50, 60]
short_cross_opts = [True, False]
long_bounce_opts = [True, False]

results = []
for rsi in short_rsi_vals:
    for cross in short_cross_opts:
        for lb in long_bounce_opts:
            cfg = mod.Config()
            cfg.symbol = 'MYX/USDT'
            # point both csv paths to daily file so script sees daily on both timeframes
            cfg.csv_15m = csv_daily
            cfg.csv_1d = csv_daily
            cfg.short_rsi_min = rsi
            cfg.short_cross_20 = cross
            cfg.enable_long_bounce = lb
            try:
                out = mod.run_backtest(cfg, df_daily, df_daily)
            except Exception as e:
                try:
                    ensure_patch(mod)
                    out = mod.run_backtest(cfg, df_daily, df_daily)
                except Exception as e2:
                    print('Failed for', rsi, cross, lb, '->', e2)
                    results.append({'short_rsi_min': rsi, 'short_cross_20': cross, 'enable_long_bounce': lb, 'error': str(e2)})
                    continue

            try:
                eq_df, trades_df, summary = out
            except Exception:
                try:
                    eq_df = out[0]
                    trades_df = out[1]
                    summary = out[2]
                except Exception as e:
                    print('Bad output for', rsi, cross, lb, '->', e)
                    results.append({'short_rsi_min': rsi, 'short_cross_20': cross, 'enable_long_bounce': lb, 'error': 'bad output'})
                    continue

            trades_count = 0
            try:
                trades_count = int(summary.get('trades', 0))
            except Exception:
                try:
                    trades_count = len(trades_df)
                except Exception:
                    trades_count = 0

            results.append({'short_rsi_min': rsi, 'short_cross_20': cross, 'enable_long_bounce': lb, 'trades': trades_count, 'summary': summary})
            print(f"rsi={rsi} cross={cross} long_bounce={lb} -> trades={trades_count} return={summary.get('return_pct')}")

os.makedirs('var', exist_ok=True)
with open('var/myx_deadcat_grid_results_daily.json', 'w', encoding='utf8') as f:
    json.dump({'symbol': 'MYX/USDT', 'results': results}, f, indent=2)

print('Wrote var/myx_deadcat_grid_results_daily.json')
