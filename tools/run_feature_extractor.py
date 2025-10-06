"""Small demo runner for the feature extractor.

Run from repo root with PYTHONPATH=src.
"""
import time
import os
import sys

sys.path.insert(0, os.path.abspath('src'))

from arbitrage.analytics.feature_extractor import FeatureExtractor
from arbitrage.hotcoins import _binance_top_by_volume


def main():
    fe = FeatureExtractor(['binance', 'kucoin', 'mexc'], top_n=5, window_seconds=60)
    # enable CSV logging
    fe.set_csv('analytics_features.csv')

    # sample alert rule: imbalance > 3 and volume_zscore > 2
    def sample_rule(sym, info):
        try:
            if (info.get('imbalance') or 0) > 3 and (info.get('volume_zscore') or 0) > 2:
                return True
        except Exception:
            return False
        return False

    fe.add_rule('imbalance_volume_spike', sample_rule)
    # Hotcoins divergence rule: if a hotcoin's mid prices across exchanges
    # diverge by more than 0.5% relative to the minimum, alert.
    hot = [it.get('symbol') or it.get('base') for it in _binance_top_by_volume(top_n=50)]
    hot_set = { (s or '').upper().replace('/', '').replace('-', '') for s in hot if s }

    def hotcoin_divergence_rule(sym, info):
        try:
            # normalize symbol to noslash form like BTCUSDT
            key = (sym or '').upper().replace('/', '').replace('-', '')
            if key not in hot_set:
                return False
            by_ex = info.get('by_exchange') or {}
            mids = []
            for ex, d in by_ex.items():
                try:
                    ask = d.get('ask')
                    bid = d.get('bid')
                    if ask is not None and bid is not None:
                        mids.append((float(ask) + float(bid)) / 2.0)
                except Exception:
                    continue
            if len(mids) < 2:
                return False
            mx = max(mids)
            mn = min(mids)
            if mn <= 0:
                return False
            diff = (mx - mn) / mn
            return diff >= 0.005
        except Exception:
            return False

    # prefer shorter dedupe for hotcoin divergence alerts
    hotcoin_divergence_rule.dedupe_seconds = 120
    fe.add_rule('hotcoin_price_divergence_0.5pct', hotcoin_divergence_rule)
    # enable snapshot dumping every 60s in background
    import threading

    def snapshot_loop():
        import time
        while True:
            p = fe.dump_snapshots('snapshots')
            if p:
                print('Wrote snapshot', p)
            time.sleep(60)

    t = threading.Thread(target=snapshot_loop, daemon=True)
    t.start()
    try:
        for i in range(30):
            out = fe.poll_once()
            alerts = out.get('_alerts') or []
            print(f'ITER {i} - symbols:', len([k for k in out.keys() if not k.startswith("_")]))
            # print a small sample
            for k, v in list((k, v) for k, v in out.items() if not k.startswith('_'))[:8]:
                print(k, v.get('imbalance'), v.get('volume_zscore'))
            if alerts:
                print('ALERTS:')
                for a in alerts:
                    print(' ', a['rule'], a['symbol'])
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
