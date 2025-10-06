"""Targeted MEXC public probe using browser-like headers.

This script connects with an Origin and User-Agent header and tests a
small set of likely public market topics (both pb and non-pb). Results
are written to `mexc_public_probe_headers.json`.
"""
import asyncio
import json
import time
import os


async def probe(endpoint, payloads, headers, duration=3.0):
    try:
        import websockets
    except Exception as e:
        return {'error': f'websockets_missing:{e}'}

    out = {'endpoint': endpoint, 'headers': headers, 'results': []}
    try:
        # websockets.connect accepts extra_headers as list/sequence of tuples
        extra = list(headers.items()) if headers else None
        async with websockets.connect(endpoint, extra_headers=extra, max_size=None) as ws:
            for p in payloads:
                txt = json.dumps(p)
                try:
                    await ws.send(txt)
                except Exception as e:
                    out['results'].append({'payload': p, 'send_error': str(e)})
                    continue
                msgs = []
                start = time.time()
                while time.time() - start < duration:
                    try:
                        m = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        break
                    except Exception as e:
                        msgs.append({'recv_error': str(e)})
                        break
                    if isinstance(m, bytes):
                        try:
                            m = m.decode('utf-8', errors='ignore')
                        except Exception:
                            m = str(m)
                    msgs.append(m)
                out['results'].append({'payload': p, 'messages': msgs})
    except Exception as e:
        out['connect_error'] = str(e)
    return out


async def main():
    endpoints = ['wss://wbs-api.mexc.com/ws', 'wss://wbs.mexc.com/ws']

    # curated topics (non-pb preferred first)
    topics = [
        'spot@public.depth.v3.api.sub@100ms@BTCUSDT',
        'spot@public.depth.v3.api@100ms@BTCUSDT',
        'spot@public.limit.depths.v3.api@BTCUSDT@100ms',
        'spot@public.bookTicker.v3.api@BTCUSDT',
        'spot@public.aggre.deals.v3.api@100ms@BTCUSDT',
        # pb variants
        'spot@public.depth.v3.api.pb@100ms@BTCUSDT',
        'spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT',
    ]

    method_variants = ['SUBSCRIPTION', 'SUBSCRIBE']
    payloads = []
    for t in topics:
        for m in method_variants:
            payloads.append({'method': m, 'params': [t], 'id': int(time.time() * 1000)})
            payloads.append({'method': m, 'params': {'topic': t}, 'id': int(time.time() * 1000)})

    headers = {
        'Origin': 'https://www.mexc.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        # adding referer sometimes helps
        'Referer': 'https://www.mexc.com',
    }

    results = []
    for ep in endpoints:
        print('probing', ep)
        r = await probe(ep, payloads, headers, duration=3.0)
        results.append(r)

    with open('mexc_public_probe_headers.json', 'w', encoding='utf-8') as fh:
        json.dump(results, fh, indent=2)
    print('wrote mexc_public_probe_headers.json')


if __name__ == '__main__':
    asyncio.run(main())
