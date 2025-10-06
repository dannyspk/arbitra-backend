"""Probe MEXC public market stream topic permutations (no listenKey).

Tries a list of plausible topic strings and method names against the
public websocket endpoints and writes results to mexc_public_probe.json.
"""
import asyncio
import json
import time


async def probe(endpoint, payloads, duration=2.0):
    try:
        import websockets
    except Exception as e:
        return {'error': f'websockets_missing:{e}'}

    out = {'endpoint': endpoint, 'results': []}
    try:
        async with websockets.connect(endpoint, max_size=None) as ws:
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
                        m = await asyncio.wait_for(ws.recv(), timeout=0.8)
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

    # candidate topic permutations (non-exhaustive)
    base_topics = [
        'spot@public.depth.v3.api.pb@100ms@{s}',
        'spot@public.depth.v3.api.sub@100ms@{s}',
        'spot@public.depth.v3.api@100ms@{s}',
        'spot@public.depth.v3.api@{s}@100ms',
        'spot@public.depth.v3.api@{s}@100ms',
        'spot@public.aggre.deals.v3.api.pb@100ms@{s}',
        'spot@public.bookTicker.v3.api@{s}',
        'spot@public.book.ticker.v3@{s}',
        'spot@public.limit.depths.v3.api@{s}@100ms',
        'spot@public.increase.depths.v3.api@{s}@100ms',
    ]

    symbols = ['BTCUSDT', 'ETHUSDT']

    payloads = []
    method_variants = ['SUBSCRIPTION', 'SUBS', 'sub', 'SUBSCRIBE']

    for s in symbols:
        for t in base_topics:
            topic = t.format(s=s)
            for m in method_variants:
                # array-style param
                payloads.append({'method': m, 'params': [topic], 'id': int(time.time() * 1000)})
                # dict-style
                payloads.append({'method': m, 'params': {'topic': topic}, 'id': int(time.time() * 1000)})

    # deduplicate small set to avoid explosion
    unique = []
    seen = set()
    for p in payloads:
        key = json.dumps(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    all_results = []
    for ep in endpoints:
        print('probing', ep, 'payloads:', len(unique))
        r = await probe(ep, unique, duration=2.0)
        all_results.append(r)

    with open('mexc_public_probe.json', 'w', encoding='utf-8') as fh:
        json.dump(all_results, fh, indent=2)
    print('wrote mexc_public_probe.json')


if __name__ == '__main__':
    asyncio.run(main())
