from __future__ import annotations

from typing import Dict, Any
import os
import time
import threading
import asyncio

from .base import Exchange, Ticker

try:
    import ccxtpro as ccxtpro  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ccxtpro = None


class CCXTProExchange:
    """A thin adapter for ccxt.pro (async websocket-capable client).

    This is a best-effort prototype to help migrate to ccxt.pro. It runs an
    asyncio event loop in a background thread and exposes a synchronous
    compatibility surface similar to the existing CCXTExchange.

    Notes:
    - ccxt.pro must be installed (pip install ccxtpro). If not present the
      constructor will raise ImportError.
    - This adapter focuses on providing fast ticker snapshots via websocket
      watch_tickers/watch_ticker and stores the latest snapshot in an
      instance-level cache accessible from `get_tickers()`.
    - Order-book and metadata methods fall back to the underlying REST
      methods where possible.
    """

    def __init__(self, id: str, api_key: str | None = None, secret: str | None = None, options: Dict[str, Any] | None = None):
        if ccxtpro is None:
            raise ImportError("ccxt.pro (ccxtpro) is required for CCXTProExchange. Install with `pip install ccxtpro`")
        self.name = id
        cfg = {}
        if api_key:
            cfg['apiKey'] = api_key
        if secret:
            cfg['secret'] = secret
        if options:
            cfg.update(options)

        # instantiate async client class
        exchange_cls = getattr(ccxtpro, id)
        # client needs to be created in the event loop; create placeholder
        self._client = None
        self._client_cfg = cfg

        # short-lived caches similar to CCXTExchange
        self._tickers_cache: dict | None = None
        self._tickers_cache_ts: float | None = None
        try:
            self._tickers_cache_ttl = float(os.environ.get('ARB_CCXT_TICKER_TTL', '1.0'))
        except Exception:
            self._tickers_cache_ttl = 1.0

        self._currency_cache: dict | None = None
        self._currency_cache_ts: float | None = None
        self._currency_cache_ttl = 300.0

        # background loop management
        self._loop = None
        self._thread = None
        self._start_background_loop(exchange_cls, cfg)

    def _start_background_loop(self, exchange_cls, cfg):
        # run an asyncio event loop in a dedicated thread and create the client there
        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            async def init_client():
                client = exchange_cls(cfg)
                # enableRateLimit is not always relevant for ccxt.pro but keep for parity
                try:
                    setattr(client, 'enableRateLimit', True)
                except Exception:
                    pass
                self._client = client

            loop.run_until_complete(init_client())
            # run forever; the loop will be used to schedule coroutines from sync methods
            try:
                loop.run_forever()
            finally:
                # cleanup client on shutdown
                try:
                    loop.run_until_complete(self._client.close())
                except Exception:
                    pass

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        # wait briefly for client to be created
        start = time.time()
        while self._client is None and (time.time() - start) < 2.0:
            time.sleep(0.01)

    def _run_coro_sync(self, coro, timeout: float = 2.0):
        """Schedule a coroutine on the background loop and wait for result."""
        if self._loop is None:
            raise RuntimeError('Event loop not running')
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return fut.result(timeout=timeout)
        except Exception:
            try:
                fut.cancel()
            except Exception:
                pass
            raise

    def get_tickers(self) -> Dict[str, Ticker]:
        """Return the latest ticker snapshot collected via websocket where possible.

        If no websocket data is available, fall back to a one-shot REST fetch
        executed on the background loop.
        """
        now = time.time()
        try:
            if self._tickers_cache is not None and self._tickers_cache_ts is not None and (now - self._tickers_cache_ts) < self._tickers_cache_ttl:
                data = self._tickers_cache
            else:
                async def _fetch():
                    # try watch_tickers if available (returns dict of tickers)
                    if hasattr(self._client, 'watch_tickers'):
                        try:
                            t = await self._client.watch_tickers()
                            return t
                        except Exception:
                            pass
                    # fallback to fetch_tickers
                    return await self._client.fetch_tickers()

                tks = self._run_coro_sync(_fetch(), timeout=3.0)
                self._tickers_cache = tks or {}
                self._tickers_cache_ts = time.time()
                data = self._tickers_cache
        except Exception:
            data = self._tickers_cache or {}

        out: Dict[str, Ticker] = {}
        if isinstance(data, dict):
            for symbol, info in data.items():
                try:
                    price = info.get('last') if isinstance(info, dict) else None
                    if price is None:
                        bid = info.get('bid') if isinstance(info, dict) else None
                        ask = info.get('ask') if isinstance(info, dict) else None
                        if bid and ask:
                            price = (bid + ask) / 2
                    if price is None:
                        continue
                    out[symbol] = Ticker(symbol, float(price))
                except Exception:
                    continue
        return out

    def prewarm_currency_metadata(self, timeout_seconds: float = 2.0) -> None:
        try:
            async def _fetch_all():
                cur = None
                try:
                    if hasattr(self._client, 'fetch_currencies'):
                        cur = await self._client.fetch_currencies()
                except Exception:
                    cur = None
                if cur:
                    return cur
                try:
                    markets = await self._client.fetch_markets()
                    cdict = {}
                    for m in markets:
                        try:
                            base = m.get('base') or m.get('baseId') or (m.get('symbol') or '').split('/')[0]
                            if not base:
                                continue
                            if base not in cdict:
                                cdict[base] = {'markets': []}
                            cdict[base]['markets'].append({'symbol': m.get('symbol'), 'info': m.get('info')})
                        except Exception:
                            continue
                    return cdict
                except Exception:
                    return None

            res = self._run_coro_sync(_fetch_all(), timeout=timeout_seconds)
            if res:
                self._currency_cache = res
                self._currency_cache_ts = time.time()
        except Exception:
            pass

    def get_currency_details(self, base_symbol: str) -> dict | None:
        try:
            if self._currency_cache is not None:
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = self._currency_cache.get(base) or self._currency_cache.get(base.upper()) or self._currency_cache.get(base.lower())
                if isinstance(entry, dict):
                    return entry
            # fallback to fetch_currencies once
            async def _fetch():
                if hasattr(self._client, 'fetch_currencies'):
                    return await self._client.fetch_currencies()
                return None

            res = self._run_coro_sync(_fetch(), timeout=2.0)
            if res and isinstance(res, dict):
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                return res.get(base) or res.get(base.upper()) or res.get(base.lower())
        except Exception:
            pass
        return None

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        try:
            async def _get():
                # prefer watch_order_book if available
                if hasattr(self._client, 'watch_order_book'):
                    try:
                        ob = await self._client.watch_order_book(symbol)
                        return ob
                    except Exception:
                        pass
                return await self._client.fetch_order_book(symbol, depth)

            ob = self._run_coro_sync(_get(), timeout=3.0)
            asks = []
            bids = []
            for a in ob.get('asks', [])[:depth]:
                try:
                    price = float(a[0])
                    size = float(a[1])
                    asks.append((price, size))
                except Exception:
                    continue
            for b in ob.get('bids', [])[:depth]:
                try:
                    price = float(b[0])
                    size = float(b[1])
                    bids.append((price, size))
                except Exception:
                    continue
            asks = sorted(asks, key=lambda x: x[0])
            bids = sorted(bids, key=lambda x: x[0], reverse=True)
            return {'asks': asks, 'bids': bids}
        except Exception as e:
            # on error, raise to let callers decide
            raise
