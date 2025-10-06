"""Quick helper to inspect currency metadata for MEXC via ccxt.

Run: python tmp_check_currency_meta.py

It prints the XYM currency entry (or any token passed via --token).
"""
import argparse
import pprint

try:
    import ccxt
except Exception:
    ccxt = None

parser = argparse.ArgumentParser()
parser.add_argument('--exchange', default='mexc')
parser.add_argument('--token', default='XYM')
args = parser.parse_args()

if ccxt is None:
    print('ccxt not installed. pip install ccxt')
    raise SystemExit(1)

if not hasattr(ccxt, args.exchange):
    print(f"ccxt build does not include exchange '{args.exchange}'")
    raise SystemExit(1)

ex = getattr(ccxt, args.exchange)({})
print('Fetching currencies... (may take a few seconds)')
cur = None
try:
    cur = ex.fetch_currencies()
except Exception as e:
    print('fetch_currencies failed:', e)
    raise

key = args.token
entry = cur.get(key) or cur.get(key.upper()) or cur.get(key.lower())
print('--- ENTRY ---')
pp = pprint.PrettyPrinter(indent=2)
pp.pprint(entry)

# if networks present, print summaries
if isinstance(entry, dict):
    nets = entry.get('networks') or entry.get('channels')
    if isinstance(nets, dict):
        print('\n--- NETWORKS ---')
        for n, info in nets.items():
            print(n)
            pp.pprint(info)
