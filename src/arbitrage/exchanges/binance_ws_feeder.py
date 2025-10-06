"""Lightweight Binance websocket feeder.

Maintains an in-memory ticker snapshot map compatible with CCXTExchange.get_tickers()
by storing dict[symbol] = { 'last': price, 'info': {...} } and exposing get_tickers().

This is intentionally minimal: it connects to Binance combined trade streams and updates
the cache with last trade price and timestamp.
"""
from __future__ import annotations

import asyncio
import json
import time
import threading
import os
from typing import Dict, Any

try:
    import websockets
except Exception:
    websockets = None


class BinanceWSFeeder:
    def __init__(self, symbols: list[str]):
        self.symbols = [s.upper().replace('/', '').replace('-', '') for s in symbols]
        self._tickers_cache: Dict[str, Dict[str, Any]] = {}
        self._tickers_cache_ts = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self):
        if websockets is None:
            raise ImportError('websockets package is required for BinanceWSFeeder')
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        try:
            if self._loop:
                # allow the background loop to exit gracefully; avoid force-stopping
                # which can leave pending tasks. We simply clear the running flag
                # and wait for the thread to finish.
                pass
        except Exception:
            pass
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
        streams = '/'.join([f"{s.lower()}@trade" for s in self.symbols])
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
                        price = data.get('p')
                        ts = time.time()
                        if sym and price is not None:
                            try:
                                p = float(price)
                                self._tickers_cache[sym.replace('/', '')] = {'last': p, 'timestamp': ts}
                                self._tickers_cache_ts = ts
                            except Exception:
                                pass
                    except Exception:
                        continue
        except Exception:
            # network error or closed socket
            return

    def get_tickers(self) -> Dict[str, Any]:
        # return map symbol -> ticker-like dict maintaining ccxt short cache shape
        out = {}
        for sym, info in self._tickers_cache.items():
            try:
                # format symbol into BASE/QUOTE. Try common quotes first.
                s = sym.upper()
                # common quote tokens ordered by length to match USDT before USD
                common_quotes = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'USD', 'TUSD']
                quote = None
                base = None
                for q in common_quotes:
                    if s.endswith(q) and len(s) > len(q):
                        quote = q
                        base = s[: -len(q)]
                        break
                if quote is None:
                    # fallback: split last 3 chars
                    quote = s[-3:]
                    base = s[:-3]
                symbol_std = f"{base}/{quote}"
                out[symbol_std] = {'last': info.get('last'), 'timestamp': info.get('timestamp')}
            except Exception:
                continue
        return out
