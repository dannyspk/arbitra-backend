#!/usr/bin/env python3
"""
Compute a volatility index for the current hotcoins list.

This script:
- fetches top hotcoins via the project's `hotcoins.find_hot_coins()` helper (which uses Binance REST when feeders
  are not provided)
- for each symbol, downloads recent klines from Binance and computes realized volatility from log returns
- outputs a simple ranked list and optional CSV

Usage:
    python tools/volatility_index.py --top 20 --interval 1h --lookback 24

Notes:
- No external dependencies required (uses urllib + math + statistics)
- Network access to Binance REST endpoints is required.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from typing import List, Dict, Tuple, Optional
from urllib import request, parse

# Ensure repository root is on sys.path so imports like `src.arbitrage` work
try:
    import os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
except Exception:
    pass

# Import the project's hotcoins helper
try:
    # prefer direct src import when running from repo root
    from src.arbitrage.hotcoins import find_hot_coins
except Exception:
    try:
        # try package import (when installed as module)
        from arbitrage.hotcoins import find_hot_coins
    except Exception:
        find_hot_coins = None


BINANCE_KLINES_URL = 'https://api.binance.com/api/v3/klines'


def _http_get_json(url: str, timeout: float = 10.0) -> Optional[dict]:
    try:
        req = request.Request(url, headers={"User-Agent": "vol-index/1.0"})
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode('utf-8'))
    except Exception as e:
        print('HTTP error for', url, '->', e, file=sys.stderr)
        return None


def fetch_klines(symbol: str, interval: str = '1h', limit: int = 100) -> List[List]:
    params = {'symbol': symbol.replace('/', '').replace('-', ''), 'interval': interval, 'limit': limit}
    url = BINANCE_KLINES_URL + '?' + parse.urlencode(params)
    data = _http_get_json(url)
    if not isinstance(data, list):
        return []
    return data


def close_prices_from_klines(klines: List[List]) -> List[float]:
    # klines format: [openTime, open, high, low, close, ...]
    out = []
    for k in klines:
        try:
            out.append(float(k[4]))
        except Exception:
            continue
    return out


def realized_volatility_from_prices(prices: List[float], periods_per_year: float) -> Optional[float]:
    if not prices or len(prices) < 2:
        return None
    # compute log returns
    rets = []
    for i in range(1, len(prices)):
        p0 = prices[i - 1]
        p1 = prices[i]
        if p0 <= 0 or p1 <= 0:
            continue
        rets.append(math.log(p1 / p0))
    if not rets:
        return None
    sd = statistics.pstdev(rets) if len(rets) >= 1 else None
    if sd is None:
        return None
    # annualize
    return sd * math.sqrt(periods_per_year)


def ewma_volatility_from_prices(prices: List[float], alpha: float, periods_per_year: float) -> Optional[float]:
    """Compute EWMA volatility (annualized) from close prices using decay alpha.

    alpha: persistence factor (0 < alpha < 1). Typical values 0.94.
    Uses squared returns EWMA: var_t = alpha * var_{t-1} + (1-alpha) * r_t^2
    """
    if not prices or len(prices) < 2:
        return None
    ewma_var = 0.0
    initialized = False
    for i in range(1, len(prices)):
        p0 = prices[i - 1]
        p1 = prices[i]
        if p0 <= 0 or p1 <= 0:
            continue
        r = math.log(p1 / p0)
        if not initialized:
            # initialize with first squared return
            ewma_var = r * r
            initialized = True
        else:
            ewma_var = alpha * ewma_var + (1.0 - alpha) * (r * r)
    if not initialized:
        return None
    ewma_sd = math.sqrt(ewma_var)
    return ewma_sd * math.sqrt(periods_per_year)


def periodicity(interval: str) -> float:
    # return number of periods per year for given interval
    # supported: 1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,1d
    if interval.endswith('m'):
        mins = int(interval[:-1])
        return 60 * 24 * 365 / mins
    if interval.endswith('h'):
        hours = int(interval[:-1])
        return 24 * 365 / hours
    if interval.endswith('d'):
        days = int(interval[:-1])
        return 365 / days
    # default to hourly
    return 24 * 365


def percentile_rank(values: List[float], v: float) -> float:
    # simple percentile rank (0-100)
    if not values:
        return 0.0
    less = sum(1 for x in values if x < v)
    equal = sum(1 for x in values if x == v)
    return 100.0 * (less + 0.5 * equal) / len(values)


def compute_vol_index(symbols: List[str], interval: str = '1h', lookback: int = 24) -> List[Dict]:
    per_year = periodicity(interval)
    rows: List[Dict] = []
    for sym in symbols:
        klines = fetch_klines(sym, interval=interval, limit=lookback + 1)
        if not klines:
            print('No klines for', sym, file=sys.stderr)
            continue
        prices = close_prices_from_klines(klines)
        vol = realized_volatility_from_prices(prices, per_year)
        last_price = prices[-1] if prices else None
        rows.append({'symbol': sym, 'volatility': vol, 'last': last_price})
        # be kind to API rate limits
        time.sleep(0.12)

    # normalize into percentile ranks
    vols = [r['volatility'] for r in rows if r['volatility'] is not None]
    for r in rows:
        v = r.get('volatility')
        r['vol_percentile'] = percentile_rank(vols, v) if v is not None else 0.0
    # sort by volatility desc
    rows.sort(key=lambda x: (x.get('volatility') or 0.0), reverse=True)
    return rows


def compute_movers_and_ewma(rows: List[Dict], interval: str, lookback: int, ewma_alpha: float) -> List[Dict]:
    per_year = periodicity(interval)
    for r in rows:
        sym = r.get('symbol')
        klines = fetch_klines(sym, interval=interval, limit=lookback + 1)
        prices = close_prices_from_klines(klines)
        # movers: percent change over lookback (last/first -1)
        mover = None
        if prices and len(prices) >= 2:
            try:
                mover = (prices[-1] / prices[0] - 1.0)
            except Exception:
                mover = None
        r['mover'] = mover
        # ewma vol
        ewma = ewma_volatility_from_prices(prices, alpha=ewma_alpha, periods_per_year=per_year)
        r['ewma_volatility'] = ewma
        # attach first/last timestamps where available
        r['num_prices'] = len(prices)
        time.sleep(0.12)
    return rows


def main(argv: List[str]):
    p = argparse.ArgumentParser(description='Compute volatility index for hotcoins list')
    p.add_argument('--top', type=int, default=20, help='how many hotcoins to query')
    p.add_argument('--interval', type=str, default='1d', help='kline interval (e.g. 1h,4h,1d). Default changed to 1d (24h)')
    p.add_argument('--lookback', type=int, default=24, help='number of periods to use for realized vol')
    p.add_argument('--csv', type=str, default=None, help='optional output CSV file path')
    p.add_argument('--history', type=str, default=None, help='path to append historical vol index CSV (timestamp,symbol,last,volatility,ewma_volatility,vol_percentile,mover)')
    p.add_argument('--plot', action='store_true', help='if set, attempt to plot history CSV (requires matplotlib)')
    p.add_argument('--ewma-alpha', type=float, default=0.94, help='alpha for EWMA variance (0-1), typical 0.94')
    args = p.parse_args(argv)

    if find_hot_coins is None:
        print('Error: cannot import project hotcoins helper; run from repository root so imports work', file=sys.stderr)
        sys.exit(1)

    print(f'Fetching top {args.top} hotcoins...')
    try:
        items = find_hot_coins(exchanges=None, max_results=args.top)
    except Exception as e:
        print('Error calling find_hot_coins:', e, file=sys.stderr)
        items = []

    # If the helper returned no items, try a direct fallback to the Binance REST helper
    if not items:
        try:
            from src.arbitrage.hotcoins import _binance_top_by_volume
            # Attempt to also import exclusion helpers (best-effort). If unavailable,
            # we'll fall back to a built-in default exclusion set.
            try:
                from src.arbitrage.hotcoins import _coingecko_top_symbols_by_marketcap, _parse_binance_symbol, _is_stablecoin_symbol
            except Exception:
                _coingecko_top_symbols_by_marketcap = None
                _parse_binance_symbol = None
                _is_stablecoin_symbol = None

            print('find_hot_coins returned empty; falling back to _binance_top_by_volume()', file=sys.stderr)
            items = _binance_top_by_volume(top_n=args.top)

            # If we got items from Binance, apply major-cap exclusion to match
            # hotcoins.find_hot_coins behavior so volatility index ignores top market-cap coins.
            if items and (_coingecko_top_symbols_by_marketcap or _parse_binance_symbol):
                # build base list
                bases = []
                for it in items:
                    try:
                        sym = it.get('symbol') if isinstance(it, dict) else None
                        if not sym:
                            continue
                        if _parse_binance_symbol:
                            b, q = _parse_binance_symbol(sym)
                            b = (b or '').upper()
                        else:
                            s = str(sym).upper().replace('/', '').replace('-', '')
                            # best-effort: treat last 4 chars as quote if endswith USDT/BUSD/USDC
                            if s.endswith('USDT') or s.endswith('BUSD') or s.endswith('USDC'):
                                if s.endswith('USDT'):
                                    b = s[:-4]
                                else:
                                    b = s[:-4]
                            else:
                                b = s[:-3]
                        if b:
                            bases.append(b)
                    except Exception:
                        continue

                # compute exclusion set via coingecko helper when available
                exclude_set = set()
                try:
                    if _coingecko_top_symbols_by_marketcap:
                        excl = _coingecko_top_symbols_by_marketcap(bases, limit=20)
                        exclude_set = {s.upper() for s in (excl or [])}
                except Exception:
                    exclude_set = set()

                # fallback built-in set (same conservative list used in hotcoins.find_hot_coins)
                if not exclude_set:
                    DEFAULT_TOP_MARKETCAPS = {
                        'BTC', 'ETH', 'USDT', 'USDC', 'BNB', 'ADA', 'XRP', 'DOGE', 'SOL', 'DOT',
                        'BCH', 'LTC', 'LINK', 'MATIC', 'TRX', 'SHIB', 'AVAX', 'UNI', 'ATOM', 'WBTC'
                    }
                    bases_set = set(bases)
                    exclude_set = {s for s in DEFAULT_TOP_MARKETCAPS if s in bases_set}

                # filter items by excluding top market caps and stable-like bases
                filtered = []
                for it in items:
                    try:
                        sym = it.get('symbol') if isinstance(it, dict) else None
                        if not sym:
                            continue
                        if _parse_binance_symbol:
                            b, q = _parse_binance_symbol(sym)
                            b = (b or '').upper()
                        else:
                            s = str(sym).upper().replace('/', '').replace('-', '')
                            if s.endswith('USDT') or s.endswith('BUSD') or s.endswith('USDC'):
                                b = s[:-4]
                            else:
                                b = s[:-3]
                        if not b:
                            continue
                        if b in exclude_set:
                            continue
                        # skip stablecoin-like bases
                        if _is_stablecoin_symbol and _is_stablecoin_symbol(b):
                            continue
                        filtered.append(it)
                    except Exception:
                        continue
                items = filtered
        except Exception as e:
            print('Fallback _binance_top_by_volume failed:', e, file=sys.stderr)
            items = []

    symbols = []
    for it in items:
        sym = it.get('symbol') if isinstance(it, dict) else None
        if sym:
            symbols.append(sym.replace('/', '').replace('-', ''))

    if not symbols:
        print('No symbols found, exiting', file=sys.stderr)
        sys.exit(1)

    print('Computing volatility for', len(symbols), 'symbols (interval=', args.interval, ' lookback=', args.lookback, ')')
    rows = compute_vol_index(symbols, interval=args.interval, lookback=args.lookback)
    rows = compute_movers_and_ewma(rows, interval=args.interval, lookback=args.lookback, ewma_alpha=args.ewma_alpha)

    # print table
    print('\nSymbol     Last      Volatility(ann)   Percentile')
    for r in rows:
        sym = r.get('symbol')
        last = r.get('last')
        vol = r.get('volatility')
        pct = r.get('vol_percentile')
        print(f"{sym:10} {str(last):10} {'' if vol is None else f'{vol:.2%}':18} {pct:6.1f}")

    # persist history rows if requested
    if args.history:
        try:
            import csv
            import datetime
            now_iso = datetime.datetime.utcnow().isoformat()
            with open(args.history, 'a', newline='') as fh:
                w = csv.writer(fh)
                # write header if file empty
                try:
                    fh.seek(0)
                    first = fh.read(1)
                except Exception:
                    first = None
                if not first:
                    w.writerow(['ts', 'symbol', 'last', 'volatility', 'ewma_volatility', 'vol_percentile', 'mover'])
                for r in rows:
                    w.writerow([now_iso, r.get('symbol'), r.get('last'), r.get('volatility'), r.get('ewma_volatility'), r.get('vol_percentile'), r.get('mover')])
            print('Appended history to', args.history)
        except Exception as e:
            print('History write error:', e, file=sys.stderr)

    # optional plotting of history file (requires matplotlib)
    if args.plot and args.history:
        try:
            import matplotlib.pyplot as plt
            import csv
            from collections import defaultdict
            ts_map = defaultdict(list)
            with open(args.history, 'r', newline='') as fh:
                rdr = csv.DictReader(fh)
                for row in rdr:
                    try:
                        ts = row.get('ts')
                        sym = row.get('symbol')
                        vol = float(row.get('volatility') or 0)
                    except Exception:
                        continue
                    ts_map[sym].append((ts, vol))
            # choose top few movers to plot
            to_plot = list(ts_map.keys())[:6]
            plt.figure(figsize=(10, 6))
            for sym in to_plot:
                data = ts_map[sym]
                data.sort(key=lambda x: x[0])
                xs = [d[0] for d in data]
                ys = [d[1] for d in data]
                plt.plot(xs, ys, label=sym)
            plt.xticks(rotation=30)
            plt.ylabel('Annualized Volatility')
            plt.legend()
            plt.title('Hotcoins Volatility History')
            plt.tight_layout()
            plt.show()
        except Exception as e:
            print('Plot error (matplotlib required):', e, file=sys.stderr)

    if args.csv:
        try:
            import csv
            with open(args.csv, 'w', newline='') as fh:
                w = csv.DictWriter(fh, fieldnames=['symbol', 'last', 'volatility', 'vol_percentile'])
                w.writeheader()
                for r in rows:
                    w.writerow({'symbol': r.get('symbol'), 'last': r.get('last'), 'volatility': r.get('volatility'), 'vol_percentile': r.get('vol_percentile')})
            print('Wrote', args.csv)
        except Exception as e:
            print('CSV write error:', e, file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1:])
