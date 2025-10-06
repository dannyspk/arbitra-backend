"""Lightweight MEXC websocket probe runner.

Tries a small set of subscription payloads across a few endpoints and
writes results to mexc_probe_results.json. This is intentionally
simpler than the previous combinatorial script.
"""
import asyncio
import json
import time
import os

async def probe_once(endpoint, subs, extra_headers=None, duration=5.0):
    try:
        import websockets
    except Exception as e:
        return {'endpoint': endpoint, 'error': f'websockets_missing:{e}'}

    hdrs = dict(extra_headers) if extra_headers else None
    out = {'endpoint': endpoint, 'subs': subs, 'messages': []}
    try:
        async with websockets.connect(endpoint, extra_headers=(hdrs.items() if hdrs else None), max_size=None) as ws:
            # send all subscriptions
            for s in subs:
                try:
                    await ws.send(json.dumps(s))
                except Exception as e:
                    out.setdefault('send_errors', []).append(str(e))

            start = time.time()
            while time.time() - start < duration:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    out.setdefault('recv_errors', []).append(str(e))
                    break
                if isinstance(msg, bytes):
                    try:
                        msg = msg.decode('utf-8', errors='ignore')
                    except Exception:
                        msg = str(msg)
                out['messages'].append(msg)
    except Exception as e:
        out['connect_error'] = str(e)
    return out


async def main():
    endpoints = [
        'wss://wbs-api.mexc.com/ws',
        'wss://wbs.mexc.com/ws',
        'wss://api.mexc.com/ws',
    ]

    # simple array-style subscription (per docs)
    topic1 = 'spot@public.depth.v3.api.pb@100ms@BTCUSDT'
    subs = [{'method': 'SUBSCRIPTION', 'params': [topic1], 'id': int(time.time() * 1000)}]

    key = os.environ.get('MEXC_API_KEY')
    headers_list = [None]
    if key:
        headers_list.append({'X-MEXC-APIKEY': key})

    results = []
    for ep in endpoints:
        for hdrs in headers_list:
            print('probing', ep, 'headers', list(hdrs.keys()) if hdrs else 'none')
            r = await probe_once(ep, subs, extra_headers=hdrs, duration=5.0)
            results.append(r)

    try:
        with open('mexc_probe_results.json', 'w', encoding='utf-8') as fh:
            json.dump(results, fh, indent=2)
    except Exception:
        pass
    print('wrote mexc_probe_results.json')


if __name__ == '__main__':
    asyncio.run(main())
