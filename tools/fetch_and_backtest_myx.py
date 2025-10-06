"""Fetch recent 1m klines for MYXUSDT from Binance Futures and run the QuickScalp backtest.

Usage:
    python tools/fetch_and_backtest_myx.py

This script uses only the Python standard library (urllib) so it works without extra deps.
"""
import json
import sys
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from time import sleep

from arbitrage.strategy import QuickScalpStrategy
from arbitrage.executor import DryRunExecutor


API = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "MYXUSDT"
INTERVAL = "1m"
LIMIT = 240  # last 4 hours


def fetch_klines(symbol=SYMBOL, interval=INTERVAL, limit=LIMIT):
    q = {"symbol": symbol, "interval": interval, "limit": str(limit)}
    url = API + "?" + urlencode(q)
    req = Request(url, headers={"User-Agent": "arbitrage-backtest/1.0"})
    try:
        with urlopen(req, timeout=20) as r:
            data = r.read()
            return json.loads(data)
    except Exception as e:
        print(f"Error fetching klines: {e}")
        return None


def klines_to_rows(klines):
    # kline format: [open_time, open, high, low, close, ...]
    rows = []
    for k in klines:
        ts = k[0]
        close = float(k[4])
        # funding not available here; set None
        rows.append((ts, close, None))
    return rows


def run_local_backtest(rows, symbol_name="MYX/USDT"):
    # Use risk-based sizing and ATR stops/targets
    strat = QuickScalpStrategy(
        notional_per_trade=50.0,
        max_notional=200.0,
        min_notional=25.0,
        round_to=0.1,
    )
    # tighten pivot/prominence and ATR multipliers
    strat.pivot_prominence_pct = 0.01
    strat.pivot_min_distance = 8
    strat.k_stop = 1.25
    strat.k_target = 2.0
    # safer conservative defaults
    strat.risk_per_trade = 10.0
    strat.max_notional = 50.0

    # Executor params (production-like conservative defaults)
    execer = DryRunExecutor(entry_fee_rate=0.0004, exit_fee_rate=0.0004, min_notional=25.0, round_to=0.1, slippage_bps=0.001, max_partial_reduces=3)

    recent = []
    bars_held = 0
    ledger = []  # per-bar ledger entries
    for ts, close, fr in rows:
        recent.append(close)
        position = execer.get_active().get(symbol_name)
        decision = strat.decide(close, recent, fr, position=position, bars_held=bars_held)
        # record base ledger entry
        entry = {"ts": ts, "price": close, "funding": fr, "position": None, "decision": getattr(decision, 'action', None), "reason": getattr(decision, 'reason', None)}
        print(f"bar ts={ts} price={close:.6f} decision={decision.action} reason={decision.reason}")
        if decision.action == "enter":
            # compute ATR if strategy exposes it via compute_atr_like
            try:
                atr = strat.compute_atr_like(recent)
            except Exception:
                atr = None
            # prefer risk-based size when ATR available
            try:
                size = strat.size_by_risk(close, atr, decision.direction)
            except Exception:
                size = None

            if size is None:
                # skip this entry due to sizing constraints (too small/large or missing ATR)
                print(f"  -> skip entry due to sizing constraints (atr={atr}, desired_size=None)")
                entry["decision"] = "hold"
                entry["reason"] = (entry.get("reason") or "") + ",skipped_by_size"
                ledger.append(entry)
                continue

            # attach size into decision
            decision.size = size
            # attach stop/target info for logging
            stop = None
            target = None
            if atr is not None:
                stop = close - strat.k_stop * atr * close if decision.direction == 'long' else close + strat.k_stop * atr * close
                target = close + strat.k_target * atr * close if decision.direction == 'long' else close - strat.k_target * atr * close
                decision.reason = (decision.reason or "") + f",stop={stop:.6f},target={target:.6f},atr={atr:.6f},size={size:.2f}"

            evt = execer.step(symbol_name, close, decision)
            print("  -> entered", evt)
            entry["position"] = repr(evt.get("position") if isinstance(evt, dict) else None)
            ledger.append(entry)
            bars_held = 0
        elif decision.action == "reduce":
            evt = execer.step(symbol_name, close, decision)
            print("  -> reduced", evt)
            entry["position"] = repr(evt.get("remaining") if isinstance(evt, dict) else None)
            entry["reduce_evt"] = evt
            ledger.append(entry)
        elif decision.action == "exit":
            evt = execer.step(symbol_name, close, decision)
            print("  -> exited", evt)
            entry["position"] = repr(evt.get("position") if isinstance(evt, dict) else None)
            ledger.append(entry)
            bars_held = 0
        else:
            entry["position"] = repr(position)
            ledger.append(entry)
            if position is not None:
                bars_held += 1

    # Liquidate
    last_price = rows[-1][1]
    execer.liquidate_all({symbol_name: last_price})

    # Liquidate
    last_price = rows[-1][1]
    execer.liquidate_all({symbol_name: last_price})

    total_pnl = sum(p.pnl for p in execer.closed)
    print(f"\nBacktest complete: Closed trades: {len(execer.closed)}, total_pnl={total_pnl:.4f}")
    for p in execer.closed:
        print(p)

    # persist ledger and closed trades for later analysis
    out = {
        "symbol": symbol_name,
        "closed_trades": [
            {
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "size": p.size,
                "qty": p.qty,
                "pnl": p.pnl,
                "entry_time": p.entry_time,
                "exit_time": p.exit_time,
            }
            for p in execer.closed
        ],
        "total_pnl": total_pnl,
        "ledger_length": len(ledger),
    }
    # serialize ledger to JSON-friendly objects (repr for complex objects)
    serial_ledger = []
    for r in ledger:
        sr = {"ts": r.get("ts"), "price": r.get("price"), "funding": r.get("funding"), "decision": r.get("decision"), "reason": r.get("reason")}
        # position may already be a repr string; keep as-is
        sr["position"] = r.get("position")
        # serialize any event object attached
        if "reduce_evt" in r:
            evt = r.get("reduce_evt")
            se = {}
            for k, v in (evt.items() if isinstance(evt, dict) else []):
                if v is None or isinstance(v, (str, bool, int, float)):
                    se[k] = v
                else:
                    try:
                        # try to use dict-like access
                        se[k] = dict(v.__dict__)
                    except Exception:
                        se[k] = repr(v)
            sr["reduce_evt"] = se
        serial_ledger.append(sr)

    # write JSON
    with open("var/myx_backtest_report.json", "w", encoding="utf8") as f:
        json.dump({**out, "ledger": serial_ledger}, f, indent=2)
    # write CSV ledger (simple flat rows)
    try:
        import csv

        with open("var/myx_backtest_ledger.csv", "w", newline="", encoding="utf8") as cf:
            writer = csv.DictWriter(cf, fieldnames=["ts", "price", "funding", "decision", "reason", "position"])
            writer.writeheader()
            for r in ledger:
                writer.writerow({k: r.get(k) for k in writer.fieldnames})
    except Exception:
        # best-effort; not critical
        pass


if __name__ == "__main__":
    kl = fetch_klines()
    if kl is None:
        print("Failed to fetch klines for", SYMBOL)
        sys.exit(2)
    if len(kl) == 0:
        print("No klines returned for", SYMBOL)
        sys.exit(2)
    rows = klines_to_rows(kl)
    run_local_backtest(rows, symbol_name="MYX/USDT")
