import sys
import traceback
try:
    import ccxt
    print('ccxt version:', getattr(ccxt,'__version__', getattr(ccxt,'version','unknown')))
    try:
        has_binance_attr = hasattr(ccxt, 'binance')
        print('ccxt module has attribute binance:', has_binance_attr)
        if has_binance_attr:
            try:
                cls = getattr(ccxt, 'binance')
                print('ccxt.binance class has watch_ticker attr:', hasattr(cls, 'watch_ticker') or hasattr(cls, 'watchTicker'))
                inst = cls({})
                print('sync instance has watch_ticker attr:', hasattr(inst, 'watch_ticker') or hasattr(inst, 'watchTicker'))
                print('sync instance.has keys:', getattr(inst, 'has', None))
            except Exception as e:
                print('error inspecting sync binance:', e)
    except Exception as e:
        print('error checking sync binance:', e)
    try:
        import ccxt.async_support as ccxta
        print('\nccxt.async_support imported')
        has_async_binance = hasattr(ccxta, 'binance')
        print('ccxt.async_support has binance:', has_async_binance)
        if has_async_binance:
            try:
                acls = getattr(ccxta, 'binance')
                print('async class has watch_ticker attr:', hasattr(acls, 'watch_ticker') or hasattr(acls, 'watchTicker'))
                ainst = acls({})
                print('async instance has watch_ticker attr:', hasattr(ainst, 'watch_ticker') or hasattr(ainst, 'watchTicker'))
                print('async instance.has keys:', getattr(ainst, 'has', None))
            except Exception as e:
                print('error inspecting async binance:', e)
    except Exception:
        print('\nccxt.async_support not available')
    try:
        import ccxtpro
        print('\nccxtpro module present at', getattr(ccxtpro,'__file__',None))
        print('ccxtpro has binance attr:', hasattr(ccxtpro, 'binance'))
    except Exception as e:
        print('\nccxtpro import error:', e)
except Exception:
    traceback.print_exc()
