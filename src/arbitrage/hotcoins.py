from __future__ import annotations

import time
from typing import List, Dict, Optional
import os
import json
from urllib import request, parse

from .utils import coingecko


def _http_get_json(url: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        req = request.Request(url, headers={"User-Agent": "arb-hotcoins/1.0"})
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode('utf-8'))
    except Exception:
        return None


def _parse_binance_symbol(sym: str) -> tuple[str, str]:
    """Return (base, quote) for a Binance symbol string (e.g. BTCUSDT -> (BTC, USDT))."""
    # common stable/quote suffixes to consider
    quotes = ['USDT', 'BUSD', 'USDC', 'USD', 'BTC', 'ETH']
    # normalize symbol: remove separators so both 'BTCUSDT' and 'BTC/USDT'
    # are handled uniformly and base/quote values do not contain '/' or '-'
    s = (sym or '').upper().replace('/', '').replace('-', '')
    for q in quotes:
        if s.endswith(q) and len(s) > len(q):
            base = s[:-len(q)]
            return base, q
    # fallback: split in middle (not ideal)
    if '/' in s:
        parts = s.split('/')
        if len(parts) == 2:
            return parts[0], parts[1]
    # last-resort: treat last 3 chars as quote
    return s[:-3], s[-3:]


def _binance_top_by_volume(top_n: int = 20, quote_filters: Optional[List[str]] = None) -> List[dict]:
    """Query Binance 24h tickers and return list of dicts sorted by base `volume` descending.

    Only include symbols whose quote asset is in quote_filters (if provided).
    Each item contains: symbol, base, quote, last, volume (base 24h), quoteVolume (quote-denominated 24h),
    and priceChangePercent.
    """
    url = 'https://api.binance.com/api/v3/ticker/24hr'
    data = _http_get_json(url, timeout=10.0)
    if not isinstance(data, list):
        return []
    out: List[dict] = []
    qf = {q.upper() for q in (quote_filters or ['USDT'])}
    for item in data:
        try:
            sym = item.get('symbol')
            if not sym:
                continue
            base, quote = _parse_binance_symbol(sym)
            base = (base or '').upper()
            quote = (quote or '').upper()
            symu = sym.upper()
            if any(marker in symu for marker in ('PERP',)):
                continue
            if base.endswith('FD') or base.endswith('3L') or base.endswith('3S'):
                continue
            if qf and quote not in qf:
                continue
            qvol_quote = item.get('quoteVolume') or 0
            try:
                qvol_quote = float(qvol_quote)
            except Exception:
                qvol_quote = 0.0
            qvol_base = item.get('volume') or 0
            try:
                qvol_base = float(qvol_base)
            except Exception:
                qvol_base = 0.0
            last = item.get('lastPrice')
            try:
                last = float(last) if last is not None else None
            except Exception:
                last = None
            pcp = item.get('priceChangePercent') or item.get('priceChange')
            try:
                pcp_val = float(pcp) if pcp is not None else None
            except Exception:
                pcp_val = None
            out.append({'symbol': sym, 'base': base, 'quote': quote, 'last': last, 'volume': qvol_base, 'quoteVolume': qvol_quote, 'priceChangePercent': pcp_val})
        except Exception:
            continue
    # Sort by 24h quote-denominated volume to match common UI (Binance app)
    out.sort(key=lambda x: x.get('quoteVolume', 0.0), reverse=True)
    return out[:top_n]


def _coingecko_top_symbols_by_marketcap(bases: List[str], limit: int = 20) -> List[str]:
    """Return the top `limit` bases by market cap among the provided bases.

    Uses the `utils.coingecko.get_metrics_for_bases` helper (cached) to avoid
    querying CoinGecko for the global top list. Returns list of base symbols
    in UPPER case sorted by market cap desc.
    """
    try:
        # coingecko.get_metrics_for_bases respects ARB_USE_COINGECKO env and caching
        metrics = coingecko.get_metrics_for_bases(bases)
        # metrics: base_upper -> (market_cap, volume)
        entries = []
        for b in bases:
            key = (b or '').strip().upper()
            mc, _ = metrics.get(key, (None, None))
            try:
                mc_val = float(mc) if mc is not None else 0.0
            except Exception:
                mc_val = 0.0
            entries.append((key, mc_val))

        # If metrics are missing or all zero (e.g., ARB_USE_COINGECKO disabled or cache miss),
        # fall back to querying CoinGecko's global market-cap list so we can still
        # exclude well-known top market-cap coins (BTC, ETH, etc.). This ensures the
        # exclusion behaves as the user expects even when per-base metrics are absent.
        any_mc = any(e[1] > 0 for e in entries)
        if not any_mc:
            try:
                # fetch global markets (page 1, top by market cap)
                url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1'
                data = _http_get_json(url, timeout=10.0)
                global_top = []
                if isinstance(data, list):
                    for item in data:
                        try:
                            s = (item.get('symbol') or '').strip().upper()
                            if s:
                                global_top.append(s)
                        except Exception:
                            continue
                # return those global-top symbols that appear in our candidate bases
                bases_set = { (b or '').strip().upper() for b in bases if b }
                filtered = [s for s in global_top if s in bases_set]
                return filtered[:limit]
            except Exception:
                # fallback to empty exclude set
                return []

        # sort by market cap desc and return top limit bases (only those with mc > 0)
        entries.sort(key=lambda x: x[1], reverse=True)
        return [e[0] for e in entries[:limit] if e[1] > 0]
    except Exception:
        return []


def find_hot_coins(
    exchanges: List[object] | None = None,
    max_results: int = 20,
    exclude_top_by_marketcap: int = 20,
) -> List[Dict]:
    """Return top coins by 24h quote volume from Binance, excluding the top-N by market cap.

    - exchanges parameter is accepted for compatibility but ignored when using Binance REST.
    - max_results controls how many coins to return after exclusion.
    """
    # If feeders were passed in, prefer their in-memory snapshots so hotcoins
    # reports can be truly real-time and avoid slow external REST calls.
    now = time.time()
    # items collects candidate symbols whether from feeders or Binance REST
    items = []
    if exchanges:
        # map symbol -> estimated orderbook notional (top-N asks+bids sum)
        depth_map: dict = {}
        # Collect tickers/orderbook-derived notional from provided feeders
        for feeder in exchanges:
            try:
                tickers = feeder.get_tickers() if hasattr(feeder, 'get_tickers') else {}
            except Exception:
                tickers = {}
            for sym, info in (tickers.items() if isinstance(tickers, dict) else []):
                try:
                    last = None
                    try:
                        last = float(info.get('last')) if isinstance(info, dict) and info.get('last') is not None else None
                    except Exception:
                        last = None
                    base, quote = _parse_binance_symbol(sym)
                    base = (base or '').upper()
                    quote = (quote or '').upper()

                    # capture base and quote volumes from feeder tickers when provided
                    qvol_base = 0.0
                    qvol_quote = 0.0
                    try:
                        if isinstance(info, dict):
                            qvol_base = float(info.get('volume') or info.get('baseVolume') or 0)
                            qvol_quote = float(info.get('quoteVolume') or info.get('qv') or 0)
                    except Exception:
                        qvol_base = 0.0
                        qvol_quote = 0.0

                    # estimate an approximate orderbook notional from top of book if available
                    qnotional = 0.0
                    if hasattr(feeder, 'get_order_book'):
                        try:
                            ob = feeder.get_order_book(sym, depth=5) or {}
                            asks = ob.get('asks', [])
                            bids = ob.get('bids', [])
                            # sum top 5 asks + top 5 bids as an orderbook notional estimate
                            ssum = 0.0
                            for p, q in (asks[:5] + bids[:5]):
                                try:
                                    pn = float(p)
                                    qn = float(q)
                                    ssum += pn * qn
                                except Exception:
                                    continue
                            qnotional = ssum
                            # store in depth_map for later inclusion in results
                            try:
                                k_orig = sym
                                k_nosep = (base + quote) if base and quote else sym.replace('/', '').replace('-', '')
                                k_slash = f"{base}/{quote}" if base and quote else sym
                                depth_map[k_orig] = ssum
                                depth_map[k_nosep] = ssum
                                depth_map[k_slash] = ssum
                            except Exception:
                                depth_map[sym] = ssum
                        except Exception:
                            qnotional = 0.0

                    items.append({'symbol': sym, 'base': base, 'quote': quote, 'last': last, 'volume': qvol_base, 'quoteVolume': qvol_quote, 'orderbook_notional': qnotional, 'priceChangePercent': None})
                except Exception:
                    continue

    # sort by estimated base 24h traded volume (volume) desc and limit to a reasonable set
    top = []
    if items:
        # If feeders provided no 24h 'quoteVolume' data (many zeros), fall back to Binance REST
        has_qvol = any((i.get('quoteVolume') or 0.0) > 0.0 for i in items)
        if not has_qvol:
            # fall back to Binance REST to get canonical top-by-quoteVolume list
            top = _binance_top_by_volume(top_n=100)
        else:
            items.sort(key=lambda x: x.get('quoteVolume', 0.0), reverse=True)
            top = items[:100]

    # If feeders were provided but produced no candidates (empty `top`),
    # fall back to Binance REST so the hotcoins endpoint continues to
    # provide a reasonable list rather than an empty payload. This handles
    # the common startup race where feeders are registered but have not
    # yet populated their in-memory tickers/orderbooks.
    if exchanges and not top:
        try:
            top = _binance_top_by_volume(top_n=100)
        except Exception:
            top = []

    # If callers passed in `exchanges`, prefer the feeder-backed `top` list
    # (this avoids hitting Binance REST and preserves feeder-derived depth_map).
    if not exchanges:
        # If explicitly configured to use a different source, fall back to the old behavior
        source = os.environ.get('ARB_HOTCOINS_SOURCE', 'binance').strip().lower()
        if source != 'binance':
            # Preserve previous heuristic behaviour for non-binance sources by returning empty list
            return []

        # fetch top symbols by quote-volume from Binance REST when no feeders are provided
        top = _binance_top_by_volume(top_n=100)
        if not top:
            return []

    # If exchanges were provided (feeder snapshots), use a fast, local-only
    # path that avoids external CoinGecko/REST queries. This keeps hotcoins
    # reports truly real-time and bounded in latency. Ensure results are
    # sorted by quoteVolume descending and limited to max_results.
    if exchanges:
        bases = sorted({(item.get('base') or '').upper() for item in top if item.get('base')})

        # Determine exclusion set using CoinGecko when enabled; otherwise
        # fall back to a conservative built-in list of top marketcaps.
        try:
            # Enable CoinGecko enrichment by default unless explicitly disabled
            use_cg = os.environ.get('ARB_USE_COINGECKO', '1').strip() == '1'
        except Exception:
            use_cg = True

        # built-in fallback list
        bases_set = set(bases)
        DEFAULT_TOP_MARKETCAPS = {
            'BTC', 'ETH', 'USDT', 'USDC', 'BNB', 'ADA', 'XRP', 'DOGE', 'SOL', 'DOT',
            'BCH', 'LTC', 'LINK', 'MATIC', 'TRX', 'SHIB', 'AVAX', 'UNI', 'ATOM', 'WBTC'
        }

        if use_cg:
            try:
                exclude_syms = set(_coingecko_top_symbols_by_marketcap(bases=bases, limit=exclude_top_by_marketcap))
            except Exception:
                exclude_syms = set()
            # if CoinGecko returned nothing (cache miss or error), fall back to built-in list
            if not exclude_syms:
                exclude_syms = {s for s in DEFAULT_TOP_MARKETCAPS if s in bases_set}
        else:
            exclude_syms = {s for s in DEFAULT_TOP_MARKETCAPS if s in bases_set}

        # Attempt to enrich with CoinGecko marketCap and 24h change when available
        metrics: dict = {}
        try:
            if bases:
                try:
                    base_metrics = coingecko.get_metrics_for_bases(list(bases)) if bases else {}
                except Exception:
                    base_metrics = {}

                # populate initial marketCap from cached helper
                for b in bases:
                    key = b.upper()
                    mc, _ = base_metrics.get(key, (None, None))
                    try:
                        mc_val = float(mc) if mc is not None else None
                    except Exception:
                        mc_val = None
                    metrics[key] = {'marketCap': mc_val, 'change24h': None}

                # Try to resolve change24h via CoinGecko markets using cache ids
                try:
                    cg_cache = getattr(coingecko, '_CACHE', {})
                    ids_to_query = []
                    id_map = {}
                    for b in bases:
                        entry = cg_cache.get(b)
                        if entry and isinstance(entry, dict):
                            cid = entry.get('id')
                            if cid:
                                ids_to_query.append(cid)
                                id_map[cid] = b

                    if ids_to_query:
                        ids_param = ','.join(ids_to_query[:250])
                        url = f'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={parse.quote(ids_param)}&order=market_cap_desc&per_page=250&page=1&price_change_percentage=24h'
                        data = _http_get_json(url, timeout=10.0)
                        if isinstance(data, list):
                            for item in data:
                                try:
                                    cid = item.get('id')
                                    sym = (item.get('symbol') or '').strip().upper()
                                    if not sym:
                                        continue
                                    ch = item.get('price_change_percentage_24h')
                                    mc = item.get('market_cap')
                                    try:
                                        change_val = float(ch) if ch is not None else None
                                    except Exception:
                                        change_val = None
                                    try:
                                        mc_val = float(mc) if mc is not None else None
                                    except Exception:
                                        mc_val = None
                                    if sym in metrics:
                                        if metrics[sym].get('marketCap') is None:
                                            metrics[sym]['marketCap'] = mc_val
                                        metrics[sym]['change24h'] = change_val
                                except Exception:
                                    continue
                except Exception:
                    pass
        except Exception:
            metrics = {}

        results: List[Dict] = []
        rank = 0
        # Try to locate a KuCoin feeder instance (optional). Import locally to avoid
        # circular imports during module load.
        kucoin_feeder = None
        try:
            from .exchanges.ws_feed_manager import get_feeder as _get_feed
            kucoin_feeder = _get_feed('kucoin')
        except Exception:
            kucoin_feeder = None
        for item in top:
            base = (item.get('base') or '').upper()
            if not base:
                continue
            # skip top-marketcap exclusions
            if _is_excluded_base(base, exclude_syms):
                continue
            # also skip stablecoin-like bases so the top list shows tradable assets
            try:
                if _is_stablecoin_symbol(base):
                    continue
            except Exception:
                pass
            rank += 1

            # Prefer CoinGecko-enriched metric when available, otherwise
            # attempt to use Binance-provided priceChangePercent from the
            # top items; finally fall back to 0.0.
            mc_val = 0.0
            ch_val = None
            try:
                if metrics and base in metrics:
                    mc_raw = metrics.get(base, {}).get('marketCap')
                    try:
                        mc_val = float(mc_raw) if mc_raw is not None else 0.0
                    except Exception:
                        mc_val = 0.0
                    ch_raw = metrics.get(base, {}).get('change24h')
                    try:
                        ch_val = float(ch_raw) if ch_raw is not None else None
                    except Exception:
                        ch_val = None
            except Exception:
                mc_val = 0.0
                ch_val = None

            # fallback: use priceChangePercent from the feeder/top item if present
            if ch_val is None:
                try:
                    bcp = item.get('priceChangePercent')
                    if bcp is None:
                        bcp = item.get('priceChange')
                    if bcp is not None:
                        ch_val = float(bcp)
                except Exception:
                    ch_val = None

            try:
                ch_val = float(ch_val) if ch_val is not None else 0.0
            except Exception:
                ch_val = 0.0

            # attach any feeder-derived orderbook depth (USD) when available
            ob_depth = None
            try:
                if exchanges:
                    ob_depth = depth_map.get(item.get('symbol')) if 'depth_map' in locals() else None
            except Exception:
                ob_depth = None

            # If we have a KuCoin feeder available, try to attach top-of-book
            # info (best_ask/best_bid) and exchange-level arrays so the frontend
            # can display the exact KuCoin-computed prices. This is best-effort
            # and will be omitted if no feeder or no book snapshot is present.
            best_ask = None
            best_bid = None
            asks_exchanges = None
            bids_exchanges = None
            try:
                # try to prefer a simple last-price from the KuCoin feeder tickers
                preferred_buy_exchange = None
                preferred_buy_price = None
                tickers_map = None
                if kucoin_feeder is not None:
                    try:
                        if hasattr(kucoin_feeder, 'get_tickers'):
                            tickers_map = kucoin_feeder.get_tickers() or {}
                    except Exception:
                        tickers_map = None

                if kucoin_feeder is not None and (tickers_map is not None or hasattr(kucoin_feeder, 'get_order_book')):
                    # Try multiple symbol formats; feeder normalizes by stripping
                    # separators so passing item symbol should work generally.
                    sym = item.get('symbol') or ''
                    ob = None
                    # attempt to resolve a ticker 'last' price first
                    try:
                        if tickers_map and sym:
                            # try forms: 'BASE/QUOTE', 'BASEQUOTE', 'BASE-QUOTE'
                            cand_forms = [sym, sym.replace('-', '/'), sym.replace('-', ''), sym.replace('/', '-'), sym.replace('/', '')]
                            # if sym lacks a separator, try to split into base/quote using helper
                            if '/' not in sym and '-' not in sym:
                                try:
                                    b, q = _parse_binance_symbol(sym)
                                    cand_forms.insert(0, f"{b}/{q}")
                                except Exception:
                                    pass
                            found = None
                            for cf in cand_forms:
                                if not cf:
                                    continue
                                if cf in tickers_map:
                                    found = tickers_map.get(cf)
                                    break
                            if found and isinstance(found, dict) and found.get('last') is not None:
                                try:
                                    preferred_buy_price = float(found.get('last'))
                                    preferred_buy_exchange = 'KUCOIN'
                                except Exception:
                                    preferred_buy_price = None
                    except Exception:
                        preferred_buy_exchange = preferred_buy_price = None
                    try:
                        ob = kucoin_feeder.get_order_book(sym, depth=5)
                    except Exception:
                        try:
                            ob = kucoin_feeder.get_order_book(str(sym).replace('/', '-'), depth=5)
                        except Exception:
                            ob = None
                    if ob:
                        asks = ob.get('asks') or []
                        bids = ob.get('bids') or []
                        if asks:
                            try:
                                best_ask = float(asks[0][0])
                            except Exception:
                                best_ask = None
                        if bids:
                            try:
                                best_bid = float(bids[0][0])
                            except Exception:
                                best_bid = None
                        # attach exchange-level arrays with simple objects
                        if asks:
                            asks_exchanges = [{'exchange': 'KUCOIN', 'price': (float(a[0]) if a and len(a) > 0 else None), 'size': (float(a[1]) if a and len(a) > 1 else None)} for a in asks[:3]]
                        if bids:
                            bids_exchanges = [{'exchange': 'KUCOIN', 'price': (float(b[0]) if b and len(b) > 0 else None), 'size': (float(b[1]) if b and len(b) > 1 else None)} for b in bids[:3]]
                        # If we don't already have a preferred buy price from tickers,
                        # fall back to using the top-of-book best_ask as the preferred buy price.
                        if preferred_buy_price is None and best_ask is not None:
                            preferred_buy_exchange = 'KUCOIN'
                            preferred_buy_price = best_ask
            except Exception:
                best_ask = best_bid = None
                asks_exchanges = bids_exchanges = None

            results.append({
                'symbol': item.get('symbol'),
                'base': base,
                'quote': item.get('quote'),
                'last': item.get('last'),
                'volume': item.get('volume', 0.0),
                'quoteVolume': item.get('quoteVolume', 0.0),
                'orderbook_depth_usd': ob_depth,
                'best_ask': best_ask,
                'best_bid': best_bid,
                'asks_exchanges': asks_exchanges,
                'bids_exchanges': bids_exchanges,
                'preferred_buy_exchange': preferred_buy_exchange if 'preferred_buy_exchange' in locals() else None,
                'preferred_buy_price': preferred_buy_price if 'preferred_buy_price' in locals() else None,
                'marketCap': mc_val,
                'change24h': ch_val,
                'rank': rank,
                'ts': now,
            })
            if len(results) >= max_results:
                break

        return results[:max_results]


def _is_stablecoin_symbol(base: str) -> bool:
    """Return True if the base symbol looks like a stablecoin.

    We treat tokens with common stablecoin names or those containing 'USD'
    as stablecoins to avoid showing USD-pegged assets in the hot list.
    This intentionally errs on the side of excluding possible stables so
    the UI shows more interesting tradable assets.
    """
    if not base:
        return False
    b = (base or '').strip().upper()
    # common explicit stablecoin symbols
    KNOWN_STABLES = {
        'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'USDP', 'USDD', 'USDX', 'GUSD', 'FDUSD', 'USDE', 'SUSD', 'EURS', 'UST'
    }
    if b in KNOWN_STABLES:
        return True
    # treat anything that contains USD (e.g. 'FDUSD', 'XUSD') as stable-like
    if 'USD' in b:
        return True
    # common fiat-pegged prefixes/suffixes
    if b.startswith('USD') or b.endswith('USD'):
        return True
    return False


def _normalize_symbol_key(s: str) -> str:
    """Normalize a symbol/base for comparison: uppercase, strip non-alphanum."""
    if not s:
        return ''
    import re
    return re.sub(r'[^A-Z0-9]', '', (s or '').strip().upper())


def _is_excluded_base(base: str, exclude_syms: set) -> bool:
    """Return True if `base` should be excluded based on the exclude_syms set.

    This does aggressive matching to handle variants like 'WBTC' -> 'BTC',
    wrapped tokens, suffixes/prefixes, and small naming differences.
    """
    if not base:
        return False
    b = _normalize_symbol_key(base)
    if not b:
        return False
    # quick path
    if b in exclude_syms:
        return True
    for es in exclude_syms:
        e = _normalize_symbol_key(es)
        if not e:
            continue
        # exact or substring matches (aggressive)
        if b == e or b.endswith(e) or b.startswith(e) or (e in b) or (b in e):
            return True
        # handle wrapped forms like WBTC -> BTC, or XBTC -> BTC
        if len(b) > len(e) and b.endswith(e):
            return True
        # strip common wrapper prefixes
        if b.startswith('W') and b[1:] == e:
            return True
    return False
