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

class BinanceDepthFeeder:
    """Feeder that maintains a lightweight L2 snapshot for Binance symbols.

    It subscribes to the combined depth streams (e.g. symbol@depth) and
    updates an in-memory orderbook. For simplicity it treats incoming
    depth update messages as full snapshots for the symbol's top of book.
    This is sufficient to provide fast approximate VWAP and available notional
    for scanner candidate validation.
    """

    def __init__(self, symbols: List[str]):
        # store normalized symbol names (e.g. BTCUSDT)
        self.symbols = [s.upper().replace('/', '').replace('-', '') for s in symbols]
        self._books: Dict[str, Dict[str, List]] = {}
        self._ts = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop = None

    def start(self):
        if websockets is None:
            raise ImportError('websockets package is required for BinanceDepthFeeder')
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
        streams = '/'.join([f"{s.lower()}@depth@100ms" for s in self.symbols])
        uri = f"wss://stream.binance.com:9443/stream?streams={streams}"
        try:
            async with websockets.connect(uri, max_size=None) as ws:
                while self._running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        obj = json.loads(msg)
                        data = obj.get('data', {})
                        sym = (data.get('s') or '').upper()
                        asks = data.get('a') or []
                        bids = data.get('b') or []
                        ts = time.time()
                        if sym:
                            # convert asks/bids into [(price,size), ...]
                            a_list = []
                            b_list = []
                            for a in asks:
                                try:
                                    p = float(a[0])
                                    q = float(a[1])
                                    a_list.append((p, q))
                                except Exception:
                                    continue
                            for b in bids:
                                try:
                                    p = float(b[0])
                                    q = float(b[1])
                                    b_list.append((p, q))
                                except Exception:
                                    continue
                            # sort asks ascending and bids descending
                            a_list = sorted(a_list, key=lambda x: x[0])
                            b_list = sorted(b_list, key=lambda x: x[0], reverse=True)
                            self._books[sym] = {'asks': a_list, 'bids': b_list, 'timestamp': ts}
                            self._ts = ts
                    except Exception:
                        continue
        except Exception:
            return

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        # Accept 'BASE/QUOTE' or 'BASE-QUOTE' or 'BASEQUOTE' forms
        key = symbol.upper().replace('/', '').replace('-', '')
        b = self._books.get(key)
        if not b:
            return {'asks': [], 'bids': []}
        asks = b.get('asks', [])[:depth]
        bids = b.get('bids', [])[:depth]
        return {'asks': asks, 'bids': bids}

    def get_tickers(self) -> Dict[str, Any]:
        # provide ticker-like last prices derived from top of book
        out = {}
        for key, v in self._books.items():
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
                # format symbol back to BASE/QUOTE
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
                symbol_std = f"{base}/{quote}"
                out[symbol_std] = {'last': last, 'timestamp': v.get('timestamp')}
            except Exception:
                continue
        return out
