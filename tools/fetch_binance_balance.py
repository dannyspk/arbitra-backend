#!/usr/bin/env python3
import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.abspath('src'))

from arbitrage.web import _get_ccxt_instance

async def main():
    key = (os.environ.get('BINANCE_API_KEY') or '').strip()
    secret = (os.environ.get('BINANCE_API_SECRET') or '').strip()
    if not key or not secret:
        print(json.dumps({'error': 'BINANCE_API_KEY/SECRET not configured'}))
        return
    inst = await _get_ccxt_instance('binance', key, secret)
    if inst is None:
        print(json.dumps({'error': 'ccxt/binance instance unavailable'}))
        return
    def _fetch():
        try:
            # CCXTExchange exposes the underlying ccxt client as .client
            return inst.client.fetch_balance()
        except Exception as e:
            return {'error': str(e)}
    bal = await asyncio.to_thread(_fetch)
    # Print succinct summary: total/free/locked per asset if available, else raw
    if isinstance(bal, dict) and ('total' in bal or 'free' in bal):
        out = {}
        totals = bal.get('total') or {}
        free = bal.get('free') or {}
        locked = bal.get('locked') or {}
        non_zero = {}
        for k, v in totals.items():
            t = totals.get(k) or 0.0
            f = free.get(k) or 0.0
            l = locked.get(k) or 0.0
            out[k] = {'total': t, 'free': f, 'locked': l}
            if float(t) != 0.0:
                non_zero[k] = out[k]
        summary = {'total_assets': len(out), 'non_zero_count': len(non_zero), 'non_zero': non_zero}
        print(json.dumps({'balances': out, 'summary': summary}, indent=2))
    else:
        print(json.dumps({'balance_raw': bal}, indent=2, default=str))

if __name__ == '__main__':
    asyncio.run(main())
