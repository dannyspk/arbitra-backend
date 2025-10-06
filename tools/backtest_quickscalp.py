"""Small backtest harness for QuickScalpStrategy using DryRunExecutor.

Usage:
    python tools/backtest_quickscalp.py <csv_file>

CSV format expected: timestamp,close,funding_rate (funding_rate optional)

The script runs a simple bar-by-bar loop, feeding closes to the strategy and applying decisions to the executor.
"""
import csv
import sys
from typing import List, Optional
from pathlib import Path
from src.arbitrage.strategy import QuickScalpStrategy
from src.arbitrage.executor import DryRunExecutor


def load_csv(path: str):
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        for row in r:
            if not row:
                continue
            ts = row[0]
            close = float(row[1])
            fr = float(row[2]) if len(row) > 2 and row[2] != "" else None
            rows.append((ts, close, fr))
    return rows


def run_backtest(rows, symbol: str = "BTC/USDT"):
    strat = QuickScalpStrategy()
    execer = DryRunExecutor()

    recent = []
    bars_held = 0
    for ts, close, fr in rows:
        recent.append(close)
        # Provide current position and bars_held
        position = execer.get_active().get(symbol)
        decision = strat.decide(close, recent, fr, position=position, bars_held=bars_held)
        if decision.action == "enter":
            execer.step(symbol, close, decision)
            bars_held = 0
        elif decision.action == "reduce":
            execer.step(symbol, close, decision)
            # do not reset bars_held on partial close
        elif decision.action == "exit":
            execer.step(symbol, close, decision)
            bars_held = 0
        else:
            # hold
            if position is not None:
                bars_held += 1

    # Liquidate at last price
    last_price = rows[-1][1]
    execer.liquidate_all({symbol: last_price})

    total_pnl = sum(p.pnl for p in execer.closed)
    print(f"Closed trades: {len(execer.closed)}, total_pnl={total_pnl:.4f}")
    for p in execer.closed:
        print(p)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/backtest_quickscalp.py <data.csv>")
        sys.exit(1)
    rows = load_csv(sys.argv[1])
    run_backtest(rows)
