#!/usr/bin/env python3
"""
Fetch the current hotcoin list from the local backend's binance feeder and
analyze 1-hour price movement using Binance public klines.

Usage: python tools/analyze_hotcoins_1h.py

Outputs a simple table and JSON summary to stdout.
"""
import json
import math
import sys
from urllib import request, parse
from statistics import mean

BACKEND = 'http://127.0.0.1:8000'
BINANCE_API = 'https://api.binance.com'

def fetch_binance_feeder():
    url = f"{BACKEND}/debug/feeder_depths?feeder_name=binance"
    try:
        with request.urlopen(url, timeout=20) as r:
            data = json.load(r)
            return data
    except Exception as e:
        print(f"Failed to fetch feeder depths: {e}", file=sys.stderr)
        return None

def fetch_klines(symbol, interval='1m', limit=60):
    q = parse.urlencode({'symbol': symbol, 'interval': interval, 'limit': str(limit)})
    url = f"{BINANCE_API}/api/v3/klines?{q}"
    try:
        with request.urlopen(url, timeout=20) as r:
            data = json.load(r)
            return data
    except Exception as e:
        print(f"Failed to fetch klines for {symbol}: {e}", file=sys.stderr)
        return None

def analyze_1h_from_1m_klines(klines):
    # klines: list of [openTime, open, high, low, close, ...]
    closes = [float(k[4]) for k in klines]
    if len(closes) < 2:
        return None
    last = closes[-1]
    first = closes[0]
    pct_change = (last / first - 1.0) * 100.0
    # simple slope via linear regression (normalized)
    n = len(closes)
    xs = list(range(n))
    xmean = (n-1)/2.0
    ymean = mean(closes)
    num = sum((x - xmean)*(y - ymean) for x,y in zip(xs, closes))
    den = sum((x - xmean)**2 for x in xs)
    slope = num/den if den != 0 else 0.0
    # 30-min SMA
    sma30 = mean(closes[-30:]) if n >= 30 else mean(closes)
    # last vs sma
    above_sma = last - sma30
    # compute total quote-volume over the hour (klines[7] is quote asset volume)
    quote_vol = 0.0
    try:
        for k in klines:
            qv = k[7] if len(k) > 7 else None
            if qv is None:
                continue
            quote_vol += float(qv)
    except Exception:
        quote_vol = 0.0
    return {
        'first': first,
        'last': last,
        'pct_change': pct_change,
        'slope': slope,
        'sma30': sma30,
        'above_sma': above_sma,
        'quote_volume_1h': quote_vol,
    }


def analyze_from_1m_klines_for_period(klines):
    """General analyzer for a list of 1m klines. Re-uses the same metrics but
    returns keys that do not assume a 1h period (caller can interpret)."""
    return analyze_1h_from_1m_klines(klines)

def classify(one_hour, min_quote_vol=1000.0):
    pct = one_hour['pct_change']
    slope = one_hour['slope']
    above_sma = one_hour['above_sma']
    qv = one_hour.get('quote_volume_1h', 0.0) or 0.0
    # If quote-volume is too low, do not emit strong signals
    if qv < float(min_quote_vol):
        # still allow mild labels if pct is large enough, but prefer to mark low-volume
        if abs(pct) >= 1.5 and ((pct > 0 and slope > 0) or (pct < 0 and slope < 0)):
            # large move despite low vol — return Mild label
            return 'Mild Bullish' if pct > 0 else 'Mild Bearish'
        return 'Neutral (low vol)'

    # thresholds (tunable) for adequate-volume symbols
    if pct >= 0.6 and above_sma > 0 and slope > 0:
        return 'Bullish'
    if pct <= -0.6 and above_sma < 0 and slope < 0:
        return 'Bearish'
    # weaker signals
    if pct > 0.2 and (above_sma > 0 or slope > 0):
        return 'Mild Bullish'
    if pct < -0.2 and (above_sma < 0 or slope < 0):
        return 'Mild Bearish'
    return 'Neutral'

def main():
    # Prefer the server's hotcoins snapshot (this matches HotCoinsPanel's WS list).
    # Fall back to /api/opportunities, then to feeder depths.
    symbols = []
    try:
        with request.urlopen(f"http://127.0.0.1:8000/api/hotcoins", timeout=10) as r:
            data = json.load(r)
            hot = data.get('hotcoins') if isinstance(data, dict) else None
            if hot and isinstance(hot, list) and len(hot) > 0:
                seen = set()
                for o in hot:
                    # hot list items contain 'symbol' and 'base'
                    s = (o.get('symbol') or o.get('base') or '')
                    if not s: continue
                    su = s.upper()
                    if su in seen: continue
                    seen.add(su)
                    symbols.append(su)
    except Exception:
        symbols = []

    # fallback: try /api/opportunities (old behavior)
    if not symbols:
        try:
            with request.urlopen(f"http://127.0.0.1:8000/api/opportunities", timeout=10) as r:
                data = json.load(r)
                opps = data.get('opportunities') if isinstance(data, dict) else None
                if opps and isinstance(opps, list) and len(opps) > 0:
                    seen = set()
                    for o in opps:
                        s = (o.get('symbol') or o.get('pair') or o.get('base') or '')
                        if not s: continue
                        su = s.upper()
                        if su in seen: continue
                        seen.add(su)
                        symbols.append(su)
        except Exception:
            symbols = []

    if not symbols:
        feeder = fetch_binance_feeder()
        if not feeder:
            print('No feeder data; aborting', file=sys.stderr)
            sys.exit(1)
        # derive symbols from feeder prices map
        prices = feeder.get('prices') or feeder.get('depths') or {}
        symbols = list(prices.keys())
    if not symbols:
        print('No symbols found in feeder', file=sys.stderr)
        sys.exit(1)
    # exclude major caps (common large-cap bases) to focus on smaller hotcoins
    majors = set(['BTC', 'ETH', 'BNB', 'USDC', 'USDT'])
    def base_of(sym: str):
        # try to strip common quote suffixes
        for q in ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'USD']:
            if sym.endswith(q):
                return sym[: -len(q)]
        return sym

    # Ensure we have a feeder snapshot for depths (used as volume metric for sorting).
    # If `feeder` wasn't created earlier (we populated symbols from /api/hotcoins),
    # try to fetch a feeder snapshot now. If that fails, use an empty map.
    try:
        _feeder = locals().get('feeder', None)
        if _feeder is None:
            _feeder = fetch_binance_feeder()
        depths_map = _feeder.get('depths') if isinstance(_feeder, dict) and _feeder is not None else {}
        if depths_map is None:
            depths_map = {}
    except Exception:
        depths_map = {}
    candidates = []
    for s in symbols:
        try:
            b = base_of(s).upper()
            if not b:
                continue
            if b in majors:
                continue
            depth_val = depths_map.get(s, 0) if isinstance(depths_map, dict) else 0
            try:
                dv = float(depth_val) if depth_val is not None else 0.0
            except Exception:
                dv = 0.0
            candidates.append((s, dv))
        except Exception:
            continue

    if not candidates:
        print('No non-major symbols found after filtering; aborting', file=sys.stderr)
        sys.exit(1)

    # sort by depth (volume-like) descending and take top 20
    candidates.sort(key=lambda x: x[1], reverse=True)
    top = [s for s, _ in candidates[:20]]
    results_1h = []
    results_4h = []
    combined = []
    for s in top:
        # Binance symbols in feeder are like 'ABCUSDT' already
        klines_1h = fetch_klines(s, interval='1m', limit=60)
        klines_4h = fetch_klines(s, interval='1m', limit=240)

        if not klines_1h:
            results_1h.append({'symbol': s, 'error': 'no_klines'})
        else:
            info1 = analyze_from_1m_klines_for_period(klines_1h)
            if not info1:
                results_1h.append({'symbol': s, 'error': 'insufficient'})
            else:
                MIN_QV_1H = 1000.0
                trend1 = classify(info1, min_quote_vol=MIN_QV_1H)
                results_1h.append({'symbol': s, 'trend': trend1, 'analysis': info1})

        if not klines_4h:
            results_4h.append({'symbol': s, 'error': 'no_klines'})
        else:
            info4 = analyze_from_1m_klines_for_period(klines_4h)
            if not info4:
                results_4h.append({'symbol': s, 'error': 'insufficient'})
            else:
                # For 4h signals we can require a slightly higher volume threshold
                MIN_QV_4H = 4000.0
                trend4 = classify(info4, min_quote_vol=MIN_QV_4H)
                results_4h.append({'symbol': s, 'trend': trend4, 'analysis': info4})

        # build combined entry (prefer analysis objects if present)
        combined.append({
            'symbol': s,
            '1h': results_1h[-1] if results_1h else {'symbol': s, 'error': 'missing'},
            '4h': results_4h[-1] if results_4h else {'symbol': s, 'error': 'missing'},
        })

    # print a readable table for 1h (summary)
    print('\n1-hour trend analysis for top 20 hotcoins (based on feeder order):\n')
    print(f"{'SYMBOL':<12} {'TREND':<12} {'%chg(1h)':>10} {'last':>12} {'sma30':>12}")
    print('-'*64)
    for r in results_1h:
        if r.get('error'):
            print(f"{r['symbol']:<12} {'ERR':<12} {'-':>10} {'-':>12} {'-':>12}")
            continue
        a = r['analysis']
        print(f"{r['symbol']:<12} {r['trend']:<12} {a['pct_change']:10.3f}% {a['last']:12.6f} {a['sma30']:12.6f}")

    # print a readable table for 4h (summary)
    print('\n4-hour trend analysis for top 20 hotcoins (based on feeder order):\n')
    print(f"{'SYMBOL':<12} {'TREND':<12} {'%chg(4h)':>10} {'last':>12} {'sma(120)':>12}")
    print('-'*64)
    for r in results_4h:
        if r.get('error'):
            print(f"{r['symbol']:<12} {'ERR':<12} {'-':>10} {'-':>12} {'-':>12}")
            continue
        a = r['analysis']
        print(f"{r['symbol']:<12} {r['trend']:<12} {a['pct_change']:10.3f}% {a['last']:12.6f} {a['sma30']:12.6f}")

    # Also print JSON summary (combined)
    print('\nJSON combined summary:\n')
    print(json.dumps(combined, indent=2))

    # persist to var/hotcoins_1h_analysis.json, hotcoins_4h_analysis.json and combined
    try:
        import os
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        outdir = os.path.join(root, 'var')
        os.makedirs(outdir, exist_ok=True)
        outpath1 = os.path.join(outdir, 'hotcoins_1h_analysis.json')
        outpath4 = os.path.join(outdir, 'hotcoins_4h_analysis.json')
        outpath_comb = os.path.join(outdir, 'hotcoins_combined_analysis.json')
        with open(outpath1, 'w', encoding='utf-8') as fh:
            json.dump(results_1h, fh, indent=2)
        with open(outpath4, 'w', encoding='utf-8') as fh:
            json.dump(results_4h, fh, indent=2)
        with open(outpath_comb, 'w', encoding='utf-8') as fh:
            json.dump(combined, fh, indent=2)
        print(f"\nSaved 1h analysis to {outpath1}")
        print(f"Saved 4h analysis to {outpath4}")
        print(f"Saved combined analysis to {outpath_comb}")
    except Exception as e:
        print(f"Failed to save analysis: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
