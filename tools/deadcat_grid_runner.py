#!/usr/bin/env python3
"""Run a small grid over the external dead-cat backtest for MYX using local CSVs.
Grid over: short_rsi_min, short_cross_20, enable_long_bounce
Saves results to var/myx_deadcat_grid_results.json
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

# helper to patch run_backtest like earlier if it throws KeyError on empty trades
import types

def ensure_patch(mod):
    # if mod.run_backtest already patched (we can detect by name), skip
    src = inspect.getsource(mod.run_backtest)
    if "expected_cols = ['side'" in src:
        return
    old = """
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    trades_df = trades_df[['side','entry_time','entry','size','sl','tp','exit_time','exit','pnl','r_multiple','reason']]

    # Metrics
"""
    if old not in src:
        # can't apply patch safely
        return
    new = """
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    # Guard: if empty, create empty df with expected columns
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

# load CSVs using module's loader
csv15 = 'var/myx_15m.csv'
csv1d = 'var/myx_1d.csv'
if not os.path.exists(csv15) or not os.path.exists(csv1d):
    print('CSV files missing; please run tools/fetch_myx_klines_csv.py first')
    sys.exit(1)

try:
    df15 = mod.load_csv(csv15)
    df1d = mod.load_csv(csv1d)
except Exception as e:
    print('Failed to load CSVs via module loader:', e)
    sys.exit(1)

short_rsi_vals = [40, 50, 60]
short_cross_opts = [True, False]
long_bounce_opts = [True, False]

results = []
for rsi in short_rsi_vals:
    for cross in short_cross_opts:
        for lb in long_bounce_opts:
            cfg = mod.Config()
            cfg.symbol = 'MYX/USDT'
            cfg.csv_15m = csv15
            cfg.csv_1d = csv1d
            cfg.short_rsi_min = rsi
            cfg.short_cross_20 = cross
            cfg.enable_long_bounce = lb
            try:
                out = mod.run_backtest(cfg, df15, df1d)
            except KeyError as ke:
                # try patching and re-running
                try:
                    ensure_patch(mod)
                    out = mod.run_backtest(cfg, df15, df1d)
                except Exception as e:
                    print('Failed after patch for', rsi, cross, lb, '->', e)
                    results.append({'short_rsi_min': rsi, 'short_cross_20': cross, 'enable_long_bounce': lb, 'error': str(e)})
                    continue
            except Exception as e:
                # try patch then retry
                try:
                    ensure_patch(mod)
                    out = mod.run_backtest(cfg, df15, df1d)
                except Exception as e2:
                    print('Failed for', rsi, cross, lb, '->', e2)
                    results.append({'short_rsi_min': rsi, 'short_cross_20': cross, 'enable_long_bounce': lb, 'error': str(e2)})
                    continue

            # out is (eq_df, trades_df, summary)
            try:
                eq_df, trades_df, summary = out
            except Exception:
                # some versions return tuple differently; try to unpack
                try:
                    eq_df = out[0]
                    trades_df = out[1]
                    summary = out[2]
                except Exception as e:
                    print('Unexpected output format for', rsi, cross, lb, '->', e)
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
out_path = 'var/myx_deadcat_grid_results.json'
with open(out_path, 'w', encoding='utf8') as f:
    json.dump({'symbol': 'MYX/USDT', 'results': results}, f, indent=2)

print('Wrote', out_path)
