from __future__ import annotations

import threading
import time
from typing import Optional, List, Dict, Any


class CCXTAsyncFeeder:
    """Background feeder that keeps a ticker snapshot warm using an
    async ccxt client when available, otherwise falls back to a threaded
    sync poller. The feeder exposes get_tickers() to read the in-memory
    snapshot and is safe to register with the ws_feed_manager.

    This is a pragmatic helper: it does not attempt full watch_* websocket
    subscriptions (ccxt.pro) but provides a low-impact background poller
    that significantly reduces scanner-induced REST calls when the feeder
    is running.
    """

    def __init__(self, exchange_id: str, symbols: Optional[List[str]] = None, interval: float = 1.0):
        self.id = exchange_id.lower()
        self.symbols = symbols
        self.interval = float(interval)
        self._tickers: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # error throttling to avoid log spam for flaky endpoints
        self._last_error_log: Dict[str, float] = {}
        self._error_throttle_s = float(30.0)
        # consecutive failure counter to allow gentle backoff
        self._consecutive_failures = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"ccxt-feeder-{self.id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def get_tickers(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            # return a shallow copy to avoid callers mutating internal state
            return dict(self._tickers)

    def _run(self) -> None:
        # Prefer async ccxt if available
        try:
            import asyncio
        except Exception:
            asyncio = None

        async_ccxt = None
        try:
            import importlib

            async_ccxt = importlib.import_module("ccxt.async_support")
        except Exception:
            async_ccxt = None

        if async_ccxt is not None and asyncio is not None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._run_async(async_ccxt))
                return
            except Exception as e:  # fall back to sync poller
                try:
                    print(f"[feeder:{self.id}] async feeder failed to start: {e}")
                except Exception:
                    pass

        # fallback: run sync poller
        self._run_sync()

    async def _run_async(self, async_ccxt) -> None:
        exch_cls = getattr(async_ccxt, self.id, None)
        client = None
        if exch_cls is not None:
            try:
                client = exch_cls({"enableRateLimit": True})
            except Exception as e:
                try:
                    print(f"[feeder:{self.id}] async client instantiation failed: {e}")
                except Exception:
                    pass
                client = None

        try:
            import asyncio as _asyncio

            while not self._stop.is_set():
                try:
                    data = None
                    if client is not None and hasattr(client, "fetch_tickers"):
                        try:
                            data = await client.fetch_tickers()
                            # reset failure counter on success
                            self._consecutive_failures = 0
                        except Exception as e:
                            # throttle noisy error messages
                            try:
                                now = time.time()
                                key = f'async_fetch_tickers'
                                last = self._last_error_log.get(key, 0.0)
                                if now - last > self._error_throttle_s:
                                    print(f"[feeder:{self.id}] async fetch_tickers failed: {e}")
                                    self._last_error_log[key] = now
                            except Exception:
                                pass
                            data = None
                            self._consecutive_failures += 1

                    # if we got no data, try per-symbol fetch_ticker
                    if (not data or not isinstance(data, dict)) and self.symbols and client is not None:
                        data = {}
                        for s in self.symbols:
                            try:
                                t = await client.fetch_ticker(s)
                                data[s] = t
                            except Exception:
                                continue

                    if isinstance(data, dict):
                        out: Dict[str, Dict[str, Any]] = {}
                        for sym, info in data.items():
                            try:
                                if isinstance(info, dict):
                                    price = info.get("last") or info.get("price")
                                elif isinstance(info, (int, float)):
                                    price = float(info)
                                else:
                                    price = None
                                if price is None:
                                    continue
                                out[sym] = {"last": float(price), "timestamp": time.time()}
                            except Exception:
                                continue
                        with self._lock:
                            self._tickers = out
                except Exception:
                    # swallow to keep feeder alive
                    self._consecutive_failures += 1
                    try:
                        key = 'generic_async_loop'
                        now = time.time()
                        if now - self._last_error_log.get(key, 0.0) > self._error_throttle_s:
                            print(f"[feeder:{self.id}] async loop exception (suppressed): check logs")
                            self._last_error_log[key] = now
                    except Exception:
                        pass
                # gentle backoff on repeated failures
                backoff = min(self.interval * (1 + 0.5 * self._consecutive_failures), 10.0)
                await _asyncio.sleep(backoff)
        finally:
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    try:
                        print(f"[feeder:{self.id}] async client close failed")
                    except Exception:
                        pass

    def _run_sync(self) -> None:
        # use ccxt sync client as fallback poller
        client = None
        try:
            import importlib

            sync_ccxt = importlib.import_module("ccxt")
            exch_cls = getattr(sync_ccxt, self.id, None)
            if exch_cls is not None:
                try:
                    client = exch_cls({"enableRateLimit": True})
                except Exception as e:
                    try:
                        print(f"[feeder:{self.id}] sync client instantiation failed: {e}")
                    except Exception:
                        pass
                    client = None
        except Exception:
            client = None

        while not self._stop.is_set():
            try:
                data = None
                if client is not None and hasattr(client, "fetch_tickers"):
                    try:
                        data = client.fetch_tickers()
                    except Exception as e:
                        try:
                            now = time.time()
                            key = 'sync_fetch_tickers'
                            last = self._last_error_log.get(key, 0.0)
                            if now - last > self._error_throttle_s:
                                print(f"[feeder:{self.id}] sync fetch_tickers failed: {e}")
                                self._last_error_log[key] = now
                        except Exception:
                            pass
                        data = None
                        self._consecutive_failures += 1

                if (not data or not isinstance(data, dict)) and self.symbols and client is not None:
                    data = {}
                    for s in self.symbols:
                        try:
                            t = client.fetch_ticker(s)
                            data[s] = t
                        except Exception:
                            continue

                if isinstance(data, dict):
                    out: Dict[str, Dict[str, Any]] = {}
                    for sym, info in data.items():
                        try:
                            if isinstance(info, dict):
                                price = info.get("last") or info.get("price")
                            elif isinstance(info, (int, float)):
                                price = float(info)
                            else:
                                price = None
                            if price is None:
                                continue
                            out[sym] = {"last": float(price), "timestamp": time.time()}
                        except Exception:
                            continue
                    with self._lock:
                        self._tickers = out
                        # reset failures on success
                        self._consecutive_failures = 0
            except Exception:
                # swallow to keep feeder running
                self._consecutive_failures += 1
                try:
                    key = 'generic_sync_loop'
                    now = time.time()
                    if now - self._last_error_log.get(key, 0.0) > self._error_throttle_s:
                        print(f"[feeder:{self.id}] sync loop exception (suppressed): check logs")
                        self._last_error_log[key] = now
                except Exception:
                    pass

            # sleep in small increments to respond to stop flag faster
            slept = 0.0
            while slept < self.interval and not self._stop.is_set():
                time.sleep(min(0.5, self.interval - slept))
                slept += 0.5
