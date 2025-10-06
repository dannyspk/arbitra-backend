"""Compare tickers between Binance and MEXC and report arbitrage opportunities."""
import os
import sys
import json
import traceback
from pprint import pprint

# make local src importable when running the script from repo root
ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# try to import adapters from the package; fall back to simple mocks if missing
try:
    # Import from the package so package-level adapter selection (e.g. CCXTPro)
    # can override the concrete implementation when enabled via env vars.
    from arbitrage.exchanges import MEXCExchange, CCXTExchange, MockExchange  # type: ignore
    from arbitrage.scanner import find_executable_opportunities
except Exception as e:
    # minimal mocks (used only in mock_mode)
    import importlib
    print('Warning: failed to import live adapters at module import time:', e)
    print('Will attempt to import adapters at runtime in live_mode()')
    class MockExchange:
        def __init__(self, name, tickers):
            self.name = name
            self._tickers = tickers
            self.depth = 1.0
            self.fee_rate = 0.001
        def get_tickers(self):
            return self._tickers
        def get_order_book(self, sym):
            # return a simple synthetic orderbook
            return {'asks': [(self._tickers.get(sym, 0.0), 1.0)], 'bids': [(self._tickers.get(sym, 0.0), 1.0)]}
    def find_executable_opportunities(exs, amount=0.01, min_profit_pct=0.05):
        # very small mock: create synthetic opportunities when prices differ
        opps = []
        for i in range(len(exs)):
            for j in range(i+1, len(exs)):
                a = exs[i].get_tickers()
                b = exs[j].get_tickers()
                for sym in set(a) & set(b):
                    pa = a[sym]
                    pb = b[sym]
                    if pa <= 0 or pb <= 0:
                        continue
                    if pa < pb and ((pb - pa) / pa) * 100.0 > min_profit_pct:
                        class O: pass
                        o = O()
                        o.symbol = sym
                        o.buy_exchange = exs[i].name
                        o.sell_exchange = exs[j].name
                        o.buy_price = pa
                        o.sell_price = pb
                        o.profit_pct = ((pb - pa) / pa) * 100.0
                        o.buy_withdraw = True
                        o.sell_deposit = True
                        opps.append(o)
        return opps

# Ensure adapter names exist (they may be importable later); set to None if not present
try:
    CCXTExchange
except NameError:
    CCXTExchange = None
try:
    MEXCExchange
except NameError:
    MEXCExchange = None

def live_mode(fast: bool = False, probe_symbols: list[str] | None = None):
    """Probe live exchanges. In fast mode we fetch only a small set of symbols
    per exchange (using fetch_ticker) to keep the probes quick. When fast=False
    we fall back to fetching compact tickers as before.
    """
    # probe exactly the exchanges requested (live CCXT mode)
    exchange_ids = ['bitrue', 'kucoin', 'okx', 'gate', 'mexc']

    # If a websocket feeder has been registered for any of these exchanges,
    # enable the adapter fast-path so adapters will prefer the feeder
    # snapshot (avoids REST fetch_tickers when possible).
    try:
        try:
            from arbitrage.exchanges.ws_feed_manager import get_feeder
        except Exception:
            from .src.arbitrage.exchanges.ws_feed_manager import get_feeder  # type: ignore
        for eid in exchange_ids:
            try:
                if get_feeder(eid) is not None:
                    os.environ['ARB_USE_WS_FEED'] = '1'
                    print(f'  [probe] ARB_USE_WS_FEED enabled because feeder registered for {eid}')
                    break
            except Exception:
                continue
    except Exception:
        # ignore if feed manager isn't importable
        pass

    # Attempt runtime import of adapters if they weren't available at module import time
    global CCXTExchange, MEXCExchange
    if CCXTExchange is None or MEXCExchange is None:
        try:
            # import from package so package-level selection (e.g., CCXTPro) applies
            from arbitrage.exchanges import CCXTExchange as _C, MEXCExchange as _M
            CCXTExchange = CCXTExchange or _C
            MEXCExchange = MEXCExchange or _M
            print('Imported live adapters at runtime (package-level)')
        except Exception as e:
            print('Runtime import of live adapters failed:', e)
            # let probe attempts continue; probe() will handle the None cases

    # Production-friendly timeouts: keep probes short and concurrent.
    # In fast mode prefer a much shorter per-exchange timeout so probes finish quickly.
    per_exchange_timeout_ms = int(os.environ.get('TMP_PROBE_TIMEOUT_MS', '1000' if fast else '3000'))
    max_workers = min(6, len(exchange_ids)) 

    # default probe symbols for quick checks
    if probe_symbols is None:
        probe_symbols = ['BTC/USDT', 'ETH/USDT'] if fast else None

    from concurrent.futures import ThreadPoolExecutor

    def _apply_aggressive_filter_and_install(ex, ticks: dict) -> tuple[dict, int, int]:
        """Apply aggressive filtering: if both marketcap and 24h volume are present
        for base, enforce thresholds (mc < 1B, vol >= 100k). If metrics are missing,
        only keep symbols quoted in TMP_KEEP_QUOTES. Install the filtered map into
        ex._tickers_cache so scanner uses the reduced set.

        Returns (kept_map, raw_count, kept_count).
        """
        try:
            raw = len(ticks) if isinstance(ticks, dict) else 0
            kept = {}
            allowed_quotes = os.getenv('TMP_KEEP_QUOTES', 'USDT')
            allowed = {q.strip().upper() for q in allowed_quotes.split(',') if q.strip()}
            cache = getattr(ex, '_currency_cache', None) or {}
            tcache = getattr(ex, '_tickers_cache', None) or {}
            for sym, price in (ticks.items() if isinstance(ticks, dict) else []):
                try:
                    base = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
                    entry = cache.get(base) or cache.get(base.upper()) or cache.get(base.lower())
                    mc = None
                    vol = None
                    if isinstance(entry, dict):
                        for mk in ('marketCap', 'market_cap', 'marketCapUsd', 'market_cap_usd'):
                            if mk in entry and entry.get(mk) is not None:
                                try:
                                    mc = float(entry.get(mk))
                                    break
                                except Exception:
                                    pass
                        info = entry.get('info') if isinstance(entry.get('info'), dict) else None
                        if isinstance(info, dict):
                            for vk in ('volume24h', 'volume_24h', 'quoteVolume', 'volume'):
                                vv = info.get(vk)
                                if vv is not None:
                                    try:
                                        vol = float(vv)
                                        break
                                    except Exception:
                                        pass
                    # fallback: try ticker cache for volume
                    if vol is None and isinstance(tcache, dict):
                        tk = tcache.get(sym) or tcache.get(sym.replace('-', '/')) or tcache.get(sym.replace('/', '-'))
                        if isinstance(tk, dict):
                            for vk in ('quoteVolume', 'baseVolume', 'volume'):
                                if vk in tk and tk.get(vk) is not None:
                                    try:
                                        v = float(tk.get(vk))
                                        if vk == 'baseVolume' and tk.get('last'):
                                            try:
                                                last = float(tk.get('last'))
                                                v = v * last
                                            except Exception:
                                                pass
                                        vol = v
                                        break
                                    except Exception:
                                        pass

                    if mc is not None and vol is not None:
                        if mc < 1_000_000_000 and vol >= 100_000:
                            kept[sym] = price
                    else:
                        # only keep if quote is allowed
                        quote = None
                        if '/' in sym:
                            parts = sym.split('/')
                            if len(parts) >= 2:
                                quote = parts[1].upper()
                        elif '-' in sym:
                            parts = sym.split('-')
                            if len(parts) >= 2:
                                quote = parts[1].upper()
                        if quote is None or quote in allowed:
                            kept[sym] = price
                except Exception:
                    # on error keep symbol
                    kept[sym] = price
            # install into adapter cache so scanner sees reduced set
            try:
                if hasattr(ex, '_tickers_cache'):
                    ex._tickers_cache = kept
                    ex._tickers_cache_ts = time.time()
            except Exception:
                pass
            return kept, raw, len(kept)
        except Exception:
            return ticks or {}, len(ticks) if isinstance(ticks, dict) else 0, len(ticks) if isinstance(ticks, dict) else 0


    def probe(eid: str, timeout_ms: int):
        print(f'  [probe] starting probe for {eid} (timeout {timeout_ms} ms)')
        try:
            if eid == 'mexc':
                # use MEXCExchange adapter which wraps ccxt internals
                print(f'    [probe:{eid}] creating MEXCExchange adapter')
                ex = MEXCExchange(api_key=None, secret=None, timeout=timeout_ms)
                # For large exchanges, try a batch CoinGecko enrichment to populate
                # marketcap/volume for many bases at once (if enabled).
                try:
                    if os.getenv('ARB_USE_COINGECKO', '0') == '1':
                        try:
                            from arbitrage.utils.coingecko import get_metrics_for_bases
                            # attempt to fetch tickers quickly (non-blocking best-effort)
                            try:
                                tmap = ex.get_tickers()
                            except Exception:
                                tmap = {}
                            bases = []
                            for s in (tmap.keys() if isinstance(tmap, dict) else []):
                                try:
                                    base = s.split('/')[0] if '/' in s else (s.split('-')[0] if '-' in s else s)
                                    if base:
                                        bases.append(base)
                                except Exception:
                                    continue
                            # only query for a reasonable number of bases to avoid long waits
                            if bases:
                                bases = list(dict.fromkeys(bases))[:1000]
                                _ = get_metrics_for_bases(bases)
                        except Exception:
                            pass
                except Exception:
                    pass
                # try to prewarm currency metadata quickly for better filtered counts
                try:
                    if hasattr(ex, 'prewarm_currency_metadata'):
                        prewarm_s = float(os.environ.get('TMP_PREWARM_TIMEOUT_S', '2.0'))
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(max_workers=1) as _p:
                            fut = _p.submit(ex.prewarm_currency_metadata, prewarm_s)
                            try:
                                fut.result(timeout=min(prewarm_s, 1.0))
                            except Exception:
                                pass
                except Exception:
                    pass
                # adapter exposes get_tickers; in fast mode, avoid full get_tickers
                if fast and probe_symbols:
                    ticks = {}
                    for s in probe_symbols:
                        try:
                            # try a few formats
                            for cand in (s, s.replace('/', '-')):
                                try:
                                    print(f'      [probe:{eid}] fetch_ticker {cand}')
                                    t = ex.client.fetch_ticker(cand)
                                    price = t.get('last') if isinstance(t, dict) else None
                                    if price is None:
                                        bid = t.get('bid') if isinstance(t, dict) else None
                                        ask = t.get('ask') if isinstance(t, dict) else None
                                        if bid and ask:
                                            price = (bid + ask) / 2
                                    if price is not None:
                                        ticks[cand] = price
                                        break
                                except Exception:
                                    print(f'      [probe:{eid}] fetch_ticker {cand} failed')
                                    continue
                        except Exception:
                            continue
                    # estimate filtered count using cached metadata
                    def _estimate_filtered(tks: dict) -> tuple[int, int]:
                        raw = len(tks)
                        filtered = 0
                        try:
                            cache = getattr(ex, '_currency_cache', None) or {}
                            tcache = getattr(ex, '_tickers_cache', None) or {}
                            for sym in tks.keys():
                                base = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
                                entry = cache.get(base) or cache.get(base.upper()) or cache.get(base.lower())
                                # if we have explicit marketcap and volume info and it fails thresholds, exclude
                                mc = None
                                vol = None
                                if isinstance(entry, dict):
                                    for mk in ('marketCap', 'market_cap', 'marketCapUsd', 'market_cap_usd'):
                                        if mk in entry and entry.get(mk) is not None:
                                            try:
                                                mc = float(entry.get(mk))
                                                break
                                            except Exception:
                                                pass
                                    info = entry.get('info') if isinstance(entry.get('info'), dict) else None
                                    if isinstance(info, dict):
                                        for vk in ('volume24h', 'volume_24h', 'quoteVolume', 'volume'):
                                            vv = info.get(vk)
                                            if vv is not None:
                                                try:
                                                    vol = float(vv)
                                                    break
                                                except Exception:
                                                    pass
                                # conservative: only exclude when both known and failing thresholds
                                # If volume missing in currency entry, try ticker cache for sym
                                if vol is None:
                                    try:
                                        tk = tcache.get(sym) if isinstance(tcache, dict) else None
                                        if isinstance(tk, dict):
                                            for vk in ('quoteVolume', 'baseVolume', 'volume'):
                                                if vk in tk and tk.get(vk) is not None:
                                                    try:
                                                        v = float(tk.get(vk))
                                                        # convert baseVolume to USD if last price available
                                                        if vk == 'baseVolume' and tk.get('last'):
                                                            try:
                                                                last = float(tk.get('last'))
                                                                v = v * last
                                                            except Exception:
                                                                pass
                                                        vol = v
                                                        break
                                                    except Exception:
                                                        pass
                                    except Exception:
                                        pass
                                # conservative inclusion: only exclude when both known and failing thresholds
                                if mc is not None and vol is not None:
                                    if mc < 1_000_000_000 and vol >= 100_000:
                                        filtered += 1
                                else:
                                    filtered += 1
                        except Exception:
                            return raw, raw
                        return raw, filtered

                    raw, filt = _estimate_filtered(ticks)
                    return (eid, ex, raw, filt)
                else:
                    t = ex.get_tickers()
                    # apply strict filtering immediately to the ticker map when requested
                    raw = len(t)
                    filt = raw
                    try:
                        strict = os.getenv('ARB_STRICT_METRICS', '0') == '1'
                        SYMBOLS_THRESHOLD = 500
                        ex_count = len(t) if isinstance(t, dict) else 0
                        apply_here = strict and ex_count > SYMBOLS_THRESHOLD
                        if apply_here:
                            cache = getattr(ex, '_currency_cache', None) or {}
                            tcache = getattr(ex, '_tickers_cache', None) or {}
                            kept: dict = {}
                            for sym, price in (t.items() if isinstance(t, dict) else []):
                                try:
                                    base = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
                                    entry = cache.get(base) or cache.get(base.upper()) or cache.get(base.lower())
                                    mc = None
                                    vol = None
                                    if isinstance(entry, dict):
                                        for mk in ('marketCap', 'market_cap', 'marketCapUsd', 'market_cap_usd'):
                                            if mk in entry and entry.get(mk) is not None:
                                                try:
                                                    mc = float(entry.get(mk))
                                                    break
                                                except Exception:
                                                    pass
                                        info = entry.get('info') if isinstance(entry.get('info'), dict) else None
                                        if isinstance(info, dict):
                                            for vk in ('volume24h', 'volume_24h', 'quoteVolume', 'volume'):
                                                vv = info.get(vk)
                                                if vv is not None:
                                                    try:
                                                        vol = float(vv)
                                                        break
                                                    except Exception:
                                                        pass
                                    # fallback: try to use ticker cache for volume
                                    if vol is None and isinstance(tcache, dict):
                                        tk = tcache.get(sym) or tcache.get(sym.replace('-', '/')) or tcache.get(sym.replace('/', '-'))
                                        if isinstance(tk, dict):
                                            for vk in ('quoteVolume', 'baseVolume', 'volume'):
                                                if vk in tk and tk.get(vk) is not None:
                                                    try:
                                                        v = float(tk.get(vk))
                                                        if vk == 'baseVolume' and tk.get('last'):
                                                            try:
                                                                last = float(tk.get('last'))
                                                                v = v * last
                                                            except Exception:
                                                                pass
                                                        vol = v
                                                        break
                                                    except Exception:
                                                        pass
                                    # conservative inclusion: only exclude when both known and failing thresholds
                                    if mc is not None and vol is not None:
                                        if mc < 1_000_000_000 and vol >= 100_000:
                                            kept[sym] = price
                                    else:
                                        # Metrics unknown: apply a lightweight quote-based heuristic to reduce
                                        # the symbol set for large exchanges. Keep only pairs quoted in
                                        # common stablecoins/majors (configurable via env TMP_KEEP_QUOTES).
                                        keep_quotes = os.getenv('TMP_KEEP_QUOTES', 'USDT')
                                        try:
                                            allowed = {q.strip().upper() for q in keep_quotes.split(',') if q.strip()}
                                        except Exception:
                                            allowed = {'USDT', 'USD', 'USDC', 'BTC', 'ETH'}
                                        quote = None
                                        if '/' in sym:
                                            parts = sym.split('/')
                                            if len(parts) >= 2:
                                                quote = parts[1].upper()
                                        elif '-' in sym:
                                            parts = sym.split('-')
                                            if len(parts) >= 2:
                                                quote = parts[1].upper()
                                        # default: keep if quote is in allowed set, otherwise drop
                                        if quote is None or quote in allowed:
                                            kept[sym] = price
                                except Exception:
                                    # on any error keep the symbol
                                    kept[sym] = price
                            filt = len(kept)
                            # install filtered tickers into adapter's cache to reduce later scanning
                            try:
                                if hasattr(ex, '_tickers_cache'):
                                    ex._tickers_cache = kept
                                    ex._tickers_cache_ts = time.time()
                            except Exception:
                                pass
                            t = kept
                    except Exception:
                        pass
                    return (eid, ex, len(t), filt)
            else:
                # use CCXTExchange wrapper
                print(f'    [probe:{eid}] creating CCXTExchange wrapper')
                ex = CCXTExchange(eid, options={'timeout': timeout_ms, 'enableRateLimit': True})
                if fast and probe_symbols:
                    ticks = {}
                    for s in probe_symbols:
                        for cand in ex._candidate_symbols(s):
                            try:
                                print(f'      [probe:{eid}] fetch_ticker {cand}')
                                t = ex.client.fetch_ticker(cand)
                                price = t.get('last') if isinstance(t, dict) else None
                                if price is None:
                                    bid = t.get('bid') if isinstance(t, dict) else None
                                    ask = t.get('ask') if isinstance(t, dict) else None
                                    if bid and ask:
                                        price = (bid + ask) / 2
                                if price is not None:
                                    ticks[cand] = price
                                    break
                            except Exception:
                                print(f'      [probe:{eid}] fetch_ticker {cand} failed')
                                continue
                    # apply aggressive filter and install into adapter cache for non-MEXC too
                    kept_map, raw, kept_count = _apply_aggressive_filter_and_install(ex, ticks)
                    return (eid, ex, raw, kept_count)
                else:
                    t = ex.get_tickers()
                    kept_map, raw, kept_count = _apply_aggressive_filter_and_install(ex, t)
                    return (eid, ex, raw, kept_count)
        except Exception as e:
            return (eid, None, e)

    live = []
    print(f'Probing exchanges concurrently with per-exchange timeout={per_exchange_timeout_ms/1000:.2f}s (fast={fast})')
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futs = {exe.submit(probe, eid, per_exchange_timeout_ms): eid for eid in exchange_ids}
        for fut in futs:
            eid = futs[fut]
            try:
                res = fut.result(timeout=(per_exchange_timeout_ms / 1000.0) + 1.0)
            except Exception as e:
                print(f'  probe timeout/failed for {eid}: {e}')
                continue
            if not res:
                continue
            # probe() may return (eid, ex, info) or (eid, ex, raw, filtered)
            try:
                if len(res) == 3:
                    eid, ex, info = res
                    raw_count = info
                    filtered_est = None
                elif len(res) == 4:
                    eid, ex, raw_count, filtered_est = res
                    info = raw_count
                else:
                    # unknown shape
                    eid, ex, info = res[0], res[1], res[2]
                    raw_count = info
                    filtered_est = None
            except Exception:
                print(f'  probe returned unexpected result for {eid}: {res}')
                continue
            if ex is None:
                print(f'  probe failed for {eid}: {info}')
                continue
            # avoid duplicate adapters by name
            if any(getattr(e, 'name', '') == getattr(ex, 'name', '') for e in live):
                continue
            if filtered_est is None:
                print(f'  live: {eid} ({raw_count} tickers found)')
            else:
                print(f'  live: {eid} (raw={raw_count} tickers, estimated_kept={filtered_est})')
            live.append(ex)

    if len(live) < 2:
        print('Not enough live exchanges available after probe; falling back to mock mode')
        return None
    print('Using live CCXT mode for exchanges:', ', '.join([getattr(e, 'name', str(e)) for e in live]))
    # Pre-warm currency metadata for live adapters to avoid repeated blocking
    # fetch_currencies() calls during scanning. Run pre-warm in parallel with
    # a short timeout per adapter so a slow exchange doesn't hang the whole run.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    prewarm_timeout = float(os.environ.get('TMP_PREWARM_TIMEOUT_S', '2.0'))
    with ThreadPoolExecutor(max_workers=min(6, len(live))) as pexe:
        futures = {pexe.submit(getattr, ex, 'prewarm_currency_metadata', None): ex for ex in live if hasattr(ex, 'prewarm_currency_metadata')}
        # we invoked getattr to obtain the bound method; call it with timeout via future.result()
        for fut in list(futures.keys()):
            ex = futures[fut]
            try:
                # if the bound method exists we expect it to run quickly; use result with timeout
                meth = fut.result(timeout=0.1)
                # submit the actual call
                p = pexe.submit(meth)
                try:
                    p.result(timeout=prewarm_timeout)
                    print(f'  [prewarm] completed for {getattr(ex, "name", str(ex))}')
                except Exception:
                    print(f'  [prewarm] timed out/failed for {getattr(ex, "name", str(ex))} (continuing)')
            except Exception:
                # retrieving the method or calling it failed; continue
                print(f'  [prewarm] could not prewarm for {getattr(ex, "name", str(ex))} (skipping)')
                continue

    return live


def mock_mode():
    ex1 = MockExchange('binance-mock', {'BTC/USDT': 27000.0, 'ETH/USDT': 1700.0, 'NEIRO/USDT': 0.00027})
    ex2 = MockExchange('mexc-mock', {'BTC/USDT': 27100.0, 'ETH/USDT': 1690.0, 'NEIRO/USDT': 0.00075})
    ex3 = MockExchange('kucoin-mock', {'BTC/USDT': 26950.0, 'ETH/USDT': 1705.0, 'XYZ/USDT': 0.5})
    ex4 = MockExchange('gate-mock', {'BTC/USDT': 27010.0, 'ETH/USDT': 1702.0, 'FOO-USD': 101.0})
    # adjust depths and fees to create variation
    ex1.depth = 1.0
    ex2.depth = 0.5
    ex3.depth = 2.0
    ex4.depth = 1.5
    for ex in (ex1, ex2, ex3, ex4):
        ex.fee_rate = 0.001
    print('Using mock mode with 4 mock exchanges')
    return [ex1, ex2, ex3, ex4]


def quick_scan(exs, probe_symbols=None, min_profit_pct=0.05, amount=0.01, collect_metrics: bool = False):
    """Lightweight scan that fetches last prices for a small set of symbols
    and looks for simple price-discrepancy opportunities without fetching
    full order books. This is intentionally fast and best-effort.
    """
    if probe_symbols is None:
        probe_symbols = ['BTC/USDT', 'ETH/USDT']
    print('Starting quick_scan for symbols:', probe_symbols)
    tickers = {}
    feeder_hits = 0
    fetch_ticker_calls = 0
    for e in exs:
        name = getattr(e, 'name', str(e))
        tickers[name] = {}
        for s in probe_symbols:
            try:
                # Prefer adapter/feeder snapshot when the ws feed feature is enabled
                # or a feeder is registered for this exchange. This avoids per-symbol
                # blocking fetch_ticker REST calls when a feeder can supply recent
                # prices.
                price = None
                use_ws_feed = os.environ.get('ARB_USE_WS_FEED', '').lower() in ('1', 'true', 'yes')
                if use_ws_feed:
                    try:
                        try:
                            from arbitrage.exchanges.ws_feed_manager import get_feeder
                        except Exception:
                            from .src.arbitrage.exchanges.ws_feed_manager import get_feeder  # type: ignore
                        feeder = get_feeder(getattr(e, 'name', name))
                    except Exception:
                        feeder = None
                    # if adapter exposes get_tickers use that first (covers mock and adapters)
                    if hasattr(e, 'get_tickers'):
                        try:
                            tk = e.get_tickers() or {}
                            # tk may be {sym: {'last': price}} or {sym: price}
                            v = tk.get(s)
                            if v is None:
                                # try alternate symbol formats
                                v = tk.get(s.replace('/', '-')) or tk.get(s.replace('-', '/'))
                            if isinstance(v, dict):
                                price = v.get('last') or v.get('price')
                                used_feeder = True
                            elif isinstance(v, (int, float)):
                                price = float(v)
                                used_feeder = True
                        except Exception:
                            price = None
                    # otherwise try feeder directly
                    if price is None and feeder is not None and hasattr(feeder, 'get_tickers'):
                        try:
                            tk = feeder.get_tickers() or {}
                            v = tk.get(s) or tk.get(s.replace('/', '-')) or tk.get(s.replace('-', '/'))
                            if isinstance(v, dict):
                                price = v.get('last') or v.get('price')
                                used_feeder = True
                            elif isinstance(v, (int, float)):
                                price = float(v)
                                used_feeder = True
                        except Exception:
                            price = None
                # fallback to client.fetch_ticker if no feeder/adapter price available
                if price is None:
                    client = getattr(e, 'client', None)
                    if client is not None and hasattr(client, 'fetch_ticker'):
                        print(f'  [quick_scan] {name} fetch_ticker {s}')
                        fetch_ticker_calls += 1
                        t = client.fetch_ticker(s)
                        price = t.get('last') if isinstance(t, dict) else None
                    else:
                        if hasattr(e, 'get_tickers'):
                            tk = e.get_tickers()
                            price = tk.get(s)
                        else:
                            price = None
            except Exception as exn:
                print(f'  [quick_scan] {name} {s} fetch failed: {exn}')
                price = None
            if price is not None:
                tickers[name][s] = price
                # record whether this came from feeder lookup or direct fetch
                try:
                    if 'used_feeder' in locals() and used_feeder:
                        feeder_hits += 1
                    # clear flag for next symbol
                    if 'used_feeder' in locals():
                        del used_feeder
                except Exception:
                    pass

    opps = []
    for s in probe_symbols:
        prices = [(name, data.get(s)) for name, data in tickers.items() if data.get(s) is not None]
        for i in range(len(prices)):
            for j in range(len(prices)):
                if i == j:
                    continue
                bi, bp = prices[i]
                si, sp = prices[j]
                try:
                    if bp <= 0 or sp <= 0:
                        continue
                    profit = ((sp - bp) / bp) * 100.0
                except Exception:
                    continue
                if profit >= min_profit_pct:
                    class O: pass
                    o = O()
                    o.symbol = s
                    o.buy_exchange = bi
                    o.sell_exchange = si
                    o.buy_price = bp
                    o.sell_price = sp
                    o.profit_pct = profit
                    o.buy_withdraw = True
                    o.sell_deposit = True
                    opps.append(o)
    print(f'quick_scan found {len(opps)} opportunities')
    if collect_metrics:
        return opps, {'feeder_hits': feeder_hits, 'fetch_ticker_calls': fetch_ticker_calls}
    return opps


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--fast', action='store_true', help='Use fast, lightweight probes (fewer network calls)')
    args = p.parse_args()

    exs = None
    try:
        exs = live_mode(fast=args.fast)
    except Exception:
        traceback.print_exc()
    if not exs:
        exs = mock_mode()

    # run a quick, time-boxed scanner in fast mode, otherwise run full scanner
    if args.fast:
        print('Running quick, time-boxed scan (fast mode)')
        opps = quick_scan(exs, probe_symbols=None, min_profit_pct=0.05, amount=0.01)
    else:
        print('Running full scanner (this may take a while)')
        opps = find_executable_opportunities(exs, amount=0.01, min_profit_pct=0.05)
    if not opps:
        print('No opportunities found')
        return

    # Filter: exclude leveraged tokens (3S / 3L) when either side is gate or bitrue
    def is_leveraged_pair(sym: str) -> bool:
        if not isinstance(sym, str):
            return False
        up = sym.upper()
        return '3S' in up or '3L' in up

    filtered = []
    for o in opps:
        be = getattr(o, 'buy_exchange', '') or ''
        se = getattr(o, 'sell_exchange', '') or ''
        sym = getattr(o, 'symbol', '') or ''
        if (be.lower() in ('gate', 'bitrue') or se.lower() in ('gate', 'bitrue')) and is_leveraged_pair(sym):
            # skip leveraged token pairs on these exchanges
            continue
        filtered.append(o)
    opps = filtered
    if not opps:
        print('No opportunities left after leveraged-pair filtering')
        return

    print(f'Found {len(opps)} opportunities (top 10):')
    for o in opps[:10]:
        pprint(o)

    # helper: find exchange adapter object by its reported name
    def find_ex_obj(name: str):
        for e in exs:
            if getattr(e, 'name', '') == name:
                return e
        # fallback: case-insensitive match
        lname = name.lower()
        for e in exs:
            if getattr(e, 'name', '').lower() == lname:
                return e
        return None

    def notional_available(side: list[tuple[float, float]], required_amount: float) -> float:
        remaining = required_amount
        tot = 0.0
        for p, s in side:
            take = min(s, remaining)
            tot += take * p
            remaining -= take
            if remaining <= 0:
                break
        return tot if remaining <= 0 else 0.0

    def top_n_notional(side: list[tuple[float, float]], n: int = 5) -> float:
        tot = 0.0
        for p, s in side[:n]:
            tot += p * s
        return tot

    # save full output to a timestamped text file for review
    import datetime
    ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out_dir = os.path.join(ROOT, 'out')
    os.makedirs(out_dir, exist_ok=True)
    out_md = os.path.join(out_dir, f'opportunities_{ts}.md')
    out_jsonl = os.path.join(out_dir, f'opportunities_{ts}.jsonl')

    header = f"""# Arbitrage opportunities snapshot — {ts} (UTC)

Exchanges used: {', '.join([getattr(e, 'name', str(e)) for e in exs])}

This report lists executable opportunities discovered by the scanner. Depth metrics show USD notional available on each side for the requested trade amount and the total USD value of the top 5 levels.

| # | Symbol | Buy @ Exchange (eff) | Sell @ Exchange (eff) | Profit % | BuyDepth (USD for amount) | SellDepth (USD for amount) | Top5AskUSD | Top5BidUSD | BuyW | SellD |
|---:|:-------|:--------------------:|:---------------------:|:--------:|:-------------------------:|:--------------------------:|:----------:|:----------:|:----:|:-----:|
"""

    json_lines = []
    with open(out_md, 'w', encoding='utf-8') as fmd, open(out_jsonl, 'w', encoding='utf-8') as fj:
        fmd.write(header)
        for idx, o in enumerate(opps, start=1):
            sym = getattr(o, 'symbol', '')
            buy_ex_name = getattr(o, 'buy_exchange', '')
            sell_ex_name = getattr(o, 'sell_exchange', '')
            buy_eff = getattr(o, 'buy_price', 0.0)
            sell_eff = getattr(o, 'sell_price', 0.0)
            profit = getattr(o, 'profit_pct', 0.0)
            bw = getattr(o, 'buy_withdraw', True)
            sd = getattr(o, 'sell_deposit', True)

            buy_ex_obj = find_ex_obj(buy_ex_name)
            sell_ex_obj = find_ex_obj(sell_ex_name)

            buy_depth = 0.0
            sell_depth = 0.0
            top5_ask = 0.0
            top5_bid = 0.0
            # attempt to fetch orderbooks and compute USD notional metrics
            try:
                if buy_ex_obj and hasattr(buy_ex_obj, 'get_order_book'):
                    ob = buy_ex_obj.get_order_book(sym)
                    asks = ob.get('asks', [])
                    buy_depth = notional_available(asks, amount)
                    top5_ask = top_n_notional(asks, 5)
            except Exception as e:
                # on error leave zeros and continue
                buy_depth = 0.0
            try:
                if sell_ex_obj and hasattr(sell_ex_obj, 'get_order_book'):
                    ob = sell_ex_obj.get_order_book(sym)
                    bids = ob.get('bids', [])
                    sell_depth = notional_available(bids, amount)
                    top5_bid = top_n_notional(bids, 5)
            except Exception:
                sell_depth = 0.0

            # write markdown table row (rounded numbers to sensible precision)
            fmd.write(f"| {idx} | {sym} | {buy_ex_name} @ {buy_eff:.6f} | {sell_ex_name} @ {sell_eff:.6f} | {profit:.3f}% | ${buy_depth:,.2f} | ${sell_depth:,.2f} | ${top5_ask:,.2f} | ${top5_bid:,.2f} | {('✔' if bw else '✖')} | {('✔' if sd else '✖')} |\n")

            record = {
                'rank': idx,
                'symbol': sym,
                'buy_exchange': buy_ex_name,
                'sell_exchange': sell_ex_name,
                'buy_price': buy_eff,
                'sell_price': sell_eff,
                'profit_pct': profit,
                'buy_depth_usd_for_amount': buy_depth,
                'sell_depth_usd_for_amount': sell_depth,
                'top5_ask_usd': top5_ask,
                'top5_bid_usd': top5_bid,
                'buy_withdraw': bool(bw),
                'sell_deposit': bool(sd),
            }
            # attach currency metadata (if adapter supports it)
            try:
                buy_cd = None
                sell_cd = None
                if buy_ex_obj and hasattr(buy_ex_obj, 'get_currency_details'):
                    buy_cd = buy_ex_obj.get_currency_details(sym)
                if sell_ex_obj and hasattr(sell_ex_obj, 'get_currency_details'):
                    sell_cd = sell_ex_obj.get_currency_details(sym)
                if buy_cd is not None:
                    record['buy_currency_details'] = buy_cd
                if sell_cd is not None:
                    record['sell_currency_details'] = sell_cd
            except Exception:
                pass
            fj.write(json.dumps(record) + '\n')
            json_lines.append(record)

    print('Saved Markdown report to', out_md)
    print('Saved machine-friendly JSONL to', out_jsonl)


if __name__ == '__main__':
    main()
