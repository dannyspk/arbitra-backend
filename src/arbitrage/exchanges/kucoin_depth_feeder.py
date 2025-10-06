from __future__ import annotations

import asyncio
import json
import time
import threading
from typing import Dict, Any, List

try:
    import websockets
except Exception:
    websockets = None


class KucoinDepthFeeder:
    """Simple KuCoin L2 feeder that maintains top-of-book snapshots.

    Note: KuCoin uses a slightly different websocket API. For this lightweight
    feeder we attempt to subscribe to public depth channels using the
    combined stream when possible. This implementation keeps the same
    interface as BinanceDepthFeeder: start(), stop(), get_order_book(),
    get_tickers().
    """

    def __init__(self, symbols: List[str]):
        # store normalized symbol names (e.g. BTCUSDT)
        self.symbols = [s.upper().replace('/', '').replace('-', '') for s in symbols]
        self._books: Dict[str, Dict[str, List]] = {}
        # per-symbol price level maps for incremental updates
        self._levels: Dict[str, Dict[str, Dict[float, float]]] = {}
        # per-symbol last applied sequence number
        self._seq: Dict[str, int] = {}
        self._ts = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop = None

    def start(self):
        if websockets is None:
            raise ImportError('websockets package is required for KucoinDepthFeeder')
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
        # KuCoin public WS requires a short REST handshake to obtain an endpoint
        # and token (see /api/v1/bullet-public). Use that endpoint to connect and
        # subscribe to per-symbol level2 topics. Symbols must be hyphenated (BASE-QUOTE)
        # for KuCoin topics (e.g., BTC-USDT).
        # Build a helper to fetch the websocket endpoint/token.
        def _get_bullet_endpoint():
            try:
                import urllib.request as _urlreq
                # KuCoin docs show POST /api/v1/bullet-public to obtain an endpoint + token
                req = _urlreq.Request('https://api.kucoin.com/api/v1/bullet-public', data=b'', headers={'User-Agent': 'arb-kucoin-feeder/1.0', 'Content-Type': 'application/json'}, method='POST')
                with _urlreq.urlopen(req, timeout=5) as resp:
                    raw = resp.read()
                    obj = json.loads(raw.decode('utf-8'))
                    data = obj.get('data') or {}
                    inst = data.get('instanceServers') or []
                    token = data.get('token')
                    if inst and isinstance(inst, list):
                        endpoint = inst[0].get('endpoint')
                        return endpoint, token
            except Exception:
                return None, None
            return None, None

        def _fetch_snapshot_for(sym_hyphen: str):
            """Fetch REST L2 snapshot for hyphenated symbol (e.g. BTC-USDT).

            Returns tuple (levels_map, seq) where levels_map={'asks':{price:qty}, 'bids':{price:qty}}
            and seq is an int sequence value if present.
            """
            try:
                import urllib.request as _urlreq
                url = f'https://api.kucoin.com/api/v1/market/orderbook/level2?symbol={sym_hyphen}&limit=200'
                req = _urlreq.Request(url, headers={'User-Agent': 'arb-kucoin-feeder/1.0'})
                with _urlreq.urlopen(req, timeout=5) as resp:
                    raw = resp.read()
                    obj = json.loads(raw.decode('utf-8'))
                    data = obj.get('data') or {}
                    asks = data.get('asks') or []
                    bids = data.get('bids') or []
                    seq = data.get('sequence') or data.get('sequenceStart') or data.get('sequenceEnd') or 0
                    try:
                        seq = int(seq)
                    except Exception:
                        seq = 0
                    a_map = {}
                    b_map = {}
                    for a in asks:
                        try:
                            p = float(a[0]) if isinstance(a, (list, tuple)) else float(a)
                            q = float(a[1]) if isinstance(a, (list, tuple)) and len(a) > 1 else 0.0
                            a_map[p] = q
                        except Exception:
                            continue
                    for b in bids:
                        try:
                            p = float(b[0]) if isinstance(b, (list, tuple)) else float(b)
                            q = float(b[1]) if isinstance(b, (list, tuple)) and len(b) > 1 else 0.0
                            b_map[p] = q
                        except Exception:
                            continue
                    return {'asks': a_map, 'bids': b_map}, seq
            except Exception:
                return {'asks': {}, 'bids': {}}, 0

        # Reconnect loop: try to keep websocket alive and refresh token when needed
        backoff = 1.0
        while self._running:
            base, token = _get_bullet_endpoint()
            if not base:
                base = 'wss://ws-api.kucoin.com/endpoint'

            # track token acquisition time so we can refresh before expiry
            token_acquired = time.time()

            # build ws url (token appended as query when provided)
            ws_url = base
            if token:
                try:
                    if '?' in base:
                        ws_url = base + '&token=' + token
                    else:
                        ws_url = base + '?token=' + token
                except Exception:
                    ws_url = base

            try:
                async with websockets.connect(ws_url, max_size=None) as ws:
                    # wait for welcome (server may send welcome/pingInterval)
                    ping_interval = 20.0
                    connect_id = None
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        try:
                            obj = json.loads(msg)
                            if isinstance(obj, dict) and obj.get('type') == 'welcome':
                                # welcome may include pingInterval or other info
                                ping_interval = float(obj.get('pingInterval') or (obj.get('data') or {}).get('pingInterval') or ping_interval)
                                connect_id = obj.get('id') or (obj.get('data') or {}).get('connectId') or token
                        except Exception:
                            pass
                    except Exception:
                        # no welcome received; continue but use default ping interval
                        pass

                    # start ping task
                    async def _ping_task(ws_conn, interval):
                        while self._running:
                            try:
                                await asyncio.sleep(interval)
                                ping_msg = {'id': str(int(time.time()*1000)), 'type': 'ping'}
                                try:
                                    await ws_conn.send(json.dumps(ping_msg))
                                except Exception:
                                    break
                            except Exception:
                                break

                    ping_runner = asyncio.create_task(_ping_task(ws, ping_interval))

                    # attempt to subscribe only after welcome (or immediate if none)
                    common_quotes = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'USD']
                    try:
                        for s in self.symbols:
                            topic_sym = s
                            for q in common_quotes:
                                if s.endswith(q):
                                    topic_sym = f"{s[:-len(q)]}-{q}"
                                    break
                            sub = {
                                'id': str(int(time.time()*1000)),
                                'type': 'subscribe',
                                'topic': f'/market/level2:{topic_sym}',
                                'response': True,
                            }
                            if connect_id:
                                sub['connectId'] = connect_id
                            elif token:
                                sub['connectId'] = token
                            try:
                                await ws.send(json.dumps(sub))
                            except Exception:
                                continue
                    except Exception:
                        pass

                    # process incoming messages until stopped
                    raw_log = []
                    start_ts = time.time()
                    while self._running:
                        # refresh token if it's getting close to 24h
                        try:
                            if token and (time.time() - token_acquired) > (23 * 3600):
                                # token expires soon -> break to reconnect and fetch new token
                                break
                        except Exception:
                            pass

                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            # If websocket is quiet, periodically refresh a small
                            # REST snapshot so prices don't become stale. Rate-limit
                            # this to at most once every 2s.
                            try:
                                now = time.time()
                                last = getattr(self, '_last_poll_refresh', 0)
                                if now - last > 2.0:
                                    self._last_poll_refresh = now
                                    for s in list(self.symbols):
                                        try:
                                            topic_sym = s
                                            for q in common_quotes:
                                                if s.endswith(q):
                                                    topic_sym = f"{s[:-len(q)]}-{q}"
                                                    break
                                            snap, seq = _fetch_snapshot_for(topic_sym)
                                            sym_key = topic_sym.replace('-', '')
                                            self._levels[sym_key] = {'asks': snap.get('asks', {}), 'bids': snap.get('bids', {})}
                                            a_map = self._levels.get(sym_key, {}).get('asks', {})
                                            b_map = self._levels.get(sym_key, {}).get('bids', {})
                                            a_list = sorted(((p, q) for p, q in a_map.items()), key=lambda x: x[0])[:200]
                                            b_list = sorted(((p, q) for p, q in b_map.items()), key=lambda x: x[0], reverse=True)[:200]
                                            ts = time.time()
                                            self._books[sym_key] = {'asks': a_list, 'bids': b_list, 'timestamp': ts}
                                            self._ts = ts
                                            try:
                                                if seq:
                                                    self._seq[sym_key] = int(seq)
                                            except Exception:
                                                pass
                                        except Exception:
                                            continue
                            except Exception:
                                pass
                            continue
                        try:
                            # capture raw messages for debugging (short-lived)
                            if len(raw_log) < 200 and (time.time() - start_ts) < 30:
                                try:
                                    raw_log.append(msg)
                                except Exception:
                                    pass
                            elif len(raw_log) == 200 or (time.time() - start_ts) >= 30:
                                try:
                                    with open('kucoin_raw_messages.log', 'w', encoding='utf-8') as fh:
                                        for m in raw_log:
                                            try:
                                                fh.write(m if isinstance(m, str) else str(m))
                                                fh.write('\n')
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                            # KuCoin messages may wrap payloads under 'data' or 'body'
                            obj = json.loads(msg)
                            data = obj.get('data') or obj.get('body') or obj
                            # determine symbol: try topic first (/market/level2:BTC-USDT)
                            sym_hyphen = ''
                            topic = obj.get('topic')
                            if isinstance(topic, str) and ':' in topic:
                                sym_hyphen = topic.split(':')[-1].upper()
                            if not sym_hyphen:
                                sym_hyphen = (data.get('symbol') or data.get('s') or '').upper()
                            sym = sym_hyphen.replace('-', '')

                            ts = time.time()
                            if not sym:
                                continue

                            # ensure we have a snapshot/levels for this symbol
                            if sym not in self._levels or self._seq.get(sym, 0) == 0:
                                snap, seq = _fetch_snapshot_for(sym_hyphen)
                                self._levels[sym] = {'asks': snap.get('asks', {}), 'bids': snap.get('bids', {})}
                                self._seq[sym] = seq

                            # sequence-aware diff application
                            try:
                                seq_start = None
                                seq_end = None
                                try:
                                    seq_start = int(data.get('sequenceStart')) if data.get('sequenceStart') is not None else None
                                except Exception:
                                    seq_start = None
                                try:
                                    seq_end = int(data.get('sequenceEnd')) if data.get('sequenceEnd') is not None else None
                                except Exception:
                                    seq_end = None

                                if seq_start is not None and self._seq.get(sym, 0):
                                    expected_next = self._seq.get(sym, 0) + 1
                                    if seq_start > expected_next:
                                        try:
                                            snap, seq = _fetch_snapshot_for(sym_hyphen)
                                            self._levels[sym] = {'asks': snap.get('asks', {}), 'bids': snap.get('bids', {})}
                                            self._seq[sym] = seq
                                        except Exception:
                                            pass
                                        continue
                                    if seq_start <= self._seq.get(sym, 0):
                                        continue

                                changes = data.get('changes') or {}
                                for side in ('asks', 'bids'):
                                    clist = changes.get(side) or []
                                    for ch in clist:
                                        try:
                                            if isinstance(ch, (list, tuple)) and len(ch) >= 2:
                                                p = float(ch[0])
                                                q = float(ch[1])
                                                lm = self._levels[sym].setdefault(side, {})
                                                if q == 0.0:
                                                    lm.pop(p, None)
                                                else:
                                                    lm[p] = q
                                        except Exception:
                                            continue

                                if seq_end is not None:
                                    try:
                                        self._seq[sym] = int(seq_end)
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        self._seq[sym] = self._seq.get(sym, 0) + 1
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                            # rebuild top lists (asks sorted asc, bids desc) limited to 200
                            try:
                                a_map = self._levels.get(sym, {}).get('asks', {})
                                b_map = self._levels.get(sym, {}).get('bids', {})
                                a_list = sorted(((p, q) for p, q in a_map.items()), key=lambda x: x[0])[:200]
                                b_list = sorted(((p, q) for p, q in b_map.items()), key=lambda x: x[0], reverse=True)[:200]
                                self._books[sym] = {'asks': a_list, 'bids': b_list, 'timestamp': ts}
                                self._ts = ts
                            except Exception:
                                pass
                        except Exception:
                            continue

                    # cancel ping runner on exit
                    try:
                        ping_runner.cancel()
                    except Exception:
                        pass
                    # if we exit while self._running inner loop, attempt reconnect after short backoff
                    backoff = 1.0
                    if not self._running:
                        return
            except Exception:
                # connection failed; backoff then retry
                try:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                except Exception:
                    pass
                continue
        return

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
                # key is normalized like 'BTCUSDT' -> recover BASE/QUOTE
                s = key
                common_quotes = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'USD']
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
