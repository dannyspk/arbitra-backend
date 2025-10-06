import asyncio
import json
import asyncio
import json
import time
from typing import List, Dict, Any


def make_topic(symbol: str, cadence_ms: int, kind: str = 'depth', variant: str = 'pb') -> str:
    # symbol expected like 'BTCUSDT' or 'BTC/USDT'
    s = symbol.upper().replace('/', '').replace('-', '')
    if kind == 'depth':
        if variant == 'pb':
            return f"spot@public.depth.v3.api.pb@{s}@{cadence_ms}ms"
        return f"spot@public.depth.v3.api.sub@{s}@{cadence_ms}ms"
    # aggregate/deals
    return f"spot@public.aggre.deals.v3.api.pb@{s}@{cadence_ms}ms"


async def try_subscriptions(symbols: List[str]):
    try:
        import websockets
    except Exception as e:
        print('websockets not installed:', e)
        return

    url = 'wss://wbs-api.mexc.com/ws'
    # If a listen key/token is present in env, append as query param to test authenticated WS
    import os
    lk = os.environ.get('MEXC_LISTEN_KEY') or os.environ.get('MEXC_API_KEY_LISTEN') or os.environ.get('MEXC_LISTENKEY')
    if not lk:
        # try to obtain a listen key via a small REST call if keys present
        try:
            import requests
            key = os.environ.get('MEXC_API_KEY') or os.environ.get('ARB_MEXC_API_KEY')
            if key:
                # attempt the common endpoint
                try:
                    r = requests.post('https://api.mexc.com/api/v3/listenKey', headers={'ApiKey': key}, timeout=3)
                    js = r.json()
                    if isinstance(js, dict):
                        lk = js.get('listenKey') or (js.get('data') or {}).get('listenKey')
                except Exception:
                    lk = None
        except Exception:
            lk = None
    if lk:
        url = url + f"?listenKey={lk}"

    # prepare multiple endpoints to try (include the default with listenKey if present)
    endpoints = [
        url,
        'wss://wbs.mexc.com/ws',
        'wss://api.mexc.com/ws',
        'wss://www.mexc.com/ws',
    ]

    # method names and param styles to try
    method_variants = [
        ('SUBSCRIPTION', 'array'),
        ('SUBSCRIPTION', 'dict_channel'),
        ('SUBSCRIPTION', 'dict_topic'),
        ('SUBSCRIBE', 'array'),
        ('SUBSCRIBE', 'dict_channel'),
        ('SUBSCRIBE', 'dict_topic'),
        # less-likely variants
        ('sub.deal', 'array'),
        ('sub.depth', 'array'),
    ]

    cadences = [100, 200, 500, 1000, 2000]
    variants = ['pb', 'sub']

    results: List[Dict[str, Any]] = []

    print('connecting to endpoints:', endpoints)
    try:
        # If API key present, try multiple header auth variants by opening separate connections
        import os, hmac, hashlib
        key = os.environ.get('MEXC_API_KEY') or os.environ.get('ARB_MEXC_API_KEY')
        secret = os.environ.get('MEXC_API_SECRET') or os.environ.get('ARB_MEXC_API_SECRET')

        header_variants = [None]
        if key:
            header_variants.extend([
                {"ApiKey": key},
                {"X-MEXC-APIKEY": key},
                {"ACCESS-KEY": key},
                {"Api-Key": key},
                {"Authorization": f"Bearer {key}"},
            ])

        # try every endpoint and header variant
        for endpoint in endpoints:
            for headers in header_variants:
                # add a default Origin header for browser-like requests
                hdrs = dict(headers) if headers else {}
                hdrs.setdefault('Origin', 'https://www.mexc.com')
                try:
                    if headers is None:
                        ws_ctx = websockets.connect(endpoint, max_size=None)
                    else:
                        ws_ctx = websockets.connect(endpoint, extra_headers=hdrs.items(), max_size=None)
                    async with ws_ctx as ws:
                        print('connected to', endpoint, 'headers=' + (str(list(hdrs.keys())) if hdrs else 'none'))
                        # for each symbol iterate cadences and method styles
                        for sym in symbols:
                            for cadence in cadences:
                                for variant in variants:
                                    topic = make_topic(sym, cadence, 'depth', variant)
                                    for method, pstyle in method_variants:
                                        # try several auth payload modes per subscription
                                        auth_payload_modes = ['none']
                                        if key:
                                            auth_payload_modes.append('api_key_param')
                                        if key and secret:
                                            auth_payload_modes.append('signed_param')

                                        for auth_mode in auth_payload_modes:
                                            # build params based on style
                                            if pstyle == 'array':
                                                params_obj = [topic]
                                            elif pstyle == 'dict_channel':
                                                params_obj = {'channel': topic}
                                            else:
                                                params_obj = {'topic': topic}

                                            # attach auth into params_obj if requested
                                            if auth_mode == 'api_key_param':
                                                if isinstance(params_obj, list):
                                                    params_obj = params_obj + [{'apiKey': key}]
                                                elif isinstance(params_obj, dict):
                                                    params_obj = dict(params_obj)
                                                    params_obj['apiKey'] = key
                                            elif auth_mode == 'signed_param':
                                                ts = str(int(time.time() * 1000))
                                                sig_base = topic + ts
                                                try:
                                                    sig = hmac.new(secret.encode('utf-8'), sig_base.encode('utf-8'), hashlib.sha256).hexdigest()
                                                except Exception:
                                                    sig = ''
                                                if isinstance(params_obj, list):
                                                    params_obj = params_obj + [{'apiKey': key, 'timestamp': ts, 'signature': sig}]
                                                elif isinstance(params_obj, dict):
                                                    params_obj = dict(params_obj)
                                                    params_obj.update({'apiKey': key, 'timestamp': ts, 'signature': sig})

                                            payload = {'method': method, 'params': params_obj, 'id': int(time.time() * 1000)}

                                            pkt_text = json.dumps(payload)
                                            print('\n>>> trying', sym, 'cadence', cadence, 'ms variant', variant, 'method', method, 'pstyle', pstyle, 'headers', (list(headers.keys()) if headers else 'none'), 'auth_mode', auth_mode)
                                            try:
                                                await ws.send(pkt_text)
                                            except Exception as e:
                                                print('send failed', type(e).__name__, e)
                                                results.append({'symbol': sym, 'topic': topic, 'method': method, 'pstyle': pstyle, 'headers': headers, 'auth_mode': auth_mode, 'error': f'send:{e}'})
                                                continue

                                            # collect messages for a short window
                                            start = time.time()
                                            seen_any = False
                                            msgs: List[str] = []
                                            while time.time() - start < 3.0:
                                                try:
                                                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                                except asyncio.TimeoutError:
                                                    break
                                                except Exception as e:
                                                    msgs.append(f'RECV_ERROR:{type(e).__name__}:{e}')
                                                    break
                                                if isinstance(msg, bytes):
                                                    try:
                                                        msg = msg.decode('utf-8', errors='ignore')
                                                    except Exception:
                                                        msg = str(msg)
                                                msgs.append(msg)
                                                # quick check for depth-like structure
                                                low = msg.lower()
                                                # treat obvious rejection/error messages as failures and continue probing
                                                if 'blocked' in low or 'not subscribed' in low or 'msg format invalid' in low or 'subscribe is not supported' in low:
                                                    # record but do not mark success
                                                    continue
                                                # success only when we see actual orderbook/tick payloads
                                                if (('asks' in low and 'bids' in low) or 'tick' in low or ('channel' in low and 'depth' in low)):
                                                    seen_any = True
                                                    break

                                    entry = {'symbol': sym, 'topic': topic, 'method': method, 'pstyle': pstyle, 'cadence': cadence, 'variant': variant, 'messages': msgs, 'success': seen_any}
                                    results.append(entry)
                                    # if success, write and return early
                                    if seen_any:
                                        print('\n=== SUCCESS candidate ===')
                                        print(json.dumps(entry, indent=2)[:2000])
                                        # persist results
                                        try:
                                            with open('mexc_probe_results.json', 'w', encoding='utf-8') as fh:
                                                json.dump(results, fh, indent=2)
                                        except Exception:
                                            pass
                                        return results

            print('\nno successful depth subscription observed; writing results')
            try:
                with open('mexc_probe_results.json', 'w', encoding='utf-8') as fh:
                    json.dump(results, fh, indent=2)
            except Exception:
                pass
            return results
    except Exception as e:
        print('connect error', type(e).__name__, e)
        return []


if __name__ == '__main__':
    import sys
    syms = ['BTC/USDT', 'ETH/USDT']
    if len(sys.argv) > 1:
        syms = sys.argv[1:]
    asyncio.run(try_subscriptions(syms))
