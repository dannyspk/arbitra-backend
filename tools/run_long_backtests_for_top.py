#!/usr/bin/env python3
"""Pick top N combos from a grid JSON and run longer single backtests for each.
Usage: python tools/run_long_backtests_for_top.py input.json --limit 5000 --top 3

Saves outputs to var/myx_long_htf{htf}_momw{momw}_risk{risk}_limit{limit}.json
"""
import json
import sys
import subprocess
import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('input_json')
parser.add_argument('--limit', type=int, default=5000)
parser.add_argument('--top', type=int, default=3)
args = parser.parse_args()

with open(args.input_json, 'r', encoding='utf-8') as f:
    data = json.load(f)

results = data.get('results', [])
if not results:
    print('No results found in', args.input_json)
    sys.exit(1)

# sort by total_pnl descending
sorted_results = sorted(results, key=lambda r: float(r.get('total_pnl', 0.0)), reverse=True)
selected = sorted_results[: args.top]

print(f'Will run {len(selected)} long backtests (limit={args.limit})')

for combo in selected:
    htf = combo.get('htf_momentum_threshold')
    mom_w = combo.get('momentum_window')
    # assume risk is same as the run file's context; try to read risk from top-level if present
    risk = data.get('risk') or combo.get('risk') or 2.5
    out_name = f"var/myx_long_htf{htf}_momw{mom_w}_risk{risk}_limit{args.limit}.json"
    cmd = [sys.executable, 'tools/grid_backtest_myx.py', '--limit', str(args.limit), '--conservative', '--htf', str(htf), '--mom-w', str(mom_w), '--risk', str(risk)]
    print('Running:', ' '.join(cmd))
    # set env PYTHONPATH=src
    env = os.environ.copy()
    env['PYTHONPATH'] = 'src'
    rc = subprocess.run(cmd, env=env)
    if rc.returncode != 0:
        print('Run failed for', htf, mom_w)
        continue
    # rename output file if present
    default_out = 'var/myx_grid_results.json'
    if os.path.exists(default_out):
        os.replace(default_out, out_name)
        print('Saved long backtest to', out_name)
    else:
        print('Expected output', default_out, 'not found')

print('Done')
