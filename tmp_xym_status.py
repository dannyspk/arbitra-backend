"""Quick check: fetch currency details for XYM on MEXC and report withdraw/deposit state.

Usage:
  python tmp_xym_status.py

This uses the existing MEXCExchange adapter (which uses ccxt) and prints a summary.
"""
from __future__ import annotations
import os
import sys
ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from arbitrage.exchanges.mexc_adapter import MEXCExchange

candidates = ['XYM', 'XYMUSDT', 'XYM/USDT', 'XYM-USDT', 'XYMTRC20', 'XYMTRX', 'xym']

print('Instantiating MEXC adapter (live via ccxt)')
key = os.getenv('MEXC_API_KEY') or os.getenv('ARB_MEXC_API_KEY')
secret = os.getenv('MEXC_API_SECRET') or os.getenv('ARB_MEXC_API_SECRET')
if key and secret:
    print('Using MEXC API key from environment')
try:
    ex = MEXCExchange(api_key=key, secret=secret)
except Exception as e:
    print('Failed to create MEXCExchange:', e)
    raise

print('\nChecking supports_withdraw / supports_deposit for canonical keys:')
for tok in candidates:
    try:
        sup_w = ex.supports_withdraw(tok)
        sup_d = ex.supports_deposit(tok)
        print(f'  {tok:12s}  withdraw={sup_w!s:5s}  deposit={sup_d!s:5s}')
    except Exception as e:
        print(f'  {tok:12s}  error: {e}')

print('\nFetching currency details via adapter.get_currency_details for canonical tokens:')
for tok in candidates:
    try:
        cd = ex.get_currency_details(tok)
        print(f'\n--- {tok} ---')
        if cd is None:
            print('  -> no entry found')
            continue
        # print compact summary
        if isinstance(cd, dict):
            # print top-level keys of interest
            interesting = {}
            for k in ('id', 'code', 'withdraw', 'deposit', 'info', 'networks', 'channels', 'name'):
                if k in cd:
                    interesting[k] = cd[k]
            if 'markets' in cd:
                interesting['markets_count'] = len(cd['markets'])
            import pprint
            pprint.pprint(interesting)
        else:
            print('  unexpected type:', type(cd))
    except Exception as e:
        print(f'  {tok} -> error: {e}')

# As a last resort, fetch all currencies and search for XYM substring in keys
print('\nSearching fetch_currencies() keys for XYM substring...')
try:
    cur = ex.client.fetch_currencies()
    matches = [k for k in cur.keys() if 'XYM' in str(k).upper()]
    print('Found', len(matches), 'keys containing XYM (case-insensitive)')
    for k in matches[:40]:
        print(' -', k)
except Exception as e:
    print('fetch_currencies failed:', e)

print('\nDone.')
