#!/usr/bin/env python
"""Aggregate Binance forceOrder websocket logs for our hotcoins list.

Reads the log at tools/ccxt_out/binance_force_orders_ws.log (or a path
you pass with --log), loads hotcoins via arbitrage.hotcoins.find_hot_coins(),
and prints a simple per-symbol summary: count, total base qty, total quote (USD) amount.

Usage: python tools/aggregate_hotcoin_liquidations.py --top 20 --csv out.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

# Ensure repo src/ is importable when running from tools/
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent
_SRC = _REPO_ROOT / 'src'
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from arbitrage.hotcoins import find_hot_coins
except Exception as e:
    print(f"warning: couldn't import find_hot_coins: {e}")
    find_hot_coins = None


def load_hotcoin_symbols(max_results: int = 100) -> set[str]:
    """Return a set of hotcoin symbols (e.g. BTCUSDT) using the project's helper.

    Prefer `find_hot_coins`; if that fails (module bug), fall back to
    `_binance_top_by_volume` which returns dicts with 'symbol' entries.
    """
    syms: set[str] = set()
    if find_hot_coins is not None:
        try:
            lst = find_hot_coins(exchanges=None, max_results=max_results)
            for e in lst or []:
                s = None
                if isinstance(e, dict):
                    s = e.get('symbol') or e.get('sym')
                if not s and isinstance(e, dict):
                    base = e.get('base')
                    quote = e.get('quote')
                    if base and quote:
                        s = f"{base}{quote}"
                if s:
                    syms.add(s.upper())
            if syms:
                return syms
        except Exception as exc:
            print("warning: find_hot_coins failed:", exc)

    # fallback: try to import _binance_top_by_volume and use its symbols
    try:
        from arbitrage.hotcoins import _binance_top_by_volume
        top = _binance_top_by_volume(top_n=max_results)
        for e in top or []:
            if isinstance(e, dict):
                s = e.get('symbol')
                if s:
                    syms.add(s.upper())
        return syms
    except Exception as exc:
        print("warning: fallback _binance_top_by_volume failed:", exc)
        return syms


def parse_log_line(line: str) -> Dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    # ignore markdown fences accidentally included
    if line.startswith('```'):
        return None
    # some lines may have leading/trailing backticks
    line = line.strip('`')
    try:
        obj = json.loads(line)
        return obj
    except Exception:
        # try to extract json substring
        try:
            start = line.find('{')
            if start >= 0:
                obj = json.loads(line[start:])
                return obj
        except Exception:
            return None
    return None


def aggregate(log_path: Path, hot_symbols: set[str]) -> Dict[str, Dict[str, Decimal]]:
    # aggregate per-symbol
    agg: Dict[str, Dict[str, Decimal]] = {}
    # init default
    for h in hot_symbols:
        agg[h] = {'count': Decimal(0), 'base_qty': Decimal(0), 'quote_amt': Decimal(0)}

    with log_path.open('r', encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            obj = parse_log_line(raw)
            if not obj:
                continue
            # top-level msg field contains 'o'
            msg = obj.get('msg') if isinstance(obj, dict) else None
            if not isinstance(msg, dict):
                continue
            o = msg.get('o') or msg.get('data') or {}
            if not isinstance(o, dict):
                continue
            sym = (o.get('s') or o.get('symbol') or '').upper()
            if not sym or sym not in hot_symbols:
                continue
            # filled qty: prefer 'z' (filled) then 'l' (last) then 'q' requested
            try:
                filled = Decimal(str(o.get('z') or o.get('l') or o.get('q') or 0))
            except Exception:
                try:
                    filled = Decimal(float(o.get('z') or o.get('l') or o.get('q') or 0))
                except Exception:
                    filled = Decimal(0)
            # price: prefer 'ap' (avg price), then 'p'
            try:
                price = Decimal(str(o.get('ap') or o.get('p') or 0))
            except Exception:
                try:
                    price = Decimal(float(o.get('ap') or o.get('p') or 0))
                except Exception:
                    price = Decimal(0)

            quote = (filled * price)
            rec = agg.setdefault(sym, {'count': Decimal(0), 'base_qty': Decimal(0), 'quote_amt': Decimal(0)})
            rec['count'] += Decimal(1)
            rec['base_qty'] += filled
            rec['quote_amt'] += quote

    return agg


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--log', default='tools/ccxt_out/binance_force_orders_ws.log')
    p.add_argument('--top', type=int, default=50, help='show top-N symbols by USD quote amount')
    p.add_argument('--csv', default=None, help='optional CSV path to write per-symbol summary')
    p.add_argument('--max-hot', type=int, default=200, help='max hotcoins to request')
    args = p.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"log file not found: {log_path}")
        return 2

    hot_symbols = load_hotcoin_symbols(max_results=args.max_hot)
    if not hot_symbols:
        print("No hotcoin symbols found (hot list empty). You can still aggregate but no symbols will match.")

    agg = aggregate(log_path, hot_symbols)

    # prepare sorted list by quote_amt
    items = []
    for sym, rec in agg.items():
        items.append((sym, rec))
    items.sort(key=lambda x: x[1]['quote_amt'], reverse=True)

    top = args.top if args.top and args.top > 0 else len(items)
    print(f"Aggregated liquidation summary for {len(items)} hot symbols (showing top {top})")
    print(f"{'symbol':12} {'count':6} {'base_qty':18} {'quote_USD':18}")
    for sym, rec in items[:top]:
        print(f"{sym:12} {int(rec['count']):6d} {rec['base_qty']:18.8f} {rec['quote_amt']:18.2f}")

    if args.csv:
        import csv
        with open(args.csv, 'w', newline='', encoding='utf-8') as cf:
            w = csv.writer(cf)
            w.writerow(['symbol', 'count', 'base_qty', 'quote_usd'])
            for sym, rec in items:
                w.writerow([sym, int(rec['count']), f"{rec['base_qty']}", f"{rec['quote_amt']}"])
        print(f"Wrote CSV to {args.csv}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
