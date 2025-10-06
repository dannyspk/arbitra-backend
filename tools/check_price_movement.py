#!/usr/bin/env python3
"""
Check price movement for a symbol over the last N minutes (default 30m).
Prints a concise summary. If --notify-http is provided the script POSTs a small JSON
alert to the given URL when the absolute percent move >= threshold.

Example:
  python tools/check_price_movement.py XPLUSDT --minutes 30 --threshold 5 \
    --notify-http http://127.0.0.1:8000/api/alerts
"""
from __future__ import annotations
import sys
import json
import argparse
from urllib import request, parse
import time
from typing import Optional, List
from datetime import datetime


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
BINANCE_FUTURES_24H_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"

# default list of major cap USDT futures symbols to exclude from batch checks
MAJOR_CAP_USDT = {
    'BTCUSDT','ETHUSDT','BNBUSDT','XRPUSDT','ADAUSDT','SOLUSDT',
    'DOGEUSDT','MATICUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','TRXUSDT'
}


def _http_get_json(url: str, timeout: float = 10.0) -> Optional[object]:
    try:
        req = request.Request(url, headers={"User-Agent": "arb-check/1.0"})
        with request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"HTTP GET error: {e}", file=sys.stderr)
        return None


def fetch_klines(symbol: str, interval: str = "1m", limit: int = 100, startTime: Optional[int] = None, endTime: Optional[int] = None, market: str = "spot") -> List[List]:
    base = BINANCE_KLINES_URL if market == "spot" else BINANCE_FUTURES_KLINES_URL
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if startTime is not None:
        params["startTime"] = int(startTime)
    if endTime is not None:
        params["endTime"] = int(endTime)
    q = parse.urlencode(params)
    url = f"{base}?{q}"
    data = _http_get_json(url)
    if not isinstance(data, list):
        return []
    return data


def closes_from_klines(klines: List[List]) -> List[float]:
    out: List[float] = []
    for k in klines:
        try:
            # close price is index 4
            out.append(float(k[4]))
        except Exception:
            continue
    return out


def percent_change(old: float, new: float) -> Optional[float]:
    try:
        if old == 0:
            return None
        return (new - old) / old * 100.0
    except Exception:
        return None


def notify_http(url: str, payload: dict) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "arb-check/1.0"})
        with request.urlopen(req, timeout=10) as r:
            return 200 <= r.getcode() < 300
    except Exception as e:
        print(f"notify_http error: {e}", file=sys.stderr)
        return False


def fetch_ticker_price(symbol: str, market: str = "spot") -> Optional[float]:
    base = BINANCE_TICKER_URL if market == "spot" else BINANCE_FUTURES_TICKER_URL
    q = parse.urlencode({"symbol": symbol})
    url = f"{base}?{q}"
    data = _http_get_json(url)
    if not isinstance(data, dict):
        return None
    try:
        return float(data.get("price"))
    except Exception:
        return None


def fetch_top_futures_symbols(top_n: int = 30, usdt_only: bool = True, exclude_majors: bool = True) -> List[str]:
    """Fetch 24h ticker data for futures and return the top_n symbols by quoteVolume (or volume).

    Returns a list of symbol strings sorted descending by volume.
    """
    data = _http_get_json(BINANCE_FUTURES_24H_URL)
    if not isinstance(data, list):
        return []
    def vol_of(item: dict) -> float:
        try:
            return float(item.get('quoteVolume') or item.get('volume') or 0.0)
        except Exception:
            return 0.0
    data_sorted = sorted(data, key=vol_of, reverse=True)
    symbols: List[str] = []
    for item in data_sorted:
        s = item.get('symbol')
        if not s:
            continue
        if usdt_only and not s.endswith('USDT'):
            continue
        if exclude_majors and s in MAJOR_CAP_USDT:
            continue
        symbols.append(s)
        if len(symbols) >= top_n:
            break
    return symbols


def check_one_symbol(symbol: str, args) -> int:
    """Core check logic for a single symbol. Returns 0 on success, non-zero error codes preserved from original main."""
    # compute how many klines needed (interval in minutes assumed '1m', '3m', '5m', '15m', etc.)
    try:
        if args.interval.endswith('m'):
            mins = int(args.interval.rstrip('m'))
        elif args.interval.endswith('h'):
            mins = int(args.interval.rstrip('h')) * 60
        else:
            mins = 1
    except Exception:
        mins = 1
    needed = max(2, (args.minutes // max(1, mins)) + 1)

    klines = fetch_klines(symbol, interval=args.interval, limit=needed, market=args.market)
    if args.debug:
        try:
            print(f"DEBUG: needed={needed} fetched={len(klines)}", file=sys.stderr)
            if len(klines) >= 1:
                first_k = klines[0]
                last_k = klines[-1]
                ft = datetime.utcfromtimestamp(int(first_k[0]) / 1000).isoformat() + 'Z'
                lt = datetime.utcfromtimestamp(int(last_k[0]) / 1000).isoformat() + 'Z'
                print(f"DEBUG first_open={first_k[0]} ({ft}) close={first_k[4]}", file=sys.stderr)
                print(f"DEBUG last_open={last_k[0]} ({lt}) close={last_k[4]}", file=sys.stderr)
        except Exception as e:
            print(f"DEBUG init print error: {e}", file=sys.stderr)
    if not klines:
        print(f"ERROR: no klines fetched for {symbol}", file=sys.stderr)
        return 2

    closes = closes_from_klines(klines)
    # If the exchange returned fewer candles than requested, try again with a startTime
    if len(closes) < needed:
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (args.minutes * 60 * 1000)
        klines2 = fetch_klines(symbol, interval=args.interval, limit=needed, startTime=start_ms, market=args.market)
        if klines2:
            closes = closes_from_klines(klines2)
        # if still short, continue with what we have but warn
        if len(closes) < 2:
            print(f"ERROR: insufficient close prices for {symbol} after retry (have {len(closes)}, need >=2)", file=sys.stderr)
            return 3
        if len(closes) < needed:
            print(f"WARNING: requested {needed} candles but only received {len(closes)}; results will represent available window", file=sys.stderr)
        if args.debug:
            try:
                print("DEBUG: start_ms:", start_ms, file=sys.stderr)
                # show openTime and close for each returned kline (if klines2 used prefer that)
                to_show = klines2 if klines2 else klines
                for k in to_show[:5]:
                    print("DEBUG k0:", k[0], "close:", k[4], file=sys.stderr)
                if len(to_show) > 5:
                    for k in to_show[-5:]:
                        print("DEBUG kN:", k[0], "close:", k[4], file=sys.stderr)
            except Exception as e:
                print(f"DEBUG error: {e}", file=sys.stderr)

    # If we have more closes than needed, keep the most recent 'needed' entries
    if len(closes) > needed:
        closes = closes[-needed:]
    if len(closes) < 2:
        print(f"ERROR: insufficient close prices for {symbol}", file=sys.stderr)
        return 3

    first = closes[0]
    last = closes[-1]
    pct = percent_change(first, last)
    if pct is None:
        print("ERROR: cannot compute percent change (first price 0)", file=sys.stderr)
        return 4

    out = {
        "symbol": symbol,
        "first_close": first,
        "last_close": last,
        "percent_change": round(pct, 4),
        "minutes": args.minutes,
    }
    # also fetch current ticker price and report percent change vs live price
    ticker_price = fetch_ticker_price(symbol, market=args.market)
    if ticker_price is not None:
        pct_ticker = percent_change(first, ticker_price)
        out["ticker_price"] = ticker_price
        out["percent_change_vs_ticker"] = round(pct_ticker, 4) if pct_ticker is not None else None
    if args.debug:
        if ticker_price is not None:
            print(f"DEBUG: ticker_price={ticker_price}", file=sys.stderr)
        else:
            print("DEBUG: ticker_price not available", file=sys.stderr)
    print(json.dumps(out))

    should_alert = args.force_alert or (abs(pct) >= args.threshold)
    if should_alert:
        # prepare payloads
        log_text = f"hot move {symbol} {round(pct,4)}% over {args.minutes}min"
        log_payload = {
            # server /logs endpoint will add ts if missing
            "src": "hotcoins",
            "level": "warning",
            "text": log_text,
            "alerts": [{"symbol": symbol, "percent": round(pct, 4), "minutes": args.minutes}],
            "symbol": symbol,
            "market": args.market if hasattr(args, 'market') else 'spot',
        }

        msg = {
            "type": "hotcoin_price_move",
            "symbol": symbol,
            "percent": round(pct, 4),
            "threshold": args.threshold,
            "first_close": first,
            "last_close": last,
        }

        if args.notify_http:
            if getattr(args, 'notify_as_log', False):
                ok = notify_http(args.notify_http, log_payload)
                print(json.dumps({"notified": ok, "endpoint": args.notify_http, "payload": log_payload}))
            else:
                ok = notify_http(args.notify_http, msg)
                print(json.dumps({"notified": ok, "endpoint": args.notify_http, "payload": msg}))
        else:
            # no notify endpoint provided: print short alert line for server logs capture
            print(json.dumps({"alert": msg}))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("symbol", nargs='?', help="Symbol to check (e.g. XPLUSDT or XPLUSUSDT). Omit if using --all-top-futures")
    p.add_argument("--minutes", type=int, default=30, help="Lookback window in minutes (default 30)")
    p.add_argument("--threshold", type=float, default=5.0, help="Percent threshold to notify (absolute value)")
    p.add_argument("--interval", default="1m", help="Kline interval to request (default 1m)")
    p.add_argument("--notify-http", default=None, help="POST alert JSON to this URL when threshold exceeded")
    p.add_argument("--debug", action="store_true", help="Print debug info about returned klines and timestamps")
    p.add_argument("--notify-as-log", action="store_true", help="When notifying, POST payload in server /logs format (src, text, alerts)")
    p.add_argument("--force-alert", action="store_true", help="Force sending an alert/log regardless of threshold (useful for samples)")
    p.add_argument("--market", choices=["spot", "futures"], default="spot", help="Market to query: spot or futures (default spot)")
    p.add_argument("--all-top-futures", action="store_true", help="Run the check across the top N Binance futures pairs by 24h volume")
    p.add_argument("--top-n", type=int, default=30, help="When using --all-top-futures, number of top futures symbols to check (default 30)")
    p.add_argument("--usdt-only", action="store_true", help="When using --all-top-futures, only include symbols ending with USDT (default: true)")
    p.add_argument("--include-majors", action="store_true", help="When using --all-top-futures, include major-cap symbols (by default majors are excluded)")
    p.add_argument("--daemon", action="store_true", help="Run continuously in a loop (useful for background status).")
    p.add_argument("--run-every", type=float, default=5.0, help="When --daemon=True, wait this many minutes between runs (default 5.0)")
    args = p.parse_args(argv)

    # Batch mode: run against top N futures symbols
    if args.all_top_futures:
        # override market to futures for this mode
        args.market = 'futures'
        symbols = fetch_top_futures_symbols(args.top_n, usdt_only=bool(args.usdt_only), exclude_majors=not bool(args.include_majors))
        if not symbols:
            print("ERROR: could not fetch top futures symbols", file=sys.stderr)
            return 5
        # iterate and check each symbol with a small throttle to avoid hammering Binance
        notified_count = 0
        for s in symbols:
            rc = check_one_symbol(s, args)
            if rc != 0:
                # continue to next symbol on error
                print(f"WARN: check for {s} returned {rc}", file=sys.stderr)
            time.sleep(0.15)
        return 0

    # Daemon/loop mode: if requested, repeatedly run the chosen mode
    if args.daemon:
        try:
            while True:
                if args.all_top_futures:
                    args.market = 'futures'
                    symbols = fetch_top_futures_symbols(args.top_n, usdt_only=bool(args.usdt_only), exclude_majors=not bool(args.include_majors))
                    if not symbols:
                        print("ERROR: could not fetch top futures symbols", file=sys.stderr)
                    else:
                        for s in symbols:
                            rc = check_one_symbol(s, args)
                            if rc != 0:
                                print(f"WARN: check for {s} returned {rc}", file=sys.stderr)
                            time.sleep(0.15)
                else:
                    if not args.symbol:
                        print("ERROR: symbol is required unless --all-top-futures is used", file=sys.stderr)
                        return 1
                    rc = check_one_symbol(args.symbol, args)
                    if rc != 0:
                        print(f"WARN: check for {args.symbol} returned {rc}", file=sys.stderr)
                # sleep between runs
                sleep_minutes = float(args.run_every)
                time.sleep(max(0.1, sleep_minutes * 60.0))
        except KeyboardInterrupt:
            print("daemon interrupted, exiting", file=sys.stderr)
            return 0

    # single-symbol mode: require symbol
    if not args.symbol:
        print("ERROR: symbol is required unless --all-top-futures is used", file=sys.stderr)
        return 1

    return check_one_symbol(args.symbol, args)


if __name__ == "__main__":
    raise SystemExit(main())
