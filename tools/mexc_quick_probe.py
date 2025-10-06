"""Quick MEXC WS subscription format probe.

Tries a few likely subscription payloads without sending extra headers
so it works across websockets versions. Writes results to
`mexc_quick_probe_results.json`.
"""
import asyncio
import json
import time


async def run_probe_once(endpoint, payloads, duration=3.0):
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

    # try both topic orders and a couple method names
    topic1 = 'spot@public.depth.v3.api.pb@100ms@BTCUSDT'
    topic2 = 'spot@public.depth.v3.api.pb@BTCUSDT@100ms'

    payloads = [
        {'method': 'SUBSCRIPTION', 'params': [topic1], 'id': int(time.time() * 1000)},
        {'method': 'SUBSCRIPTION', 'params': [topic2], 'id': int(time.time() * 1000)},
        {'method': 'SUBSCRIBE', 'params': [topic1], 'id': int(time.time() * 1000)},
        {'method': 'SUBSCRIBE', 'params': [topic2], 'id': int(time.time() * 1000)},
        # dict-style
        {'method': 'SUBSCRIPTION', 'params': {'topic': topic1}, 'id': int(time.time() * 1000)},
        {'method': 'SUBSCRIPTION', 'params': {'topic': topic2}, 'id': int(time.time() * 1000)},
    ]

    all_results = []
    for ep in endpoints:
        print('probing', ep)
        r = await run_probe_once(ep, payloads, duration=3.0)
        all_results.append(r)

    with open('mexc_quick_probe_results.json', 'w', encoding='utf-8') as fh:
        json.dump(all_results, fh, indent=2)
    print('wrote mexc_quick_probe_results.json')


if __name__ == '__main__':
    asyncio.run(main())
