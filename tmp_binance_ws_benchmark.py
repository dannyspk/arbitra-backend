"""Binance websocket benchmark

Connects to Binance combined trade streams for a set of symbols and measures
inter-arrival times (seconds) for messages per symbol.

Usage (PowerShell):
  $env:BINANCE_SYMBOLS='BTCUSDT,ETHUSDT'
  $env:MAX_UPDATES='50'
  $env:TIMEOUT_S='30'
  python tmp_binance_ws_benchmark.py

Defaults: BTCUSDT,ETHUSDT; MAX_UPDATES=50; TIMEOUT_S=30
"""

import os
import asyncio
import time
import json
import statistics

try:
    import websockets
except Exception:
    websockets = None


async def run_benchmark(symbols, max_updates=50, timeout_s=30.0):
    # Binance combined stream expects lowercase symbols without slash
    streams = '/'.join([f"{s.lower()}@trade" for s in symbols])
    uri = f"wss://stream.binance.com:9443/stream?streams={streams}"
    print('Connecting to', uri)

    results = {s: [] for s in symbols}
    counts = {s: 0 for s in symbols}

    start = time.time()
    try:
        async with websockets.connect(uri, max_size=None) as ws:
            while True:
                now = time.time()
                if now - start > timeout_s:
                    print('Timed out after', timeout_s, 'seconds')
                    break
                # stop if all symbols reached max_updates
                if all(counts[s] >= max_updates for s in symbols):
                    print('Reached max updates for all symbols')
                    break
                try:
                    remaining = max(0.1, timeout_s - (time.time() - start))
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    continue
                t = time.time()
                try:
                    obj = json.loads(msg)
                except Exception:
                    # not JSON? skip
                    continue
                stream = obj.get('stream')
                data = obj.get('data')
                sym = None
                if stream:
                    sym = stream.split('@')[0].upper()
                elif isinstance(data, dict):
                    sym = data.get('s')
                if not sym:
                    continue
                if sym not in results:
                    # ignore other symbols
                    continue
                results[sym].append(t)
                counts[sym] += 1
                # show progress occasionally
                if counts[sym] % max(1, max_updates // 10) == 0:
                    print(f"{sym}: updates={counts[sym]}")
    except Exception as e:
        print('WebSocket error:', e)

    # compute stats
    stats = {}
    for s, times in results.items():
        if len(times) < 2:
            stats[s] = None
            continue
        deltas = [t2 - t1 for t1, t2 in zip(times, times[1:])]
        stats[s] = {
            'updates': len(times),
            'duration_s': times[-1] - times[0] if len(times) >= 2 else 0.0,
            'avg_s': statistics.mean(deltas) if deltas else None,
            'median_s': statistics.median(deltas) if deltas else None,
            'min_s': min(deltas) if deltas else None,
            'max_s': max(deltas) if deltas else None,
        }
    return stats


def main():
    if websockets is None:
        print('The required package "websockets" is not installed. Install it with: pip install websockets')
        return
    sym_env = os.environ.get('BINANCE_SYMBOLS', 'BTCUSDT,ETHUSDT')
    symbols = [s.strip().upper().replace('/', '') for s in sym_env.split(',') if s.strip()]
    try:
        max_updates = int(os.environ.get('MAX_UPDATES', '50'))
    except Exception:
        max_updates = 50
    try:
        timeout_s = float(os.environ.get('TIMEOUT_S', '30.0'))
    except Exception:
        timeout_s = 30.0

    print('Symbols:', symbols)
    print('Max updates per symbol:', max_updates)
    print('Timeout:', timeout_s)

    stats = asyncio.run(run_benchmark(symbols, max_updates=max_updates, timeout_s=timeout_s))

    print('\nBenchmark results:')
    for s, st in stats.items():
        print('\n---', s, '---')
        if st is None:
            print('Not enough messages received to compute stats')
            continue
        print('updates:', st['updates'])
        print('duration_s:', f"{st['duration_s']:.3f}")
        print('avg_s:', f"{st['avg_s']:.6f}")
        print('median_s:', f"{st['median_s']:.6f}")
        print('min_s:', f"{st['min_s']:.6f}")
        print('max_s:', f"{st['max_s']:.6f}")


if __name__ == '__main__':
    main()
