import os
import sys
import time

# ensure local src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

print('PYTHONPATH:', sys.path[0])

try:
    from arbitrage.feeder_utils import start_all, stop_all
    from arbitrage.exchanges.ws_feed_manager import get_feeder
except Exception as e:
    print('import failed:', e)
    raise

print('Starting feeders (gate) via start_all...')
feeders = start_all(exchanges=['gate'])
print('start_all returned keys:', list(feeders.keys()))

# give feeders some time to start and register
time.sleep(2)

try:
    f = get_feeder('gate')
    print('get_feeder("gate") ->', repr(f))
    if f is not None:
        last_ts = getattr(f, 'last_update_ts', None) or getattr(f, '_ts', None)
        try:
            syms = getattr(f, 'symbols', None) or getattr(f, '_symbols', None) or []
            print('symbols sample (first 10):', (syms[:10] if isinstance(syms, (list, tuple)) else 'not a list'))
        except Exception:
            pass
        print('last_update_ts:', last_ts)
    else:
        print('Feeder not registered (None)')
except Exception as e:
    print('error checking feeder:', e)

print('Stopping feeders...')
try:
    stop_all(feeders)
except Exception as e:
    print('stop_all failed:', e)

print('Done.')
