import sys, time, json
sys.path.insert(0, 'src')
from arbitrage.exchanges.kucoin_depth_feeder import KucoinDepthFeeder
from arbitrage.exchanges.ws_feed_manager import register_feeder, get_feeder, unregister_feeder

f = KucoinDepthFeeder(['BTC/USDT','ETH/USDT','SOL/USDT','PEPE/USDT'])
try:
    f.start()
    register_feeder('kucoin', f)
    time.sleep(8)
    print('feeder registered:', get_feeder('kucoin') is not None)
    try:
        tk = f.get_tickers()
        print('tickers count:', len(tk))
        print(json.dumps({k: tk[k] for k in list(tk.keys())[:20]}, indent=2))
    except Exception as e:
        print('get_tickers error', e)
finally:
    try:
        unregister_feeder('kucoin')
    except Exception:
        pass
    try:
        f.stop()
    except Exception:
        pass
