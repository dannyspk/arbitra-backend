"""Probe XYM variants across multiple exchanges and print ticker/orderbook/metadata.

Usage:
  python tmp_probe_xym.py
"""
from __future__ import annotations
import os, sys, json, time
ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from pprint import pprint

exchange_ids = ['bitrue', 'kucoin', 'okx', 'gate', 'mexc', 'binance']
variants = ['XYM', 'XYM/USDT', 'XYM-USDT', 'XYMUSDT', 'xym']

print('Probing exchanges:', exchange_ids)

# Try to import adapters
try:
    from arbitrage.exchanges.mexc_adapter import MEXCExchange
    from arbitrage.exchanges.ccxt_adapter import CCXTExchange
except Exception as e:
    print('Failed to import adapters:', e)
    raise

PER_EX_TIMEOUT_MS = int(os.environ.get('TMP_PROBE_TIMEOUT_MS', '2000'))

for eid in exchange_ids:
    print('\n--- Exchange:', eid, '---')
    try:
        if eid == 'mexc':
            ex = MEXCExchange(api_key=os.getenv('MEXC_API_KEY'), secret=os.getenv('MEXC_API_SECRET'), timeout=PER_EX_TIMEOUT_MS)
        else:
            ex = CCXTExchange(eid, options={'timeout': PER_EX_TIMEOUT_MS, 'enableRateLimit': True})
    except Exception as e:
        print('  adapter init failed:', e)
        continue

    name = getattr(ex, 'name', eid)
    print('Adapter name:', name)

    # Currency metadata and supports
    base = 'XYM'
    try:
        if hasattr(ex, 'supports_withdraw'):
            try:
                sw = ex.supports_withdraw(base)
            except Exception as e:
                sw = f'error: {e}'
        else:
            sw = 'n/a'
        if hasattr(ex, 'supports_deposit'):
            try:
                sd = ex.supports_deposit(base)
            except Exception as e:
                sd = f'error: {e}'
        else:
            sd = 'n/a'
        print('  supports_withdraw:', sw, 'supports_deposit:', sd)
    except Exception as e:
        print('  supports checks failed:', e)

    # get_currency_details if available
    try:
        if hasattr(ex, 'get_currency_details'):
            cd = ex.get_currency_details(base)
            print('  get_currency_details ->')
            pprint(cd)
        else:
            print('  get_currency_details: n/a')
    except Exception as e:
        print('  get_currency_details failed:', e)

    # For each variant, try fetch_ticker and get_order_book
    client = getattr(ex, 'client', None)
    for v in variants:
        print('  Variant:', v)
        # fetch_ticker
        try:
            if client is not None and hasattr(client, 'fetch_ticker'):
                t = client.fetch_ticker(v)
                last = t.get('last') if isinstance(t, dict) else None
                bid = t.get('bid') if isinstance(t, dict) else None
                ask = t.get('ask') if isinstance(t, dict) else None
                print('    fetch_ticker -> last:', last, 'bid:', bid, 'ask:', ask)
            elif hasattr(ex, 'get_tickers'):
                tk = ex.get_tickers()
                val = tk.get(v)
                print('    get_tickers lookup ->', val)
            else:
                print('    no ticker interface')
        except Exception as e:
            print('    fetch_ticker failed:', e)

        # orderbook
        try:
            if hasattr(ex, 'get_order_book'):
                ob = ex.get_order_book(v)
                if ob is None:
                    print('    get_order_book -> None')
                else:
                    asks = ob.get('asks', [])
                    bids = ob.get('bids', [])
                    print(f'    order_book asks:{len(asks)} bids:{len(bids)}')
                    if asks:
                        print('      top ask:', asks[0])
                    if bids:
                        print('      top bid:', bids[0])
            else:
                print('    get_order_book not available')
        except Exception as e:
            print('    get_order_book failed:', e)

    # done exchange
    time.sleep(0.1)

print('\nProbe complete.')
