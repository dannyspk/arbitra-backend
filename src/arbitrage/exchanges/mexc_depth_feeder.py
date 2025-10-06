from __future__ import annotations

import asyncio
import json
import time
import threading
from typing import Dict, Any, List
import os
import base64
import gzip
import zlib
import importlib
import inspect
import types
try:
    import requests
except Exception:
    requests = None

try:
    import websockets
except Exception:
    websockets = None


class MexcDepthFeeder:
    """Lightweight MEXC L2 feeder.

    This feeder subscribes to public depth/trade streams and keeps a small
    in-memory top-of-book snapshot per symbol. The implementation is
    defensive because MEXC websocket payload shapes may vary; it attempts
    to handle common shapes (data.asks/data.bids, tick, etc.).

    Assumptions (based on MEXC docs):
    - Websocket endpoint: wss://wbs-api.mexc.com/ws
    - Subscription topic forms look like: spot@public.depth.v3.api.pb@BTCUSDT@100ms
      or spot@public.aggre.deals.v3.api.pb@BTCUSDT@100ms. We try several
      reasonable topic names per symbol.
    """

    def __init__(self, symbols: List[str]):
        # normalize symbol names (MEXC expects uppercase symbols without separators)
        self.symbols = [s.upper().replace('/', '').replace('-', '') for s in symbols]
        self._books: Dict[str, Dict[str, List]] = {}
        self._levels: Dict[str, Dict[str, Dict[float, float]]] = {}
        self._ts = 0.0
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        if websockets is None:
            raise ImportError('websockets package is required for MexcDepthFeeder')
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        try:
            if self._thread is not None:
                self._thread.join(timeout=2.0)
        except Exception:
            pass

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_main())
        except Exception:
            pass

    async def _ws_main(self):
        base = 'wss://wbs-api.mexc.com/ws'

        # If API keys are present, attempt to fetch a listenKey/token via REST
        # This is defensive: try several common header names and candidate URLs.
        def _get_listen_key() -> str | None:
            try:
                key = os.environ.get('MEXC_API_KEY') or os.environ.get('ARB_MEXC_API_KEY')
                secret = os.environ.get('MEXC_API_SECRET') or os.environ.get('ARB_MEXC_API_SECRET')
                if not key or not requests:
                    return None
                # candidate endpoints to try (best-effort). MEXC docs show
                # GET/POST on /api/v3/userDataStream for listenKey creation/listing
                candidates = [
                    'https://api.mexc.com/api/v3/userDataStream',
                    'https://api.mexc.com/api/v3/listenKey',
                    'https://wbs-api.mexc.com/api/v3/listenKey',
                    'https://www.mexc.com/api/v3/listenKey',
                    'https://api.mexc.com/open/api/v2/listenKey',
                    'https://api.mexc.com/open/api/v2/user/listenKey',
                ]
                # common header names observed in various docs/clients
                header_names = ['X-MEXC-APIKEY', 'ApiKey', 'Api-Key', 'ACCESS-KEY']
                for url in candidates:
                    for hn in header_names:
                        try:
                            h = {hn: key}
                            # small timeout to avoid blocking
                            # POST is used to create a new listenKey on many APIs
                            r = requests.post(url, headers=h, timeout=3)
                        except Exception:
                            # try GET as a fallback (some endpoints expose listing via GET)
                            try:
                                r = requests.get(url, headers={hn: key}, timeout=3)
                            except Exception:
                                continue
                        try:
                            js = r.json()
                        except Exception:
                            js = None
                        # common shapes: {'listenKey': '...'} or {'data': {'listenKey': '...'}}
                        if isinstance(js, dict):
                            # top-level keys
                            for k in ('listenKey', 'listen_key', 'listenkey', 'token', 'data'):
                                if k in js and js.get(k):
                                    if k == 'data' and isinstance(js.get('data'), dict):
                                        d = js.get('data')
                                        for dk in ('listenKey', 'listen_key', 'token'):
                                            if dk in d and d.get(dk):
                                                return str(d.get(dk))
                                    elif k != 'data':
                                        # sometimes the API returns a list under 'listenKey'
                                        val = js.get(k)
                                        if isinstance(val, list) and val:
                                            return str(val[0])
                                        return str(val)
                # If not found yet, try a signed POST per MEXC docs: timestamp + signature on query
                try:
                    import hashlib, hmac
                    ts = str(int(time.time() * 1000))
                    query = f"timestamp={ts}"
                    sig = hmac.new(secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest() if secret else ''
                    for url in candidates:
                        signed_url = f"{url}?{query}&signature={sig}"
                        for hn in header_names:
                            try:
                                r = requests.post(signed_url, headers={hn: key}, timeout=5)
                            except Exception:
                                try:
                                    r = requests.get(signed_url, headers={hn: key}, timeout=5)
                                except Exception:
                                    continue
                            try:
                                js = r.json()
                            except Exception:
                                js = None
                            if isinstance(js, dict):
                                if 'listenKey' in js and js.get('listenKey'):
                                    return str(js.get('listenKey'))
                                if 'data' in js and isinstance(js.get('data'), dict):
                                    d = js.get('data')
                                    for dk in ('listenKey', 'listen_key', 'token'):
                                        if dk in d and d.get(dk):
                                            return str(d.get(dk))
                except Exception:
                    pass
                return None
            except Exception:
                return None

        listen_key = _get_listen_key()
        if listen_key:
            try:
                # attach as query param; some servers expect ?listenKey=token
                base = base + f"?listenKey={listen_key}"
            except Exception:
                pass

        # build candidate topics for each symbol; MEXC uses uppercase symbols
        topics = []
        for s in self.symbols:
            # prefer depth snapshots with a 100ms cadence (per docs examples)
            # NOTE: MEXC docs show cadence before the symbol (e.g. ...@100ms@BTCUSDT)
            topics.append(f"spot@public.depth.v3.api.pb@100ms@{s}")
            topics.append(f"spot@public.depth.v3.api.sub@100ms@{s}")
            topics.append(f"spot@public.aggre.deals.v3.api.pb@100ms@{s}")

        # MEXC allows up to 30 subscriptions per websocket connection. Split topics
        # into chunks of up to 30 and create one connection per chunk.
        chunks: List[List[str]] = []
        cur: List[str] = []
        for t in topics:
            if len(cur) >= 30:
                chunks.append(cur)
                cur = []
            cur.append(t)
        if cur:
            chunks.append(cur)

        async def _run_conn(chunk: List[str]):
            # Try to maintain a persistent connection with keepalive pings.
            reconnect_backoff = 1.0
            while self._running:
                try:
                    async with websockets.connect(base, max_size=None) as ws:
                        # send all subscriptions for this chunk
                        for t in chunk:
                            # send the documented array-style subscription: params is an array of topic strings
                            sub = {'method': 'SUBSCRIPTION', 'params': [t], 'id': int(time.time() * 1000)}
                            # log outgoing subscription for diagnostics
                            try:
                                with open('mexc_raw_messages.log', 'a', encoding='utf-8') as fh:
                                    fh.write('OUT: ' + json.dumps(sub) + '\n')
                            except Exception:
                                pass
                            try:
                                await ws.send(json.dumps(sub))
                            except Exception:
                                # ignore individual subscribe failures
                                continue

                        # keep track of a small raw sample for debugging
                        raw_log: List[str] = []
                        start_ts = time.time()

                        async def _recv_loop():
                            while self._running:
                                try:
                                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                except asyncio.TimeoutError:
                                    # continue to allow pinging
                                    await asyncio.sleep(0)
                                    continue
                                except Exception:
                                    return
                                try:
                                    if len(raw_log) < 200 and (time.time() - start_ts) < 30:
                                        raw_log.append(msg if isinstance(msg, str) else str(msg))
                                    elif len(raw_log) == 200 or (time.time() - start_ts) >= 30:
                                        try:
                                            with open('mexc_raw_messages.log', 'w', encoding='utf-8') as fh:
                                                for m in raw_log:
                                                    try:
                                                        fh.write(m)
                                                        fh.write('\n')
                                                    except Exception:
                                                        pass
                                        except Exception:
                                            pass

                                    # attempt to parse JSON payload
                                    try:
                                        obj = json.loads(msg)
                                    except Exception:
                                        # not JSON; skip
                                        continue

                                    # quick ping/pong handling
                                    try:
                                        if isinstance(obj, dict) and ('ping' in obj or obj.get('method') == 'PING'):
                                            ping_val = obj.get('ping') if 'ping' in obj else (obj.get('params') or {}).get('ping') if isinstance(obj.get('params'), dict) else None
                                            try:
                                                if ping_val is not None:
                                                    await ws.send(json.dumps({'pong': ping_val}))
                                                else:
                                                    await ws.send(json.dumps({'method': 'PONG', 'id': int(time.time() * 1000)}))
                                            except Exception:
                                                pass
                                            continue
                                    except Exception:
                                        pass

                                    # normalize payload container and support compressed/base64/protobuf data
                                    raw_data = None
                                    if isinstance(obj, dict):
                                        if 'data' in obj:
                                            raw_data = obj['data']
                                        elif 'tick' in obj:
                                            raw_data = obj['tick']
                                        elif 'result' in obj:
                                            raw_data = obj['result']
                                        else:
                                            raw_data = obj

                                    data = None
                                    # helper to try parsing bytes with possible decompress
                                    def try_parse_bytes(bts: bytes):
                                        # try direct json
                                        try:
                                            return json.loads(bts.decode('utf-8', errors='ignore'))
                                        except Exception:
                                            pass
                                        # try gzip
                                        try:
                                            txt = gzip.decompress(bts).decode('utf-8', errors='ignore')
                                            return json.loads(txt)
                                        except Exception:
                                            pass
                                        # try zlib
                                        try:
                                            txt = zlib.decompress(bts).decode('utf-8', errors='ignore')
                                            return json.loads(txt)
                                        except Exception:
                                            pass
                                        # not JSON; return raw bytes for possible protobuf parsing
                                        return bts

                                    # If raw_data is bytes, attempt to parse or hand off to proto
                                    if isinstance(raw_data, bytes):
                                        parsed = try_parse_bytes(raw_data)
                                        data = parsed
                                    elif isinstance(raw_data, str):
                                        # try JSON in the string first
                                        try:
                                            data = json.loads(raw_data)
                                        except Exception:
                                            # maybe base64-encoded protobuf or compressed payload
                                            try:
                                                b = base64.b64decode(raw_data)
                                                parsed = try_parse_bytes(b)
                                                data = parsed
                                                # if parsed returned raw bytes (likely protobuf), save sample and attempt parse
                                                if isinstance(parsed, (bytes, bytearray)):
                                                    # write sample binary to disk for offline analysis
                                                    try:
                                                        idx = int(time.time() * 1000)
                                                        with open(f'mexc_sample_{idx}.bin', 'wb') as fh:
                                                            fh.write(parsed)
                                                    except Exception:
                                                        pass
                                                    # attempt to parse via generated mexc_proto if present
                                                    try:
                                                        proto_mod = importlib.import_module('mexc_proto')
                                                        # try to find a suitable message class by name heuristics
                                                        for name, objv in inspect.getmembers(proto_mod):
                                                            if inspect.isclass(objv) and name.lower().find('depth') >= 0:
                                                                try:
                                                                    inst = objv()
                                                                    if hasattr(inst, 'ParseFromString'):
                                                                        inst.ParseFromString(parsed)
                                                                        # convert protobuf Message to a plain dict so downstream
                                                                        # code can treat it like JSON (asks/bids fields, etc.)
                                                                        parsed_dict = None
                                                                        try:
                                                                            # prefer the official helper if available
                                                                            from google.protobuf.json_format import MessageToDict
                                                                            parsed_dict = MessageToDict(inst, preserving_proto_field_name=True)
                                                                        except Exception:
                                                                            parsed_dict = None

                                                                        if parsed_dict:
                                                                            data = parsed_dict
                                                                        else:
                                                                            # fallback: try a lightweight field extraction
                                                                            try:
                                                                                # inst is a protobuf Message with ListFields()
                                                                                fd = {}
                                                                                for field, val in inst.ListFields():
                                                                                    # convert nested messages/lists to Python types conservatively
                                                                                    try:
                                                                                        fd[field.name] = val
                                                                                    except Exception:
                                                                                        fd[field.name] = str(val)
                                                                                data = fd
                                                                            except Exception:
                                                                                # last resort: expose the proto instance for offline inspection
                                                                                data = {'_proto_type': name, '_proto_obj': inst}
                                                                        break
                                                                except Exception:
                                                                    continue
                                                    except Exception:
                                                        pass
                                            except Exception:
                                                data = None
                                    else:
                                        data = raw_data

                                    # derive symbol: try topic or data fields
                                    sym = ''
                                    topic = None
                                    if isinstance(obj, dict):
                                        topic = obj.get('channel') or obj.get('ch') or obj.get('topic')
                                        if isinstance(topic, str) and '@' in topic:
                                            parts = topic.split('@')
                                            for p in reversed(parts):
                                                if p and p.isupper():
                                                    sym = p
                                                    break
                                    if not sym and isinstance(data, dict):
                                        sym = (data.get('symbol') or data.get('s') or data.get('symbolName') or '').upper()
                                    key = sym.replace('-', '').replace('/', '') if sym else ''

                                    asks = None
                                    bids = None
                                    if isinstance(data, dict):
                                        if 'asks' in data and 'bids' in data:
                                            asks = data.get('asks') or []
                                            bids = data.get('bids') or []
                                        elif 'a' in data and 'b' in data:
                                            asks = data.get('a') or []
                                            bids = data.get('b') or []
                                        elif 'depth' in data and isinstance(data.get('depth'), dict):
                                            asks = data.get('depth').get('asks') or []
                                            bids = data.get('depth').get('bids') or []
                                        elif 'data' in data and isinstance(data.get('data'), dict):
                                            nested = data.get('data')
                                            if 'asks' in nested and 'bids' in nested:
                                                asks = nested.get('asks') or []
                                                bids = nested.get('bids') or []

                                    if key and (asks is not None or bids is not None):
                                        try:
                                            lm = self._levels.setdefault(key, {'asks': {}, 'bids': {}})
                                            if asks:
                                                new_asks = {}
                                                for a in asks:
                                                    try:
                                                        if isinstance(a, (list, tuple)) and len(a) >= 2:
                                                            p = float(a[0]); q = float(a[1]); new_asks[p] = q
                                                        elif isinstance(a, str):
                                                            parts = a.split(',')
                                                            p = float(parts[0]); q = float(parts[1]); new_asks[p] = q
                                                    except Exception:
                                                        continue
                                                if new_asks:
                                                    lm['asks'] = new_asks
                                            if bids:
                                                new_bids = {}
                                                for b in bids:
                                                    try:
                                                        if isinstance(b, (list, tuple)) and len(b) >= 2:
                                                            p = float(b[0]); q = float(b[1]); new_bids[p] = q
                                                        elif isinstance(b, str):
                                                            parts = b.split(',')
                                                            p = float(parts[0]); q = float(parts[1]); new_bids[p] = q
                                                    except Exception:
                                                        continue
                                                if new_bids:
                                                    lm['bids'] = new_bids

                                            a_map = self._levels.get(key, {}).get('asks', {})
                                            b_map = self._levels.get(key, {}).get('bids', {})
                                            a_list = sorted(((p, q) for p, q in a_map.items()), key=lambda x: x[0])[:200]
                                            b_list = sorted(((p, q) for p, q in b_map.items()), key=lambda x: x[0], reverse=True)[:200]
                                            self._books[key] = {'asks': a_list, 'bids': b_list, 'timestamp': time.time()}
                                            self._ts = time.time()
                                        except Exception:
                                            pass
                                except Exception:
                                    continue

                        # run receiver in background task
                        recv_task = asyncio.create_task(_recv_loop())

                        # ping periodically to keep connection alive (docs: send ping or similar)
                        try:
                            while self._running and not recv_task.done():
                                try:
                                    await ws.send(json.dumps({'method': 'PING', 'id': int(time.time() * 1000)}))
                                except Exception:
                                    # ignore ping failures; recv loop will detect closure
                                    pass
                                await asyncio.sleep(15)
                        finally:
                            try:
                                recv_task.cancel()
                            except Exception:
                                pass

                except Exception:
                    # backoff before reconnecting
                    await asyncio.sleep(min(reconnect_backoff, 30.0))
                    reconnect_backoff = min(reconnect_backoff * 2.0, 30.0)

        # launch one connection task per chunk
        tasks = [asyncio.create_task(_run_conn(chunk)) for chunk in chunks]
        if tasks:
            # wait until stop requested
            try:
                while self._running:
                    await asyncio.sleep(0.5)
            finally:
                for t in tasks:
                    try:
                        t.cancel()
                    except Exception:
                        pass

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        key = symbol.upper().replace('/', '').replace('-', '')
        b = self._books.get(key)
        if not b:
            return {'asks': [], 'bids': []}
        asks = b.get('asks', [])[:depth]
        bids = b.get('bids', [])[:depth]
        return {'asks': asks, 'bids': bids}

    def get_tickers(self) -> Dict[str, Any]:
        out = {}
        for key, v in list(self._books.items()):
            try:
                asks = v.get('asks', [])
                bids = v.get('bids', [])
                last = None
                if bids:
                    last = bids[0][0]
                elif asks:
                    last = asks[0][0]
                if last is None:
                    continue
                # recover base/quote by heuristic (assume last 4/3 chars are quote)
                s = key
                common_quotes = ['USDT', 'USDC', 'USDT', 'BTC', 'ETH', 'USD']
                quote = None
                base = None
                for q in common_quotes:
                    if s.endswith(q) and len(s) > len(q):
                        quote = q
                        base = s[:-len(q)]
                        break
                if quote is None:
                    quote = s[-3:]
                    base = s[:-3]
                if not base:
                    continue
                symbol_std = f"{base}/{quote}"
                out[symbol_std] = {'last': last, 'timestamp': v.get('timestamp')}
            except Exception:
                continue
        return out
