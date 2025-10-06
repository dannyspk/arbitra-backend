import sys, time, json
sys.path.insert(0, 'src')
from arbitrage.hotcoins import _binance_top_by_volume
from arbitrage.feeder_utils import start_all, stop_all
from arbitrage.exchanges.ws_feed_manager import get_feeder

if __name__ == '__main__':
    tops = _binance_top_by_volume(top_n=30)
    symbols = [f"{i['base']}/{i['quote']}" for i in tops]
    print('subscribe_symbols_sample:', symbols[:10])
    fs = start_all(symbols=symbols, exchanges=['kucoin'])
    try:
        time.sleep(8)
        ku = get_feeder('kucoin')
        print('ku_present:', ku is not None)
        if not ku:
            print('KuCoin feeder not present')
        else:
            try:
                books = getattr(ku, '_books', None)
                if books is None:
                    print('ku._books attribute missing')
                else:
                    print('ku._books count:', len(books))
                    # print up to 20 keys
                    keys = list(books.keys())[:20]
                    print('ku._books keys sample:', keys)
                try:
                    tk = ku.get_tickers()
                    print('get_tickers count:', len(tk))
                    print('get_tickers sample:', json.dumps({k: v for k, v in list(tk.items())[:10]}, indent=2))
                except Exception as e:
                    print('get_tickers error:', repr(e))
            except Exception as e:
                print('error inspecting ku feeder:', repr(e))
    finally:
        stop_all(fs)
