#!/usr/bin/env python3
import sys, inspect
script_dir = r'c:\cointistreact\public\assets\guidesgemin'
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
try:
    import binance_perps_deadcat_backtest as mod
except Exception as e:
    print('Import error:', e)
    sys.exit(1)

print('module file:', getattr(mod, '__file__', 'unknown'))
# print Config defaults
if hasattr(mod, 'Config'):
    try:
        cfg = mod.Config()
        print('\nConfig defaults:')
        for k, v in sorted(vars(cfg).items()):
            print(f'  {k} = {v!r}')
    except Exception as e:
        print('Failed to instantiate Config:', e)
else:
    print('No Config class found')

# try to print top of run_backtest source
if hasattr(mod, 'run_backtest'):
    try:
        src = inspect.getsource(mod.run_backtest)
        print('\nrun_backtest source (first 400 chars):')
        print(src[:400])
    except Exception as e:
        print('Could not get run_backtest source:', e)

# Try to find likely entry-check functions or names
candidates = ['entry','should_enter','check_entry','short_rsi_min','short_cross_20','enable_long_bounce']
print('\nModule attributes containing keywords:')
for name in dir(mod):
    for kw in candidates:
        if kw in name:
            print(' ', name)
            break

# Done
print('\nInspector done')
