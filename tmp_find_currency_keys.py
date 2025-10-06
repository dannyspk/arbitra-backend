"""Find currency metadata keys matching a token substring and print details.

Usage:
  python tmp_find_currency_keys.py --exchange mexc --q XYM

This helps locate tokens that may be listed under different keys (e.g., 'XYM', 'XYMTRC20', etc.)
and inspect withdraw/deposit flags and per-network info.
"""
import argparse
import pprint

try:
    import ccxt
except Exception:
    ccxt = None

parser = argparse.ArgumentParser()
parser.add_argument('--exchange', default='mexc')
parser.add_argument('--q', default='XYM')
args = parser.parse_args()

if ccxt is None:
    print('ccxt not installed. pip install ccxt')
    raise SystemExit(1)

if not hasattr(ccxt, args.exchange):
    print(f"ccxt build does not include exchange '{args.exchange}'")
    raise SystemExit(1)

ex = getattr(ccxt, args.exchange)({})
print('Fetching currencies... (may take a few seconds)')
try:
    cur = ex.fetch_currencies()
except Exception as e:
    print('fetch_currencies failed:', e)
    raise

q = args.q.lower()
matches = []
for k, v in (cur.items() if isinstance(cur, dict) else []):
    if q in str(k).lower() or (isinstance(v, dict) and q in str(v.get('id', '')).lower()):
        matches.append((k, v))

pp = pprint.PrettyPrinter(depth=3, compact=False)
print(f'Found {len(matches)} matching currency entries for query "{args.q}":')
for k, v in matches:
    print('\n--- KEY:', k, '---')
    pp.pprint(v)
    # print networks summary if present
    if isinstance(v, dict):
        nets = v.get('networks') or v.get('channels')
        if isinstance(nets, dict):
            print('\nNetworks:')
            for n, info in nets.items():
                print(' -', n)
                pp.pprint(info)

if not matches:
    # as a fallback, print a few currency keys that might be similar
    print('\nNo exact matches; printing a short sample of currency keys for manual inspection:')
    sample_keys = list(cur.keys())[:60]
    for key in sample_keys:
        print(' -', key)
