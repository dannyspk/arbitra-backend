"""Simple ccxt.pro demo: subscribe to live tickers for a few symbols and measure latency/throughput.

Usage (PowerShell):
  $env:CCXTPRO_EXCHANGE='binance'
  $env:CCXTPRO_SYMBOLS='BTC/USDT,ETH/USDT'
  python tmp_ccxtpro_demo.py

Notes:
- Requires ccxtpro installed.
- Uses watch_ticker if available; falls back to polling fetch_ticker if not.
- Runs for a limited number of updates or a timeout and prints stats.
"""

import asyncio
import os
import time
import statistics

try:
    import ccxtpro as ccxtpro  # type: ignore
except Exception:
    ccxtpro = None
try:
    import ccxt  # type: ignore
except Exception:
    ccxt = None


async def watch_ticker_loop(client, symbol, results, max_updates=20, timeout=15.0):
    start = time.time()
    updates = 0
    last_ts = None
    times = []
    try:
        if hasattr(client, 'watch_ticker'):
            while updates < max_updates and (time.time() - start) < timeout:
                tick = await asyncio.wait_for(client.watch_ticker(symbol), timeout=max(1.0, timeout - (time.time()-start)))
                now = time.time()
                # record arrival timestamp
                times.append(now)
                updates += 1
                if updates % 5 == 0:
                    print(f"[{client.id}] {symbol} updates={updates} last_price={tick.get('last')} elapsed={now-start:.2f}s")
        else:
            # fallback: polling
            while updates < max_updates and (time.time() - start) < timeout:
                tick = await asyncio.wait_for(client.fetch_ticker(symbol), timeout=max(1.0, timeout - (time.time()-start)))
                now = time.time()
                times.append(now)
                updates += 1
                if updates % 5 == 0:
                    print(f"[{client.id}] (poll) {symbol} updates={updates} last_price={tick.get('last')} elapsed={now-start:.2f}s")
    except asyncio.TimeoutError:
        print(f"[{client.id}] {symbol} watcher timed out after {time.time()-start:.1f}s with {updates} updates")
    except Exception as e:
        print(f"[{client.id}] {symbol} watcher error: {e}")
    # compute deltas
    deltas = [t2 - t1 for t1, t2 in zip(times, times[1:])] if len(times) > 1 else []
    results[symbol] = {
        'updates': updates,
        'duration': time.time() - start,
        'deltas': deltas,
        'last_price': tick.get('last') if 'tick' in locals() and isinstance(tick, dict) else None,
    }


async def main():
    exchange_id = os.environ.get('CCXTPRO_EXCHANGE', 'binance')
    symbols_env = os.environ.get('CCXTPRO_SYMBOLS', 'BTC/USDT,ETH/USDT')
    symbols = [s.strip() for s in symbols_env.split(',') if s.strip()]

    print('Using ccxt.pro exchange:', exchange_id)
    print('Symbols:', symbols)

    client = None
    used = None
    # Try ccxt.pro first
    if ccxtpro is not None:
        try:
            exchange_cls = getattr(ccxtpro, exchange_id)
            client = exchange_cls({})
            used = 'ccxtpro'
        except Exception:
            client = None
    # Fallback to synchronous ccxt if pro not available for this exchange
    if client is None and ccxt is not None:
        try:
            exchange_cls = getattr(ccxt, exchange_id)
            client = exchange_cls({})
            used = 'ccxt'
        except Exception:
            client = None

    if client is None:
        raise SystemExit(f"Could not instantiate exchange '{exchange_id}' via ccxtpro or ccxt")

    print('Using client from', used)

    # try to enable rate limit parity though for websockets it's less relevant
    try:
        setattr(client, 'enableRateLimit', True)
    except Exception:
        pass

    results = {}

    # If using sync ccxt, our watcher will fallback to polling via asyncio.to_thread
    tasks = [asyncio.create_task(watch_ticker_loop(client, sym, results, max_updates=20, timeout=20.0)) for sym in symbols]

    # Wait for tasks to complete or timeout
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=25.0)
    except asyncio.TimeoutError:
        print('Overall demo timed out')
    except Exception as e:
        print('Demo error:', e)

    # print summary
    for sym in symbols:
        r = results.get(sym, {})
        print('\n---', sym, '---')
        print('updates:', r.get('updates'))
        print('duration:', f"{r.get('duration'):.2f}s" if r.get('duration') else 'n/a')
        deltas = r.get('deltas') or []
        if deltas:
            print('avg interval: %.3fs' % (statistics.mean(deltas)))
            print('median interval: %.3fs' % (statistics.median(deltas)))
            print('min: %.3fs max: %.3fs' % (min(deltas), max(deltas)))
        else:
            print('no deltas recorded')
        print('last_price:', r.get('last_price'))

    # close client
    try:
        await client.close()
    except Exception:
        pass


if __name__ == '__main__':
    asyncio.run(main())
