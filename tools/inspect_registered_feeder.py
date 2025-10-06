# Run with PYTHONPATH=src
try:
    from arbitrage.exchanges.ws_feed_manager import get_feeder
except Exception as e:
    print('import fail', e); raise

f = get_feeder('mexc')
print('feeder repr:', repr(f))
if not f:
    print('no feeder registered')
else:
    # print type and whether it has get_tickers/get_order_book
    print('type:', type(f))
    print('has get_tickers:', hasattr(f, 'get_tickers'))
    print('has get_order_book:', hasattr(f, 'get_order_book'))
    try:
        print('tickers sample length:', len(f.get_tickers() or {}))
    except Exception as e:
        print('get_tickers failed:', e)
    try:
        print('order book BTC/USDT:', f.get_order_book('BTC/USDT'))
    except Exception as e:
        print('get_order_book failed:', e)
