"""Helpers to start/stop lightweight feeders and register them with ws_feed_manager.

This module centralizes feeder startup so it can be used both by the
tmp_start_all_feeders demo script and optionally by the FastAPI app at
startup when ARB_AUTO_START_FEEDERS=1.
"""
from __future__ import annotations

import os
from typing import Dict, Any, Optional

try:
    # local imports from package
    from .exchanges import ccxt_async_feeder as feeder_mod
    from .exchanges.binance_depth_feeder import BinanceDepthFeeder
    # KuCoin has a similar websocket depth feeder if present
    try:
        from .exchanges.kucoin_depth_feeder import KucoinDepthFeeder  # type: ignore
    except Exception:
        KucoinDepthFeeder = None  # type: ignore
    from .exchanges.ws_feed_manager import register_feeder, unregister_feeder, get_feeder
    # helper to fetch binance top symbols when available
    try:
        from .hotcoins import _binance_top_by_volume
    except Exception:
        _binance_top_by_volume = None
except Exception:
    # fallback for ad-hoc execution where package imports may differ
    from arbitrage.exchanges import ccxt_async_feeder as feeder_mod  # type: ignore
    from arbitrage.exchanges.binance_depth_feeder import BinanceDepthFeeder  # type: ignore
    from arbitrage.exchanges.ws_feed_manager import register_feeder, unregister_feeder, get_feeder  # type: ignore

EXCHANGES = ['binance', 'bitrue', 'kucoin', 'okx', 'gate', 'mexc']


def start_all(interval: float = 1.0, symbols: Optional[list[str]] = None, exchanges: Optional[list[str]] = None) -> Dict[str, Any]:
    """Start websocket feeders.

    - interval: polling interval for non-ws feeders
    - symbols: optional list of symbols to subscribe/request
    - exchanges: optional list of exchange ids to start. If omitted, the
      function will consult the ARB_WS_FEED_EXCHANGES env var. If that is
      not set, default to ['binance'] to avoid starting unreliable adapters
      (e.g., okx) by default.
    """
    feeders: Dict[str, Any] = {}
    exclude_env = os.environ.get('ARB_WS_FEED_EXCLUDE', '')
    exclude_set = set([s.strip().lower() for s in exclude_env.split(',') if s.strip()])

    # determine target exchanges to start
    if exchanges is None:
        raw = os.environ.get('ARB_WS_FEED_EXCHANGES')
        if raw:
            target_exchanges = [e.strip().lower() for e in raw.split(',') if e.strip()]
        else:
            # default to only binance for live websocket feeders to reduce
            # external failures (okx, etc.) unless an explicit list is provided
            target_exchanges = ['binance']
    else:
        target_exchanges = [e.strip().lower() for e in exchanges if e and isinstance(e, str)]

    # If arbitrage mode is enabled, allow starting kucoin in addition to binance
    arb_enabled = os.environ.get('ARB_ENABLE_ARBITRAGE', '0').strip() == '1'
    for ex in target_exchanges:
        if ex.lower() in exclude_set:
            continue
        # Only auto-start websocket-capable feeders. At the moment we only
        # support BinanceDepthFeeder (websocket). Skip non-ws/ccxt polling
        # feeders to avoid starting adapters that are unreliable in this
        # environment (e.g., okx). If caller passes an explicit exchanges
        # list and requests non-binance adapters they will be skipped here
        # to enforce the "ws-only" policy.
        try:
            existing = None
            try:
                existing = get_feeder(ex)
            except Exception:
                existing = None
            if existing is not None:
                feeders[ex] = existing
                continue

            if ex == 'binance':
                # Start the websocket-based Binance feeder. If no explicit
                # symbols list is provided, attempt to subscribe to the top
                # N symbols by quote volume so the feeder can provide
                # orderbook snapshots for the hotcoins list.
                sub_symbols = symbols
                if not sub_symbols:
                    try:
                        if _binance_top_by_volume is not None:
                            top = _binance_top_by_volume(top_n=60)
                            # convert to symbol strings like 'BTC/USDT'
                            sub_symbols = [f"{i.get('base')}/{i.get('quote')}" for i in top if i.get('base') and i.get('quote')]
                    except Exception:
                        sub_symbols = None
                if not sub_symbols:
                    sub_symbols = ['BTC/USDT', 'ETH/USDT']
                # Start the feeder with the chosen subscription list
                f = BinanceDepthFeeder(sub_symbols)
                f.start()
                try:
                    register_feeder(ex, f)
                except Exception:
                    pass
                feeders[ex] = f
            elif ex == 'kucoin' and arb_enabled and KucoinDepthFeeder is not None:
                # Start KuCoin feeder only when arbitrage mode is explicitly enabled
                try:
                    # If a symbols list is provided, attempt to map/validate
                    # the requested symbols against KuCoin's listed symbols so
                    # we subscribe using the correct hyphenated form (e.g. BTC-USDT).
                    def _map_symbols_for_kucoin(candidates: list[str]) -> list[str]:
                        if not candidates:
                            return []
                        try:
                            import urllib.request as _urlreq, json as _json
                            # fetch KuCoin symbols list
                            req = _urlreq.Request('https://api.kucoin.com/api/v1/symbols', headers={'User-Agent': 'arb-feeder/1.0'})
                            with _urlreq.urlopen(req, timeout=5) as resp:
                                raw = resp.read()
                                obj = _json.loads(raw.decode('utf-8'))
                                data = obj.get('data') or []
                                available = set()
                                for it in data:
                                    try:
                                        s = (it.get('symbol') or '').upper()
                                        if s:
                                            available.add(s)
                                    except Exception:
                                        continue
                        except Exception:
                            # If we can't fetch listings, fall back to best-effort mapping
                            available = set()

                        out: list[str] = []
                        for c in candidates:
                            if not c:
                                continue
                            s = c.strip().upper().replace('/', '').replace('-', '')
                            # Try common hyphenated/normalized forms
                            cand1 = f"{s[:-4]}-{s[-4:]}" if len(s) > 4 else None
                            cand2 = f"{s[:-3]}-{s[-3:]}" if len(s) > 3 else None
                            hy1 = (c.strip().upper().replace('/', '-'))
                            hy2 = (c.strip().upper().replace('/', '').replace('-', ''))
                            chosen = None
                            # prefer exact match against KuCoin's available symbols
                            if hy1 in available:
                                chosen = hy1
                            elif hy2 in available:
                                chosen = hy2
                            elif cand1 and cand1 in available:
                                chosen = cand1
                            elif cand2 and cand2 in available:
                                chosen = cand2
                            else:
                                # if we have no listing info, attempt hyphenated form as last resort
                                chosen = hy1
                            if chosen:
                                out.append(chosen)
                        return out

                    sub_symbols = symbols or ['BTC/USDT', 'ETH/USDT']
                    # map/validate for KuCoin
                    try:
                        mapped = _map_symbols_for_kucoin(sub_symbols)
                        if mapped:
                            sub_symbols = mapped
                    except Exception:
                        pass
                    f = KucoinDepthFeeder(sub_symbols or ['BTC/USDT', 'ETH/USDT'])
                    f.start()
                    try:
                        register_feeder(ex, f)
                    except Exception:
                        pass
                    feeders[ex] = f
                except Exception:
                    # If KuCoin feeder fails to start, continue without it
                    continue
            else:
                # Intentionally skip starting non-websocket feeders here.
                # This avoids launching CCXT polling adapters automatically.
                # However, for MEXC we can start a dedicated feeder or fall back
                # to the lightweight CCXT async poller so MEXC is usable.
                try:
                    if ex == 'mexc':
                        # try to load a dedicated websocket Depth feeder for MEXC if present
                        MexcDepthFeeder = None
                        try:
                            from .exchanges.mexc_depth_feeder import MexcDepthFeeder  # type: ignore
                        except Exception:
                            MexcDepthFeeder = None

                        sub_symbols = symbols
                        if not sub_symbols:
                            try:
                                if _binance_top_by_volume is not None:
                                    top = _binance_top_by_volume(top_n=60)
                                    sub_symbols = [f"{i.get('base')}/{i.get('quote')}" for i in top if i.get('base') and i.get('quote')]
                            except Exception:
                                sub_symbols = None
                        if not sub_symbols:
                            sub_symbols = ['BTC/USDT', 'ETH/USDT']

                        if MexcDepthFeeder is not None:
                            try:
                                f = MexcDepthFeeder(sub_symbols)
                                f.start()
                                try:
                                    register_feeder(ex, f)
                                except Exception:
                                    pass
                                feeders[ex] = f
                                continue
                            except Exception:
                                # fallthrough to CCXTAsyncFeeder
                                pass

                        # Fallback: start the CCXT async poller for mexc so we have tickers
                        try:
                            f = feeder_mod.CCXTAsyncFeeder('mexc', symbols=sub_symbols, interval=interval)
                            f.start()
                            try:
                                register_feeder(ex, f)
                            except Exception:
                                pass
                            feeders[ex] = f
                            continue
                        except Exception:
                            continue
                    if ex == 'gate':
                        # Try to start a lightweight Gate websocket feeder
                        try:
                            from .exchanges.gate_depth_feeder import GateDepthFeeder  # type: ignore
                            sub_symbols = symbols or ['BTC/USDT', 'ETH/USDT']
                            f = GateDepthFeeder(sub_symbols)
                            f.start()
                            try:
                                register_feeder(ex, f)
                            except Exception:
                                pass
                            feeders[ex] = f
                            continue
                        except Exception:
                            # ignore gate feeder startup failures and continue
                            pass
                except Exception:
                    continue
        except Exception:
            # ignore individual feeder failures
            continue
    # indicate adapters to prefer feeders
    os.environ['ARB_USE_WS_FEED'] = '1'
    return feeders


def stop_all(feeders: Dict[str, Any]) -> None:
    for ex, f in list(feeders.items()):
        try:
            try:
                unregister_feeder(ex)
            except Exception:
                pass
            try:
                f.stop()
            except Exception:
                pass
        except Exception:
            pass
