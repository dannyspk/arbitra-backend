import sys, time, json, os
sys.path.insert(0, 'src')
# ensure arbitrage mode enabled so feeders can start
os.environ['ARB_ENABLE_ARBITRAGE'] = '1'
from arbitrage.feeder_utils import start_all, stop_all
from arbitrage.exchanges.ws_feed_manager import get_feeder
from arbitrage.hotcoins import find_hot_coins

# Start KuCoin feeder (and Binance to be safe)
fs = start_all(exchanges=['kucoin','binance'])
print('started feeders:', list(fs.keys()))
try:
    time.sleep(6)
    ku = get_feeder('kucoin')
    bi = get_feeder('binance')
    print('ku present:', ku is not None)
    print('bi present:', bi is not None)
    feeders = []
    if ku:
        feeders.append(ku)
    # request hotcoins using feeder snapshots when present
    res = find_hot_coins(exchanges=feeders or None, max_results=20)
    print('hotcoins count:', len(res))
    out = []
    for r in res:
        out.append({
            'symbol': r.get('symbol'),
            'best_ask': r.get('best_ask'),
            'best_bid': r.get('best_bid'),
            'asks_exchanges': r.get('asks_exchanges'),
            'bids_exchanges': r.get('bids_exchanges'),
            'orderbook_depth_usd': r.get('orderbook_depth_usd'),
            'quoteVolume': r.get('quoteVolume')
        })
    print(json.dumps(out, indent=2))
finally:
    stop_all(fs)
