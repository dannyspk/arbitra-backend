"""Backtest harness for feature extractor alert rules.

Expected input: a directory of JSON files. Each file should be a mapping
of exchange -> symbol -> orderbook dict (same shape used in compute_from_snapshots).

Usage:
  $env:PYTHONPATH='src'; python tools/backtest_features.py snapshots_dir
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath('src'))

from arbitrage.analytics.feature_extractor import FeatureExtractor


def load_snapshot(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        print('Usage: backtest_features.py <snapshots_dir>')
        return
    d = sys.argv[1]
    files = sorted([os.path.join(d, f) for f in os.listdir(d) if f.endswith('.json')])
    if not files:
        print('No JSON snapshot files found in', d)
        return

    fe = FeatureExtractor(['binance', 'kucoin', 'mexc'], top_n=5, window_seconds=60)

    # add same sample rule as demo
    def sample_rule(sym, info):
        try:
            if (info.get('imbalance') or 0) > 3 and (info.get('volume_zscore') or 0) > 2:
                return True
        except Exception:
            return False
        return False

    fe.add_rule('imbalance_volume_spike', sample_rule)

    total_alerts = 0
    alerted_symbols = set()
    for p in files:
        snap = load_snapshot(p)
        if not snap:
            continue
        feats = fe.compute_from_snapshots(snap)
        alerts = fe.evaluate_alerts(feats)
        total_alerts += len(alerts)
        for a in alerts:
            alerted_symbols.add(a['symbol'])
    print('Backtest complete')
    print('Files processed:', len(files))
    print('Total alerts:', total_alerts)
    print('Unique symbols alerted:', len(alerted_symbols))
    if alerted_symbols:
        print('Sample symbols:', list(alerted_symbols)[:20])


if __name__ == '__main__':
    main()
