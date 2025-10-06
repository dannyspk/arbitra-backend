#!/usr/bin/env python3
"""Fetch MEXC "last" price for the hotcoins top-20 and print JSON.

This script imports the project's hotcoins finder (so it uses the same
top-20 logic) and then queries MEXC REST ticker endpoint trying a couple
of common symbol formats (underscore and no-separator) until one returns
a price. Results are printed to stdout as JSON.

Usage: python tools/get_mexc_prices_hotcoins.py

The script adds the project `src` to sys.path so it can be run from the
repo root without extra env vars.
"""
from __future__ import annotations

import json
import sys
import time
from typing import List, Dict, Optional

import requests

# ensure we can import the package from repo root when running the script
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

try:
    from arbitrage.hotcoins import _binance_top_by_volume
except Exception as e:
    print('Error importing _binance_top_by_volume:', e, file=sys.stderr)
    raise


MEXC_BASE = os.environ.get('MEXC_REST') or 'https://api.mexc.com'
TICKER_PATH = '/api/v3/ticker/price'


def try_mexc_price_for(base: str, quote: str) -> Dict[str, Optional[object]]:
    """Try common MEXC symbol formats and return a dict with result info."""
    base_u = (base or '').strip().upper()
    quote_u = (quote or '').strip().upper()
    candidates: List[str] = []
    if base_u and quote_u:
        candidates.append(f"{base_u}_{quote_u}")
        candidates.append(f"{base_u}{quote_u}")
        # some older endpoints may accept SYMBOL like BTC_USDT or BTCUSDT; try both
        # also try swapping underscore to hyphen (less likely but cheap)
        candidates.append(f"{base_u}-{quote_u}")
    else:
        candidates.append(base_u or base)

    last_err = None
    for cand in candidates:
        if not cand:
            continue
        url = f"{MEXC_BASE}{TICKER_PATH}?symbol={cand}"
        try:
            r = requests.get(url, timeout=5)
        except Exception as e:
            last_err = str(e)
            continue
        if r.status_code != 200:
            last_err = f"status={r.status_code}"
            continue
        try:
            data = r.json()
        except Exception as e:
            last_err = f"jsonerr:{e}"
            continue
        # typical successful shape: {"symbol":"BTC_USDT","price":"12345.67"}
        price_raw = None
        if isinstance(data, dict):
            price_raw = data.get('price') or data.get('last') or data.get('close')
        if price_raw is None:
            last_err = f"no-price-in-response:{data}"
            continue
        try:
            price = float(price_raw)
        except Exception:
            price = None
        return {'mexc_symbol': cand, 'price': price, 'price_raw': price_raw, 'status': 'ok'}

    # all candidates failed
    return {'mexc_symbol': None, 'price': None, 'price_raw': None, 'status': f'failed ({last_err})'}


def main() -> None:
    # fetch top-20 by quote-denominated volume from Binance (stable helper)
    hot = _binance_top_by_volume(top_n=20)
    # Build a minimal mapping: symbol -> price (only the numeric price value, nothing else)
    prices_map: dict = {}
    for item in hot:
        base = (item.get('base') or '').upper()
        quote = (item.get('quote') or '').upper() if item.get('quote') else 'USDT'
        if not base:
            continue
        sym_key = f"{base}/{quote}"
        res = try_mexc_price_for(base, quote)
        # store numeric price or null
        prices_map[sym_key] = res.get('price') if res.get('price') is not None else None

    # Print only the minimal payload: mapping of symbol -> price (JSON object)
    print(json.dumps(prices_map))


if __name__ == '__main__':
    main()
