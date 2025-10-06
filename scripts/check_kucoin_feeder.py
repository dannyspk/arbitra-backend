import sys, time, json
sys.path.insert(0, 'src')
from arbitrage.hotcoins import _binance_top_by_volume, find_hot_coins
from arbitrage.feeder_utils import start_all, stop_all
from arbitrage.exchanges.ws_feed_manager import get_feeder

if __name__ == '__main__':
    tops = _binance_top_by_volume(top_n=60)
    symbols = [f"{i['base']}/{i['quote']}" for i in tops]
    print('subscribe_symbols_sample:', symbols[:10])
    fs = start_all(symbols=symbols, exchanges=['kucoin'])
    try:
        print('feeders_started:', list(fs.keys()))
        time.sleep(8)
        ku = get_feeder('kucoin')
        print('ku_present:', ku is not None)
        if not ku:
            print('KuCoin feeder not available or failed to start.')
        else:
            res = find_hot_coins([ku], max_results=50)
            print('kucoin_hotcoins_count:', len(res))
            print(json.dumps([{
                'symbol': r.get('symbol'),
                'base': r.get('base'),
                'quote': r.get('quote'),
                'orderbook_depth_usd': r.get('orderbook_depth_usd'),
                'quoteVolume': r.get('quoteVolume')
            } for r in res], indent=2))
    finally:
        stop_all(fs)
