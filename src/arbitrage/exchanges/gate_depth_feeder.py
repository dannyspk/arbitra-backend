from __future__ import annotations

import asyncio
import json
import time
import threading
from typing import Dict, List, Optional

try:
    import websockets
except Exception:
    websockets = None


class GateDepthFeeder:
    """Lightweight Gate.io feeder for public spot tickers and book tickers."""

    @staticmethod
    def _normalize_in(s: str) -> str:
        if not s:
            return ''
        return s.strip().upper().replace('/', '_').replace('-', '_')

    @staticmethod
    def _normalize_out(s: str) -> str:
        return s.replace('_', '/').upper()

    @staticmethod
    def _to_float(x):
        try:
            if x is None:
                return None
            return float(x)
        except Exception:
            return None

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        *,
        retry_timeout: float = 6.0,
        max_retries: int = 2,
        chunk_size: int = 5,
        chunk_pause: float = 3.0,
    ):
        self._symbols = [] if symbols is None else [self._normalize_in(s) for s in symbols]
        self._tickers: Dict[str, Dict] = {}
        self._book_tickers: Dict[str, Dict] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connected: bool = False
        self.last_update_ts: Optional[float] = None
        self._seen_first: set = set()
        self._sub_state: Dict[str, Dict] = {}
        self._retry_timeout: float = float(retry_timeout)
        self._max_retries: int = int(max_retries)
        self._chunk_size: int = int(chunk_size)
        self._chunk_pause: float = float(chunk_pause)
        self._exhausted: set = set()

    def start(self):
        if websockets is None:
            raise ImportError('websockets package is required for GateDepthFeeder')
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_main())
        except Exception:
            pass

    async def _ws_main(self):
        base = 'wss://api.gateio.ws/ws/v4/'

        payload_symbols = [s for s in self._symbols if s] or ['BTC_USDT', 'ETH_USDT']
        print(f"GateDepthFeeder: will attempt to subscribe to payload_symbols={payload_symbols}")

        # Optional REST presence filtering (best effort)
        try:
            import requests
            try:
                resp = requests.get('https://api.gateio.ws/api/v4/spot/currency_pairs', timeout=5)
                if resp.ok:
                    data = resp.json()
                    supported = set()
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                idv = item.get('id') or item.get('currency_pair') or item.get('symbol')
                                if idv:
                                    supported.add(str(idv).upper())
                    if supported:
                        before = len(payload_symbols)
                        filtered = [s for s in payload_symbols if s.upper() in supported]
                        if filtered:
                            payload_symbols = filtered
                            after = len(payload_symbols)
                            print(f'GateDepthFeeder: filtered subscription list by REST: {before} -> {after} pairs')
                        else:
                            print('GateDepthFeeder: REST supported list returned but intersection was empty; skipping filter')
            except Exception as e:
                print('GateDepthFeeder: error fetching supported pairs from Gate REST:', e)
        except Exception:
            pass

        def build_sub(channel: str, symbols: List[str]) -> str:
            return json.dumps({
                'time': int(time.time()),
                'channel': channel,
                'event': 'subscribe',
                'payload': symbols,
            })

        def chunked(iterable: List[str], size: int) -> List[List[str]]:
            if size <= 0:
                return [list(iterable)]
            return [list(iterable[i:i + size]) for i in range(0, len(iterable), size)]

        backoff = 1.0
        while self._running:
            try:
                print("GateDepthFeeder: attempting websocket connection to Gate")
                async with websockets.connect(
                    base,
                    max_size=None,
                    ping_interval=None,   # rely on server heartbeats
                    ping_timeout=None,
                    close_timeout=5,
                ) as ws:
                    print("GateDepthFeeder: websocket connected")
                    self._connected = True
                    backoff = 1.0

                    # Send subscriptions in chunks
                    try:
                        for chunk in chunked(payload_symbols, self._chunk_size):
                            print(f"GateDepthFeeder: sending subscribe spot.tickers chunk: {chunk}")
                            await ws.send(build_sub('spot.tickers', chunk))
                            await asyncio.sleep(self._chunk_pause)
                    except Exception as e:
                        print(f"GateDepthFeeder: exception while sending spot.tickers subs: {e}")

                    try:
                        for chunk in chunked(payload_symbols, self._chunk_size):
                            print(f"GateDepthFeeder: sending subscribe spot.book_ticker chunk: {chunk}")
                            await ws.send(build_sub('spot.book_ticker', chunk))
                            await asyncio.sleep(self._chunk_pause)
                    except Exception as e:
                        print(f"GateDepthFeeder: exception while sending spot.book_ticker subs: {e}")

                    # Seed sub-state
                    now = time.time()
                    for s in payload_symbols:
                        self._sub_state[s] = {'last_sub': now, 'retries': 0}

                    # Receive loop
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            await asyncio.sleep(0)
                            # periodic retry check below
                        except Exception as e:
                            try:
                                exc_mod = getattr(websockets, 'exceptions', None)
                                conn_cls = getattr(exc_mod, 'ConnectionClosed', None)
                                if conn_cls is not None and isinstance(e, conn_cls):
                                    print(f"GateDepthFeeder: websocket closed code={getattr(e, 'code', None)} reason={getattr(e, 'reason', None)}")
                            except Exception:
                                pass
                            break
                        else:
                            # handle message
                            try:
                                obj = json.loads(msg)
                            except Exception:
                                continue

                            # Handle ping/pong
                            try:
                                if isinstance(obj, dict) and ('ping' in obj or obj.get('channel') == 'spot.pong'):
                                    if 'ping' in obj:
                                        try:
                                            await ws.send(json.dumps({'pong': obj.get('ping')}))
                                        except Exception:
                                            pass
                                    continue
                            except Exception:
                                pass

                            ch = obj.get('channel') if isinstance(obj, dict) else None
                            ev = obj.get('event') if isinstance(obj, dict) else None
                            res = obj.get('result') if isinstance(obj, dict) else None

                            # Log non-update server messages (acks/errors)
                            if ev != 'update':
                                try:
                                    print(f"GateDepthFeeder: server message channel={ch} event={ev} resultType={type(res).__name__}")
                                except Exception:
                                    pass

                            # --- spot.tickers ---
                            if ch == 'spot.tickers' and ev == 'update' and res is not None:
                                items = res if isinstance(res, list) else [res]
                                for it in items:
                                    if not isinstance(it, dict):
                                        continue
                                    cp = it.get('currency_pair') or it.get('symbol') or it.get('s')
                                    if not cp:
                                        continue
                                    out = self._normalize_out(str(cp).upper())
                                    last = self._to_float(it.get('last'))
                                    bid = self._to_float(it.get('highest_bid'))
                                    ask = self._to_float(it.get('lowest_ask'))
                                    # Some payloads might use 'b'/'a' like book_ticker; accept them as fallback
                                    if bid is None:
                                        bid = self._to_float(it.get('b'))
                                    if ask is None:
                                        ask = self._to_float(it.get('a'))

                                    print(f"GateDepthFeeder: received spot.tickers update for {out}: last={last} bid={bid} ask={ask}")
                                    if out not in self._seen_first:
                                        self._seen_first.add(out)
                                        print(f"GateDepthFeeder: first ticker update for {out}")
                                    self._tickers[out] = {'last': last, 'bid': bid, 'ask': ask, 'ts': time.time()}
                                    # mark satisfied
                                    k_in = self._normalize_in(out)
                                    st = self._sub_state.get(k_in)
                                    if st:
                                        st['last_sub'] = time.time()
                                    self.last_update_ts = time.time()

                            # --- spot.book_ticker ---
                            if ch == 'spot.book_ticker' and ev == 'update' and res is not None:
                                items = res if isinstance(res, list) else [res]
                                for it in items:
                                    if not isinstance(it, dict):
                                        continue
                                    cp = it.get('s') or it.get('currency_pair') or it.get('symbol')
                                    if not cp:
                                        continue
                                    out = self._normalize_out(str(cp).upper())
                                    bid = self._to_float(it.get('b') if 'b' in it else it.get('highest_bid'))
                                    bid_sz = self._to_float(it.get('B') if 'B' in it else it.get('bid_size'))
                                    ask = self._to_float(it.get('a') if 'a' in it else it.get('lowest_ask'))
                                    ask_sz = self._to_float(it.get('A') if 'A' in it else it.get('ask_size'))

                                    print(f"GateDepthFeeder: received spot.book_ticker for {out}: bid={bid} ask={ask} bid_sz={bid_sz} ask_sz={ask_sz}")
                                    if out not in self._seen_first:
                                        self._seen_first.add(out)
                                        print(f"GateDepthFeeder: first book_ticker update for {out}")
                                    self._book_tickers[out] = {'bid': bid, 'bid_sz': bid_sz, 'ask': ask, 'ask_sz': ask_sz, 'ts': time.time()}
                                    k_in = self._normalize_in(out)
                                    st = self._sub_state.get(k_in)
                                    if st:
                                        st['last_sub'] = time.time()
                                    self.last_update_ts = time.time()

                        # periodic resubscribe for missing symbols
                        try:
                            now = time.time()
                            missing = []
                            for s in list(payload_symbols):
                                out_name = self._normalize_out(s)
                                if out_name and out_name not in self._seen_first:
                                    st = self._sub_state.get(s)
                                    if st is None:
                                        self._sub_state[s] = {'last_sub': now, 'retries': 0}
                                        continue
                                    elapsed = now - float(st.get('last_sub', 0))
                                    retries = int(st.get('retries', 0))
                                    if elapsed > self._retry_timeout and retries < self._max_retries:
                                        missing.append(s)
                            if missing:
                                print(f"GateDepthFeeder: resubscribing for missing symbols -> {missing}")
                                for chunk in chunked(missing, self._chunk_size):
                                    try:
                                        await ws.send(build_sub('spot.tickers', chunk))
                                    except Exception as e:
                                        print(f"GateDepthFeeder: retry spot.tickers failed: {e}")
                                    try:
                                        await ws.send(build_sub('spot.book_ticker', chunk))
                                    except Exception as e:
                                        print(f"GateDepthFeeder: retry spot.book_ticker failed: {e}")
                                    await asyncio.sleep(0.2)
                                for s in missing:
                                    st = self._sub_state.setdefault(s, {'last_sub': now, 'retries': 0})
                                    st['retries'] = int(st.get('retries', 0)) + 1
                                    st['last_sub'] = now
                                    if st['retries'] >= self._max_retries and s not in self._exhausted:
                                        self._exhausted.add(s)
                                        print(f"GateDepthFeeder: max retries reached for {s}; no more auto-resubscribes")
                        except Exception:
                            pass

                    # connection closed; mark state
                    self._connected = False
            except Exception as e:
                try:
                    print(f"GateDepthFeeder: websocket loop exception: {e}")
                except Exception:
                    pass
                self._connected = False
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

    def get_tickers(self) -> Dict[str, Dict]:
        out: Dict[str, Dict] = {}
        tks = dict(self._tickers)
        bks = dict(self._book_tickers)
        keys = set(tks.keys()) | set(bks.keys())
        for k in keys:
            if k in tks and isinstance(tks.get(k), dict):
                val = dict(tks.get(k))
                last = val.get('last')
                if last is None and k in bks and isinstance(bks.get(k), dict):
                    bk = bks.get(k)
                    bid = self._to_float(bk.get('bid'))
                    ask = self._to_float(bk.get('ask'))
                    if bid is not None and ask is not None:
                        val['last'] = (bid + ask) / 2.0
                    elif bid is not None:
                        val['last'] = bid
                    elif ask is not None:
                        val['last'] = ask
                out[k] = val
            elif k in bks and isinstance(bks.get(k), dict):
                bk = bks.get(k)
                bid = self._to_float(bk.get('bid'))
                ask = self._to_float(bk.get('ask'))
                info = {'last': None, 'bid': bid, 'ask': ask, 'ts': bk.get('ts')}
                if bid is not None and ask is not None:
                    info['last'] = (bid + ask) / 2.0
                elif bid is not None:
                    info['last'] = bid
                elif ask is not None:
                    info['last'] = ask
                out[k] = info
        return out

    def get_status(self) -> Dict:
        try:
            status = 'ok' if self._connected else 'disconnected'
        except Exception:
            status = 'disconnected'
        try:
            depths = self.get_book_tickers()
        except Exception:
            depths = {}
        try:
            tickers = self.get_tickers()
        except Exception:
            tickers = {}
        try:
            ts = float(self.last_update_ts) if self.last_update_ts is not None else None
        except Exception:
            ts = None
        return {'feeder': 'gate', 'status': status, 'bids': {sym: info.get('bid') for sym, info in (depths or {}).items()}, 'last_update_ts': ts}


    def get_book_tickers(self) -> Dict[str, Dict]:
        return dict(self._book_tickers)

    def get_order_book(self, symbol: str):
        return None
