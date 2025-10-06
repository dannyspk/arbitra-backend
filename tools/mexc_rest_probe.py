import time

def try_ccxt(symbols):
    try:
        import ccxt
    except Exception as e:
        print('ccxt import failed:', type(e).__name__, e)
        return None
    try:
        ex = ccxt.mexc()
        out = {}
        for s in symbols:
            try:
                t = ex.fetch_ticker(s)
                out[s] = {'last': t.get('last'), 'ask': t.get('ask'), 'bid': t.get('bid')}
            except Exception as e:
                out[s] = {'error': str(e)}
        return out
    except Exception as e:
        print('ccxt operation failed:', type(e).__name__, e)
        return None


def try_rest(symbols):
    import requests
    out = {}
    for s in symbols:
        # MEXC REST frequently uses symbol with underscore: BTC_USDT
        sym = s.replace('/', '_')
        # try v3 ticker price endpoint
        urls = [
            f'https://www.mexc.com/api/v3/ticker/price?symbol={sym}',
            f'https://api.mexc.com/api/v3/ticker/price?symbol={sym}',
            f'https://www.mexc.com/api/v3/ticker/24hr?symbol={sym}',
            f'https://api.mexc.com/api/v3/ticker/24hr?symbol={sym}',
        ]
        ok = False
        for url in urls:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    try:
                        j = r.json()
                        # typical shapes: {symbol: 'BTC_USDT', price: '...'} or list
                        if isinstance(j, dict):
                            out[s] = j
                        else:
                            out[s] = {'raw': j}
                        ok = True
                        break
                    except Exception as e:
                        out[s] = {'error': 'json:'+str(e)}
                        ok = True
                        break
                else:
                    out[s] = {'status': r.status_code, 'text': r.text[:200]}
            except Exception as e:
                out[s] = {'error': str(e)}
        if not ok:
            # leave whatever last error is
            pass
    return out

if __name__ == '__main__':
    symbols = ['BTC/USDT', 'ETH/USDT', 'DOGE/USDT']
    print('Trying CCXT...')
    ccxt_out = try_ccxt(symbols)
    print('CCXT result:', ccxt_out)
    if not ccxt_out:
        print('Trying REST fallback...')
        rest_out = try_rest(symbols)
        print('REST result:', rest_out)
    else:
        print('Done')
