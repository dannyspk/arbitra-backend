#!/usr/bin/env python3
"""Patch-run the external deadcat backtest to guard against empty trades DataFrame.
This imports the external module, extracts run_backtest source, replaces the lines that
select trade columns with a guarded version, injects the patched function into the
module's globals, and executes it.
"""
import sys
import inspect
import types

script_dir = r'c:\cointistreact\public\assets\guidesgemin'
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

import binance_perps_deadcat_backtest as mod

src = inspect.getsource(mod.run_backtest)
# find the problematic block that assigns trades_df and slices columns
old = """
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    trades_df = trades_df[['side','entry_time','entry','size','sl','tp','exit_time','exit','pnl','r_multiple','reason']]

    # Metrics
"""

new = """
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    # Guard: if empty, create empty df with expected columns
    expected_cols = ['side','entry_time','entry','size','sl','tp','exit_time','exit','pnl','r_multiple','reason']
    if trades_df.empty:
        trades_df = pd.DataFrame(columns=expected_cols)
    else:
        # keep only expected columns but tolerate missing ones
        present = [c for c in expected_cols if c in trades_df.columns]
        trades_df = trades_df[present]

    # Metrics
"""

if old not in src:
    print('Did not find expected block to patch; aborting')
    sys.exit(1)

patched_src = src.replace(old, new)
# compile and exec the patched function in module globals
g = mod.__dict__
try:
    exec(patched_src, g)
except Exception as e:
    print('Failed to exec patched source:', e)
    sys.exit(1)

# now call the patched function
from binance_perps_deadcat_backtest import Config, load_csv
cfg = Config(symbol='MYX/USDT', csv_15m='var/myx_15m.csv', csv_1d='var/myx_1d.csv')
try:
    df15 = load_csv(cfg.csv_15m)
    df1d = load_csv(cfg.csv_1d)
except Exception as e:
    print('Failed to load CSVs:', e)
    sys.exit(1)

try:
    eq_df, trades_df, summary = mod.run_backtest(cfg, df15, df1d)
except Exception as e:
    print('Patched run_backtest raised exception:', e)
    sys.exit(1)

print('Patched run complete. Trades:', len(trades_df))
print('Summary:', summary)
# save outputs
eq_df.to_csv('MYX_deadcat_equity.csv')
trades_df.to_csv('MYX_deadcat_trades.csv', index=False)
print('Saved MYX_deadcat_equity.csv and MYX_deadcat_trades.csv')
