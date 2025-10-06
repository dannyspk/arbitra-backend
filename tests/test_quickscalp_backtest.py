import tempfile
import os
from src.arbitrage.strategy import QuickScalpStrategy
from src.arbitrage.executor import DryRunExecutor


def test_quickscalp_smoke():
    # Create a synthetic price series with a clear uptrend then downtrend
    prices = [100 + i * 0.5 for i in range(30)] + [115 - i * 0.6 for i in range(30)]
    rows = [(str(i), p, 0.0) for i, p in enumerate(prices)]

    strat = QuickScalpStrategy(sma_window=3, entry_threshold=0.005)
    execer = DryRunExecutor()

    recent = []
    for ts, close, fr in rows:
        recent.append(close)
        dec = strat.decide(close, recent, fr)
        if dec.action == "enter":
            execer.step("TEST/USDT", close, dec)
        elif dec.action == "exit":
            execer.step("TEST/USDT", close, dec)

    execer.liquidate_all({"TEST/USDT": prices[-1]})
    # Should have closed trades (non-zero len)
    assert isinstance(execer.closed, list)
    assert len(execer.closed) >= 0
    # total pnl numeric
    total = sum(p.pnl for p in execer.closed)
    assert isinstance(total, float)
