#!/usr/bin/env python3
"""Summarize grid JSON results into a ranked CSV.
Usage: python tools/summarize_grid_results.py input.json output.csv
"""
import json
import sys
from math import isfinite

if len(sys.argv) < 3:
    print("Usage: python tools/summarize_grid_results.py input.json output.csv")
    sys.exit(2)

in_path = sys.argv[1]
out_path = sys.argv[2]

with open(in_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

rows = []
for combo in data.get('results', []):
    htf = combo.get('htf_momentum_threshold')
    mom_w = combo.get('momentum_window')
    closed = combo.get('closed', [])
    closed_trades = combo.get('closed_trades', len(closed))
    total_pnl = float(combo.get('total_pnl', 0.0))

    pnls = [float(t.get('pnl', 0.0)) for t in closed]
    win_count = sum(1 for p in pnls if p > 0)
    loss_count = sum(1 for p in pnls if p <= 0)
    win_rate = (win_count / closed_trades) if closed_trades else 0.0
    avg_pnl = (sum(pnls) / closed_trades) if closed_trades else 0.0
    avg_win = (sum(p for p in pnls if p > 0) / win_count) if win_count else 0.0
    avg_loss = (sum(p for p in pnls if p <= 0) / loss_count) if loss_count else 0.0
    max_win = max((p for p in pnls), default=0.0)
    max_loss = min((p for p in pnls), default=0.0)

    # compute cumulative PnL sequence and max drawdown
    cum = []
    s = 0.0
    for p in pnls:
        s += p
        cum.append(s)
    peak = float('-inf')
    max_dd = 0.0
    for v in cum:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    if peak > 0 and isfinite(peak):
        max_dd_pct = max_dd / peak
    else:
        max_dd_pct = None

    rows.append({
        'htf_momentum_threshold': htf,
        'momentum_window': mom_w,
        'closed_trades': closed_trades,
        'total_pnl': total_pnl,
        'win_count': win_count,
        'loss_count': loss_count,
        'win_rate': round(win_rate, 4),
        'avg_pnl': round(avg_pnl, 6),
        'avg_win': round(avg_win, 6),
        'avg_loss': round(avg_loss, 6),
        'max_win': round(max_win, 6),
        'max_loss': round(max_loss, 6),
        'max_drawdown_abs': round(max_dd, 6),
        'max_drawdown_pct': round(max_dd_pct, 6) if max_dd_pct is not None else ''
    })

# sort by total_pnl desc
rows.sort(key=lambda r: r['total_pnl'], reverse=True)

# write CSV
import csv
with open(out_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    header = ['htf_momentum_threshold','momentum_window','closed_trades','total_pnl','win_count','loss_count','win_rate','avg_pnl','avg_win','avg_loss','max_win','max_loss','max_drawdown_abs','max_drawdown_pct']
    writer.writerow(header)
    for r in rows:
        writer.writerow([r[h] for h in header])

print(f'Wrote summary to {out_path} with {len(rows)} rows')
