"""Run a flexible grid search over QuickScalpStrategy and executor params.

Usage:
    python tools/grid_backtest_myx.py [--limit 1000] [--conservative] [--htf 0.005 0.01] [--mom-w 3 6]

Produces `var/myx_grid_results.json` with results for each parameter combo.
"""
import argparse
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from arbitrage.strategy import QuickScalpStrategy
from arbitrage.executor import DryRunExecutor

API = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "MYXUSDT"
INTERVAL = "1m"
LIMIT = 1000


def fetch_klines(symbol=SYMBOL, interval=INTERVAL, limit=LIMIT):
    q = {"symbol": symbol, "interval": interval, "limit": str(limit)}
    url = API + "?" + urlencode(q)
    req = Request(url, headers={"User-Agent": "arbitrage-grid-backtest/1.0"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def klines_to_rows(klines):
    rows = []
    for k in klines:
        ts = k[0]
        close = float(k[4])
        rows.append((ts, close, None))
    return rows


def run_backtest(rows, momentum_window, htf_momentum_threshold, risk_per_trade=5.0, k_stop=1.25, k_target=2.0, conservative=False):
    # Build strategy with either conservative (production-like) or relaxed debug sizing
    if conservative:
        strat = QuickScalpStrategy(
            notional_per_trade=50.0,
            max_notional=200.0,
            min_notional=25.0,
            round_to=0.1,
            momentum_window=momentum_window,
        )
    else:
        strat = QuickScalpStrategy(
            notional_per_trade=200.0,
            max_notional=1000.0,
            min_notional=1.0,
            round_to=0.0001,
            momentum_window=momentum_window,
        )
    strat.risk_per_trade = risk_per_trade
    strat.k_stop = k_stop
    strat.k_target = k_target
    strat.htf_momentum_threshold = htf_momentum_threshold
    strat.pivot_prominence_pct = 0.01
    strat.pivot_min_distance = 8

    if conservative:
        execer = DryRunExecutor(entry_fee_rate=0.0004, exit_fee_rate=0.0004, min_notional=25.0, round_to=0.1, slippage_bps=0.001, max_partial_reduces=3)
    else:
        execer = DryRunExecutor(entry_fee_rate=0.0004, exit_fee_rate=0.0004, min_notional=1.0, round_to=0.0001, slippage_bps=0.001, max_partial_reduces=3)

    recent = []
    bars_held = 0

    for ts, close, fr in rows:
        recent.append(close)
        position = execer.get_active().get("MYX/USDT")
        decision = strat.decide(close, recent, fr, position=position, bars_held=bars_held)

        if decision.action == "enter":
            try:
                atr = strat.compute_atr_like(recent)
            except Exception:
                atr = None
            try:
                size = strat.size_by_risk(close, atr, decision.direction)
            except Exception:
                size = None
            if size is None:
                # skip
                bars_held = bars_held + (1 if position is not None else 0)
                continue
            decision.size = size
            evt = execer.step("MYX/USDT", close, decision)
            bars_held = 0
        elif decision.action in ("exit", "reduce"):
            execer.step("MYX/USDT", close, decision)
            if decision.action == "exit":
                bars_held = 0
        else:
            if position is not None:
                bars_held += 1

    # final liquidation
    last_price = rows[-1][1]
    execer.liquidate_all({"MYX/USDT": last_price})

    total_pnl = sum(p.pnl for p in execer.closed)
    return {"closed_trades": len(execer.closed), "total_pnl": total_pnl, "closed": [ {"direction": p.direction, "entry_price": p.entry_price, "exit_price": p.exit_price, "pnl": p.pnl} for p in execer.closed ]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=LIMIT)
    p.add_argument("--htf", nargs="*", type=float, default=[0.005, 0.01, 0.02, 0.03])
    p.add_argument("--mom-w", nargs="*", type=int, default=[3, 6, 12])
    p.add_argument("--risk", type=float, default=5.0)
    p.add_argument("--k-stop", type=float, default=1.25)
    p.add_argument("--k-target", type=float, default=2.0)
    p.add_argument("--conservative", action="store_true", help="Use conservative/production-like sizing and executor settings")
    args = p.parse_args()

    kl = fetch_klines(limit=args.limit)
    rows = klines_to_rows(kl)

    results = []
    for htf in args.htf:
        for mw in args.mom_w:
            print(f"Running grid htf_momentum_threshold={htf}, momentum_window={mw}, risk={args.risk}, conservative={args.conservative}")
            res = run_backtest(rows, momentum_window=mw, htf_momentum_threshold=htf, risk_per_trade=args.risk, k_stop=args.k_stop, k_target=args.k_target, conservative=args.conservative)
            entry = {"htf_momentum_threshold": htf, "momentum_window": mw, "risk_per_trade": args.risk, "k_stop": args.k_stop, "k_target": args.k_target, "conservative": args.conservative, **res}
            results.append(entry)

    # write JSON summary
    with open("var/myx_grid_results.json", "w", encoding="utf8") as f:
        json.dump({"symbol": "MYX/USDT", "limit": len(rows), "results": results}, f, indent=2)

    # print concise table
    print("\nGrid results:")
    for r in results:
        print(f"htf={r['htf_momentum_threshold']}, mom_w={r['momentum_window']} -> closed={r['closed_trades']}, pnl={r['total_pnl']:.4f}")


if __name__ == '__main__':
    main()
"""Run a small grid search over QuickScalpStrategy HTF/short-term momentum params.

Usage:
    python tools/grid_backtest_myx.py

Produces `var/myx_grid_results.json` with results for each parameter combo.
"""
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from arbitrage.strategy import QuickScalpStrategy
from arbitrage.executor import DryRunExecutor

API = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "MYXUSDT"
INTERVAL = "1m"
LIMIT = 1000


def fetch_klines(symbol=SYMBOL, interval=INTERVAL, limit=LIMIT):
    q = {"symbol": symbol, "interval": interval, "limit": str(limit)}
    url = API + "?" + urlencode(q)
    req = Request(url, headers={"User-Agent": "arbitrage-grid-backtest/1.0"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def klines_to_rows(klines):
    rows = []
    for k in klines:
        ts = k[0]
        close = float(k[4])
        rows.append((ts, close, None))
    return rows


def run_backtest(rows, momentum_window, htf_momentum_threshold):
    # mirror the strategy/executor settings used in the interactive runs
    strat = QuickScalpStrategy(
        notional_per_trade=200.0,
        max_notional=1000.0,
        min_notional=1.0,
        round_to=0.0001,
        momentum_window=momentum_window,
    )
    strat.risk_per_trade = 5.0
    strat.k_stop = 1.25
    strat.k_target = 2.0
    strat.htf_momentum_threshold = htf_momentum_threshold
    strat.pivot_prominence_pct = 0.01
    strat.pivot_min_distance = 8

    execer = DryRunExecutor(entry_fee_rate=0.0004, exit_fee_rate=0.0004, min_notional=1.0, round_to=0.0001, slippage_bps=0.001, max_partial_reduces=3)

    recent = []
    bars_held = 0

    for ts, close, fr in rows:
        recent.append(close)
        position = execer.get_active().get("MYX/USDT")
        decision = strat.decide(close, recent, fr, position=position, bars_held=bars_held)

        if decision.action == "enter":
            try:
                atr = strat.compute_atr_like(recent)
            except Exception:
                atr = None
            try:
                size = strat.size_by_risk(close, atr, decision.direction)
            except Exception:
                size = None
            if size is None:
                # skip
                bars_held = bars_held + (1 if position is not None else 0)
                continue
            decision.size = size
            evt = execer.step("MYX/USDT", close, decision)
            bars_held = 0
        elif decision.action in ("exit", "reduce"):
            execer.step("MYX/USDT", close, decision)
            if decision.action == "exit":
                bars_held = 0
        else:
            if position is not None:
                bars_held += 1

    # final liquidation
    last_price = rows[-1][1]
    execer.liquidate_all({"MYX/USDT": last_price})

    total_pnl = sum(p.pnl for p in execer.closed)
    return {"closed_trades": len(execer.closed), "total_pnl": total_pnl, "closed": [ {"direction": p.direction, "entry_price": p.entry_price, "exit_price": p.exit_price, "pnl": p.pnl} for p in execer.closed ]}


def main():
    kl = fetch_klines()
    rows = klines_to_rows(kl)

    # grid: htf_momentum_threshold x momentum_window
    htf_vals = [0.005, 0.01, 0.02, 0.03]
    mom_windows = [3, 6, 12]

    results = []
    for htf in htf_vals:
        for mw in mom_windows:
            print(f"Running grid htf_momentum_threshold={htf}, momentum_window={mw}")
            res = run_backtest(rows, momentum_window=mw, htf_momentum_threshold=htf)
            entry = {"htf_momentum_threshold": htf, "momentum_window": mw, **res}
            results.append(entry)

    # write JSON summary
    with open("var/myx_grid_results.json", "w", encoding="utf8") as f:
        json.dump({"symbol": "MYX/USDT", "limit": len(rows), "results": results}, f, indent=2)

    # print concise table
    print("\nGrid results:")
    for r in results:
        print(f"htf={r['htf_momentum_threshold']}, mom_w={r['momentum_window']} -> closed={r['closed_trades']}, pnl={r['total_pnl']:.4f}")


if __name__ == '__main__':
    main()
