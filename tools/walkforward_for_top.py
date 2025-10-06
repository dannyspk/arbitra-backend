#!/usr/bin/env python3
"""Walk-forward evaluation for top combos in a grid JSON using existing 1000-bar klines.
Usage: python tools/walkforward_for_top.py results.json --top 3

This script fetches 1000 1m klines, then for each selected combo runs the strategy on rolling test windows
and reports aggregated metrics (mean pnl, std, win rate, windows tested).
"""
import json
import sys
import os
import argparse
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from statistics import mean, stdev

from arbitrage.strategy import QuickScalpStrategy
from arbitrage.executor import DryRunExecutor

API = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "MYXUSDT"
INTERVAL = "1m"
LIMIT = 1000


def fetch_klines(symbol=SYMBOL, interval=INTERVAL, limit=LIMIT):
    q = {"symbol": symbol, "interval": interval, "limit": str(limit)}
    url = API + "?" + urlencode(q)
    req = Request(url, headers={"User-Agent": "arbitrage-walkforward/1.0"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def klines_to_rows(klines):
    rows = []
    for k in klines:
        ts = k[0]
        close = float(k[4])
        rows.append((ts, close, None))
    return rows


def run_single_backtest(rows, combo, conservative=True):
    # build strat from combo
    mw = combo.get('momentum_window')
    htf = combo.get('htf_momentum_threshold')
    risk = combo.get('risk_per_trade') or combo.get('risk') or combo.get('risk_per_trade') if combo.get('risk_per_trade') is not None else 2.5

    if conservative:
        strat = QuickScalpStrategy(notional_per_trade=50.0, max_notional=200.0, min_notional=25.0, round_to=0.1, momentum_window=mw)
    else:
        strat = QuickScalpStrategy(notional_per_trade=200.0, max_notional=1000.0, min_notional=1.0, round_to=0.0001, momentum_window=mw)
    strat.risk_per_trade = risk
    strat.k_stop = combo.get('k_stop', 1.25)
    strat.k_target = combo.get('k_target', 2.0)
    strat.htf_momentum_threshold = htf

    execer = DryRunExecutor(entry_fee_rate=0.0004, exit_fee_rate=0.0004, min_notional=25.0 if conservative else 1.0, round_to=0.1 if conservative else 0.0001, slippage_bps=0.001, max_partial_reduces=3)

    recent = []
    bars_held = 0
    for ts, close, fr in rows:
        recent.append(close)
        position = execer.get_active().get("MYX/USDT")
        decision = strat.decide(close, recent, fr, position=position, bars_held=bars_held)
        if decision.action == 'enter':
            atr = strat.compute_atr_like(recent)
            size = strat.size_by_risk(close, atr, decision.direction)
            if size is None:
                bars_held = bars_held + (1 if position is not None else 0)
                continue
            decision.size = size
            execer.step("MYX/USDT", close, decision)
            bars_held = 0
        elif decision.action in ('exit','reduce'):
            execer.step("MYX/USDT", close, decision)
            if decision.action == 'exit':
                bars_held = 0
        else:
            if position is not None:
                bars_held += 1

    last_price = rows[-1][1]
    execer.liquidate_all({"MYX/USDT": last_price})
    closed = execer.closed
    pnls = [p.pnl for p in closed]
    total = sum(pnls)
    win_count = sum(1 for p in pnls if p > 0)
    lose_count = sum(1 for p in pnls if p <= 0)
    win_rate = (win_count / len(pnls)) if pnls else 0.0
    return {"closed_trades": len(pnls), "total_pnl": total, "win_rate": win_rate, "pnls": pnls}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input_json')
    p.add_argument('--top', type=int, default=3)
    p.add_argument('--klimit', type=int, default=LIMIT, help='Number of klines to fetch (max ~1500)')
    p.add_argument('--train', type=int, default=600)
    p.add_argument('--test', type=int, default=200)
    p.add_argument('--step', type=int, default=200)
    args = p.parse_args()

    with open(args.input_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    results = data.get('results', [])
    if not results:
        print('No results in', args.input_json)
        return

    sorted_results = sorted(results, key=lambda r: float(r.get('total_pnl', 0.0)), reverse=True)
    selected = sorted_results[:args.top]
    print('Selected combos:')
    for s in selected:
        print(' ', s.get('htf_momentum_threshold'), s.get('momentum_window'), 'pnl=', s.get('total_pnl'))

    # fetch klines (default 1000, configurable via --klimit)
    kl = fetch_klines(limit=args.klimit)
    rows = klines_to_rows(kl)
    n = len(rows)
    train = args.train
    test = args.test
    step = args.step

    if train + test > n:
        print('Not enough data for train+test (have', n, 'need', train+test, ')')
        return

    outputs = {}
    for combo in selected:
        combo_key = f"htf{combo.get('htf_momentum_threshold')}_mw{combo.get('momentum_window')}"
        outputs[combo_key] = {"windows": []}
        start = 0
        while start + train + test <= n:
            test_rows = rows[start + train : start + train + test]
            res = run_single_backtest(test_rows, combo, conservative=True)
            outputs[combo_key]['windows'].append(res)
            start += step

        # aggregate
        pnls = [w['total_pnl'] for w in outputs[combo_key]['windows']]
        outputs[combo_key]['mean_pnl'] = mean(pnls) if pnls else 0.0
        outputs[combo_key]['std_pnl'] = stdev(pnls) if len(pnls) > 1 else 0.0
        outputs[combo_key]['n_windows'] = len(pnls)

    out_path = 'var/myx_walkforward_summary.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(outputs, f, indent=2)
    print('Wrote', out_path)
    # print summary
    for k, v in outputs.items():
        print(k, 'windows=', v['n_windows'], 'mean_pnl=', v['mean_pnl'], 'std=', v['std_pnl'])

if __name__ == '__main__':
    main()
