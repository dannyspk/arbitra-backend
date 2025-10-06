from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional
import time
import os
try:
    from arbitrage.utils.coingecko import get_metrics_for_base
except Exception:
    # when running tests or if module unavailable, provide a noop
    def get_metrics_for_base(base: str):
        return None, None


@dataclass
class Opportunity:
    buy_exchange: str
    sell_exchange: str
    symbol: str
    buy_price: float
    sell_price: float
    profit_pct: float
    # optional flags indicating whether the buy exchange supports withdrawing
    # the base asset and whether the sell exchange supports depositing it.
    buy_withdraw: bool = True
    sell_deposit: bool = True


def find_opportunities(exchanges: List[object], min_profit_pct: float = 0.1) -> List[Opportunity]:
    """Scan the provided exchange adapters for arbitrage opportunities.

    - exchanges: list of exchange objects implementing .get_tickers() -> {symbol: Ticker}
    - min_profit_pct: minimal profit percentage (e.g. 0.1 means 0.1%)

    This naive scanner only looks for the same symbol across exchanges and computes
    a simple (sell - buy)/buy * 100 profit percentage.
    """
    # Helper: normalize various ticker shapes into (price: float, timestamp: Optional[float])
    def _normalize_tk(tk) -> tuple[float | None, Optional[float]]:
        try:
            if tk is None:
                return None, None
            # numeric
            if isinstance(tk, (int, float)):
                return float(tk), None
            # dict-like
            if isinstance(tk, dict):
                for k in ('last', 'price', 'close', 'mid'):
                    if k in tk and tk.get(k) is not None:
                        try:
                            return float(tk.get(k)), float(tk.get('timestamp')) if 'timestamp' in tk and tk.get('timestamp') is not None else None
                        except Exception:
                            pass
                return None, None
            # object-like (ccxt.Ticker or similar)
            if hasattr(tk, 'last') and getattr(tk, 'last') is not None:
                try:
                    price = float(getattr(tk, 'last'))
                except Exception:
                    price = None
            else:
                price = None
            if price is None and hasattr(tk, 'price') and getattr(tk, 'price') is not None:
                try:
                    price = float(getattr(tk, 'price'))
                except Exception:
                    price = None
            ts = None
            if hasattr(tk, 'timestamp') and getattr(tk, 'timestamp') is not None:
                try:
                    ts = float(getattr(tk, 'timestamp'))
                except Exception:
                    ts = None
            return (price, ts) if price is not None else (None, None)
        except Exception:
            return None, None

    # Build a mapping symbol -> list of (exchange_obj, exchange_name, price, timestamp)
    market = {}
    for ex in exchanges:
        try:
            tickers = ex.get_tickers()
        except Exception:
            tickers = {}
        if not isinstance(tickers, dict):
            continue
        for sym, tk in tickers.items():
            price, ts = _normalize_tk(tk)
            if price is None:
                continue
            market.setdefault(sym, []).append((ex, ex.name, float(price), ts))

    opportunities: List[Opportunity] = []
    for sym, quotes in market.items():
        # need at least two exchanges to compare
        if len(quotes) < 2:
            continue
        # find best effective buy (lowest) and sell (highest) using raw prices
        quotes_sorted = sorted(quotes, key=lambda x: x[2])
        buy_obj, buy_ex, buy_price, buy_ts = quotes_sorted[0]
        sell_obj, sell_ex, sell_price, sell_ts = quotes_sorted[-1]
        if sell_price <= buy_price:
            continue
        profit_pct = (sell_price - buy_price) / buy_price * 100.0
        if profit_pct >= min_profit_pct:
            opportunities.append(
                Opportunity(buy_exchange=buy_ex, sell_exchange=sell_ex, symbol=sym, buy_price=buy_price, sell_price=sell_price, profit_pct=profit_pct)
            )

    # sort by profit descending
    opportunities.sort(key=lambda o: o.profit_pct, reverse=True)
    return opportunities


def vwap_price_from_orderbook(side: List[Tuple[float, float]], amount: float) -> float | None:
    """Compute the effective price to fill `amount` using a list of (price, size)
    entries from an orderbook side (asks or bids). The side should be ordered
    best-first (e.g. for asks: lowest price first; for bids: highest price first).

    Returns the volume-weighted average price for the filled volume, or None if
    the available size is insufficient.
    """
    remaining = amount
    total_cost = 0.0
    total_filled = 0.0
    for price, size in side:
        if remaining <= 0:
            break
        take = min(size, remaining)
        total_cost += take * price
        total_filled += take
        remaining -= take
    if total_filled <= 0 or remaining > 0:
        return None
    return total_cost / total_filled


def _are_same_asset(ex_a: object, symbol_a: str, ex_b: object, symbol_b: str) -> bool:
    """Best-effort check whether symbol_a on ex_a and symbol_b on ex_b refer to the same asset.

    This is heuristic-only. It checks:
    - exact symbol equality
    - base token equality (e.g., BTC/USDT -> BTC)
    - looks for chain hints in exchange names or symbol suffixes (e.g., 'SOL' vs 'ETH')
    Returns True if likely same asset, False if clearly different (e.g., same base but different chain hints).
    """
    if symbol_a == symbol_b:
        return True
    def base(sym: str) -> str:
        if '/' in sym:
            return sym.split('/')[0]
        if '-' in sym:
            return sym.split('-')[0]
        return sym

    base_a = base(symbol_a).upper()
    base_b = base(symbol_b).upper()
    if base_a != base_b:
        return False

    # look for chain hints in exchange names or symbol text
    # e.g., MEXC listing might include '/SOL' or '.SOL' or exchange name contains 'sol'
    name_a = getattr(ex_a, 'name', '') or ''
    name_b = getattr(ex_b, 'name', '') or ''
    combined = (name_a + ' ' + name_b + ' ' + symbol_a + ' ' + symbol_b).lower()
    # if one mentions 'sol' and the other mentions 'eth' or 'bep2' etc, consider different
    chain_indicators = ['sol', 'eth', 'bep2', 'bep20', 'erc20', 'tron', 'trc20', 'matic', 'avax']
    present = [c for c in chain_indicators if c in combined]
    if len(present) >= 2:
        # if two different chains appear in the combined string and they're different, likely not same asset
        # crude check: if both 'sol' and 'eth' appear, reject
        if not all(p == present[0] for p in present):
            return False

    return True


def find_executable_opportunities(
    exchanges: List[object],
    amount: float = 1.0,
    min_profit_pct: float = 0.1,
    min_price_diff_pct: float = 1.0,
    *,
    min_price: float = 1e-6,
    min_notional: float = 0.0,
    min_listing_age_seconds: float = 0.0,
    min_top_level_size: float = 0.0001,
    allow_ticker_fallback: bool = True,
    min_side_notional: float = 0.0,
) -> List[Opportunity]:
    """Scan exchanges for executable arbitrage opportunities for a given `amount`.

    For exchanges that expose `get_order_book(symbol)` this function will use the
    order book to compute an executable buy price (fill on asks) and executable
    sell price (fill on bids). For exchanges without order books it falls back
    to the naive `find_opportunities` ticker-based scan using mid/last prices.

    This function does NOT account for fees or withdrawal/deposit times — those
    must be applied by the caller (or extended here) before executing.
    """
    # Phase 1: collect tickers and build candidate pairs using ticker prices only
    market: dict[str, list[tuple[object, str, float, Optional[float]]]] = {}
    # Optionally pre-filter tickers by market metrics to reduce the symbol set.
    strict_metrics = os.getenv('ARB_STRICT_METRICS', '0') == '1'
    # thresholds
    MC_THRESHOLD = 1_000_000_000  # $1B
    VOL24_THRESHOLD = 100_000.0    # $100k
    # simple per-base cache to avoid repeated metadata calls
    _base_metrics_cache: dict[str, tuple[float | None, float | None]] = {}

    def _get_base_metrics_from_exchange(base: str, ex: object) -> tuple[float | None, float | None]:
        """Try to fetch marketcap and 24h volume for `base` using a single exchange adapter.
        Returns (marketcap, volume24h) where values may be None when not available.
        """
        # cached
        if base in _base_metrics_cache:
            return _base_metrics_cache[base]
        mc = None
        vol = None
        try:
            if hasattr(ex, 'get_currency_details'):
                try:
                    cd = ex.get_currency_details(base)
                except Exception:
                    cd = None
                if isinstance(cd, dict):
                    for mk in ('marketCap', 'market_cap', 'marketCapUsd', 'market_cap_usd'):
                        v = cd.get(mk)
                        if v is not None:
                            try:
                                mc = float(v)
                                break
                            except Exception:
                                pass
                    info = cd.get('info') if isinstance(cd.get('info'), dict) else None
                    if isinstance(info, dict):
                        for vk in ('volume24h', 'volume_24h', 'quoteVolume', 'volume'):
                            vv = info.get(vk)
                            if vv is not None:
                                try:
                                    vol = float(vv)
                                    break
                                except Exception:
                                    pass
            client = getattr(ex, 'client', None)
            if client is not None and hasattr(client, 'fetch_ticker'):
                # try a ticker to obtain 24h volume if possible; perform network calls
                # in a thread with a short timeout to avoid blocking the scanner.
                try:
                    timeout_s = float(os.environ.get('TMP_FETCH_TICKER_TIMEOUT_S', '1.0'))
                except Exception:
                    timeout_s = 1.0
                t = None
                try:
                    from concurrent.futures import ThreadPoolExecutor

                    def _call_fetch(sym: str):
                        try:
                            return client.fetch_ticker(sym)
                        except Exception:
                            return None

                    with ThreadPoolExecutor(max_workers=1) as _exe:
                        fut = _exe.submit(_call_fetch, base + '/USDT')
                        try:
                            t = fut.result(timeout=timeout_s)
                        except Exception:
                            # try USD variant briefly
                            try:
                                fut2 = _exe.submit(_call_fetch, base + '/USD')
                                t = fut2.result(timeout=timeout_s)
                            except Exception:
                                t = None
                except Exception:
                    t = None
                if isinstance(t, dict) and t is not None:
                    for vol_key in ('quoteVolume', 'baseVolume', 'volume', 'quoteVolume24h'):
                        if vol_key in t and t.get(vol_key) is not None:
                            try:
                                v = float(t.get(vol_key))
                                if vol_key == 'baseVolume' and t.get('last'):
                                    try:
                                        last = float(t.get('last'))
                                        v = v * last
                                    except Exception:
                                        pass
                                vol = v
                                break
                            except Exception:
                                pass
        except Exception:
            pass
        # if CoinGecko is enabled, prefer its metrics for the base
        try:
            cg_mc, cg_vol = get_metrics_for_base(base)
            if cg_mc is not None or cg_vol is not None:
                # if either value present prefer coingecko value(s)
                return (cg_mc if cg_mc is not None else mc, cg_vol if cg_vol is not None else vol)
        except Exception:
            pass
        _base_metrics_cache[base] = (mc, vol)
        return mc, vol

    SYMBOLS_THRESHOLD = 500
    # record per-exchange symbol counts so phase-2 can decide whether to apply strict filtering
    ex_symbol_counts: dict[int, int] = {}
    for ex in exchanges:
        try:
            tickers = ex.get_tickers()
        except Exception:
            tickers = {}
        ex_symbol_count = len(tickers) if isinstance(tickers, dict) else 0
        ex_symbol_counts[id(ex)] = ex_symbol_count
        if not isinstance(tickers, dict):
            continue
        for sym, tk in tickers.items():
            try:
                base = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
                mc, vol24 = _base_metrics_cache.get(base, (None, None))
                if mc is None and strict_metrics:
                    mc, vol24 = _get_base_metrics_from_exchange(base, ex)
                # If strict metrics enabled, only exclude when both metrics are known
                # and the token fails the thresholds. If metrics are unknown, keep the
                # symbol (conservative) so tests and partial data aren't filtered out.
                # Only apply strict filtering when enabled and the exchange has many symbols
                apply_strict_here = strict_metrics and ex_symbol_count > SYMBOLS_THRESHOLD
                if apply_strict_here and (mc is not None and vol24 is not None):
                    if not (mc < MC_THRESHOLD and vol24 >= VOL24_THRESHOLD):
                        continue
                # normalize ticker shapes to avoid Ticker object comparisons
                def _normalize_local(tk_local):
                    try:
                        if tk_local is None:
                            return None, None
                        if isinstance(tk_local, (int, float)):
                            return float(tk_local), None
                        if isinstance(tk_local, dict):
                            for k in ('last', 'price', 'close', 'mid'):
                                if k in tk_local and tk_local.get(k) is not None:
                                    try:
                                        return float(tk_local.get(k)), float(tk_local.get('timestamp')) if 'timestamp' in tk_local and tk_local.get('timestamp') is not None else None
                                    except Exception:
                                        pass
                            return None, None
                        if hasattr(tk_local, 'last') and getattr(tk_local, 'last') is not None:
                            try:
                                return float(getattr(tk_local, 'last')), float(getattr(tk_local, 'timestamp')) if hasattr(tk_local, 'timestamp') and getattr(tk_local, 'timestamp') is not None else None
                            except Exception:
                                return None, None
                        if hasattr(tk_local, 'price') and getattr(tk_local, 'price') is not None:
                            try:
                                return float(getattr(tk_local, 'price')), None
                            except Exception:
                                return None, None
                        return None, None
                    except Exception:
                        return None, None

                price_val, ts = _normalize_local(tk)
                if price_val is None:
                    continue
                market.setdefault(sym, []).append((ex, ex.name, float(price_val), ts))
            except Exception:
                continue

    opportunities: List[Opportunity] = []
    max_age_seconds = 5.0
    transfer_cost_default = 0.0

    candidates: list[tuple] = []
    for sym, quotes in market.items():
        if len(quotes) < 2:
            continue
        for i in range(len(quotes)):
            for j in range(len(quotes)):
                if i == j:
                    continue
                buy_obj, buy_ex, buy_price, buy_ts = quotes[i]
                sell_obj, sell_ex, sell_price, sell_ts = quotes[j]
                now = time.time()
                if buy_ts is not None and sell_ts is not None:
                    if abs(buy_ts - sell_ts) > max_age_seconds:
                        continue
                    if (now - buy_ts) > max_age_seconds or (now - sell_ts) > max_age_seconds:
                        continue
                # quick raw-price filter to avoid scanning tiny spreads
                raw_diff_pct = (sell_price - buy_price) / buy_price * 100.0 if buy_price > 0 else 0.0
                if raw_diff_pct < min_price_diff_pct:
                    continue

                buy_fee = getattr(buy_obj, "fee_rate", 0.0)
                sell_fee = getattr(sell_obj, "fee_rate", 0.0)
                effective_buy = buy_price * (1.0 + buy_fee)
                effective_sell = sell_price * (1.0 - sell_fee)
                transfer_cost = getattr(sell_obj, "withdraw_fee", transfer_cost_default)
                net_profit = effective_sell - effective_buy - transfer_cost
                if net_profit <= 0:
                    continue
                profit_pct = net_profit / effective_buy * 100.0
                if profit_pct >= min_profit_pct:
                    # basic exclusion filters
                    if buy_price < min_price or sell_price < min_price:
                        continue
                    if (buy_price * amount) < min_notional:
                        continue
                    now = time.time()
                    if buy_ts is not None and (now - buy_ts) < min_listing_age_seconds:
                        continue
                    if sell_ts is not None and (now - sell_ts) < min_listing_age_seconds:
                        continue

                    # ensure the base asset is the same across exchanges (best-effort)
                    try:
                        same = _are_same_asset(buy_obj, sym, sell_obj, sym)
                    except Exception:
                        same = True
                    if not same:
                        continue

                    # Ensure withdraw/deposit availability: the exchange where we buy
                    # must allow withdrawals of the base asset, and the exchange where
                    # we sell must allow deposits for the base asset. We call
                    # supports_withdraw/supports_deposit if available; if the
                    # adapter does not provide such a method, we conservatively
                    # assume support (fail-open).
                    base_token = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
                    # Check supports_withdraw/supports_deposit with a short timeout to avoid blocking
                    def _call_bool_method_with_timeout(obj, method_name: str, arg, timeout_s: float = 0.5) -> bool:
                        try:
                            if not hasattr(obj, method_name):
                                return True
                            meth = getattr(obj, method_name)
                            from concurrent.futures import ThreadPoolExecutor

                            def _call():
                                try:
                                    return bool(meth(arg))
                                except Exception:
                                    return True

                            with ThreadPoolExecutor(max_workers=1) as _exe:
                                fut = _exe.submit(_call)
                                try:
                                    return fut.result(timeout=timeout_s)
                                except Exception:
                                    return True
                        except Exception:
                            return True

                    if not _call_bool_method_with_timeout(buy_obj, 'supports_withdraw', base_token):
                        continue
                    if not _call_bool_method_with_timeout(sell_obj, 'supports_deposit', base_token):
                        continue

                    # record the withdraw/deposit support as available from adapters
                    buy_withdraw = True
                    sell_deposit = True
                    # fetch support flags with timeboxed calls (fail-open)
                    try:
                        buy_withdraw = _call_bool_method_with_timeout(buy_obj, 'supports_withdraw', base_token)
                    except Exception:
                        buy_withdraw = True
                    try:
                        sell_deposit = _call_bool_method_with_timeout(sell_obj, 'supports_deposit', base_token)
                    except Exception:
                        sell_deposit = True

                    # Skip if buy side cannot withdraw or sell side cannot deposit
                    if not buy_withdraw or not sell_deposit:
                        continue

                    candidates.append((sym, buy_obj, buy_ex, buy_price, sell_obj, sell_ex, sell_price, buy_withdraw, sell_deposit))

    # reporting: how many tickers/candidates we collected
    try:
        print(f'[scanner] collected {len(market)} ticker symbols across exchanges')
        print(f'[scanner] built {len(candidates)} candidate pairs for orderbook verification')
    except Exception:
        pass

    # Phase 2: fetch order books only for candidate symbols and recompute executable prices
    # New: filter candidates by market metrics to reduce number of orderbook fetches
    def _collect_symbol_metrics(sym: str, involved_exchanges: list[object]) -> tuple[float | None, float | None]:
        """Attempt to collect marketcap and 24h volume for the base token of sym across the provided exchanges.

        Returns (marketcap_usd_or_None, volume24h_usd_or_None). If any metric cannot be determined
        across all exchanges, returns None for that metric.
        """
        base = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
        marketcap: float | None = None
        volume24h: float | None = None
        for ex in involved_exchanges:
            try:
                # Check currency details for marketcap-like fields
                if hasattr(ex, 'get_currency_details'):
                    try:
                        cd = ex.get_currency_details(base)
                    except Exception:
                        cd = None
                    if isinstance(cd, dict):
                        # look for marketcap fields in various common keys
                        for mk in ('marketCap', 'market_cap', 'marketCapUsd', 'market_cap_usd'):
                            v = cd.get(mk)
                            if v is not None:
                                try:
                                    mc = float(v)
                                    if marketcap is None or mc < marketcap:
                                        # prefer the smallest reported marketcap conservatively
                                        marketcap = mc
                                except Exception:
                                    pass
                        # some adapters embed volume in cd/info
                        info = cd.get('info') if isinstance(cd.get('info'), dict) else None
                        if isinstance(info, dict):
                            # try to find 24h volume in info
                            for vk in ('volume24h', 'volume_24h', 'quoteVolume', 'volume'):
                                vv = info.get(vk)
                                if vv is not None:
                                    try:
                                        vol = float(vv)
                                        if volume24h is None or vol > volume24h:
                                            volume24h = vol
                                    except Exception:
                                        pass
                # Try fetch_ticker on the underlying client for 24h volume
                client = getattr(ex, 'client', None)
                if client is not None and hasattr(client, 'fetch_ticker'):
                    try:
                        t = client.fetch_ticker(sym)
                        if isinstance(t, dict):
                            for vol_key in ('quoteVolume', 'baseVolume', 'volume', 'quoteVolume24h'):
                                if vol_key in t and t.get(vol_key) is not None:
                                    try:
                                        v = float(t.get(vol_key))
                                        # convert base-volume to USD using last price if needed
                                        if vol_key == 'baseVolume' and t.get('last'):
                                            try:
                                                last = float(t.get('last'))
                                                v_usd = v * last
                                            except Exception:
                                                v_usd = None
                                        else:
                                            v_usd = v
                                        if v_usd is not None:
                                            if volume24h is None or v_usd > volume24h:
                                                volume24h = v_usd
                                    except Exception:
                                        pass
                            # some tickers include market cap in info
                            info = t.get('info') if isinstance(t.get('info'), dict) else None
                            if isinstance(info, dict):
                                for mk in ('marketCap', 'market_cap'):
                                    if mk in info and info.get(mk) is not None:
                                        try:
                                            mc = float(info.get(mk))
                                            if marketcap is None or mc < marketcap:
                                                marketcap = mc
                                        except Exception:
                                            pass
                    except Exception:
                        pass
            except Exception:
                continue
        return marketcap, volume24h

    # Build a mapping from symbol -> list of involved exchange adapters (from candidates)
    sym_to_exs: dict[str, list[object]] = {}
    for entry in candidates:
        sym = entry[0]
        buy_obj = entry[1]
        sell_obj = entry[4]
        sym_to_exs.setdefault(sym, []).extend([buy_obj, sell_obj])

    # Filter candidates by market metrics optionally. This can be enabled by setting
    # ARB_STRICT_METRICS=1 in the environment. Default is off (to avoid excluding
    # candidates in test/mock environments where metrics are unavailable).
    strict_metrics = os.getenv('ARB_STRICT_METRICS', '0') == '1'
    filtered_candidates: list[tuple] = []
    excluded_count = 0
    for entry in candidates:
        sym = entry[0]
        exs_for_sym = sym_to_exs.get(sym, [])
        mc, vol24 = _collect_symbol_metrics(sym, exs_for_sym)
        # if not strict, keep candidate when metrics are missing
        if not strict_metrics:
            filtered_candidates.append(entry)
            continue
        # decide whether to apply strict filtering for this symbol based on involved exchanges size
        apply_strict_for_sym = any(ex_symbol_counts.get(id(ex), 0) > SYMBOLS_THRESHOLD for ex in exs_for_sym)
        if not apply_strict_for_sym:
            # don't apply strict filtering for small/mock exchanges
            filtered_candidates.append(entry)
            continue
        # strict mode here: require metrics and thresholds
        keep = True
        if mc is None or vol24 is None:
            keep = False
        else:
            if not (mc < 1_000_000_000 and vol24 >= 100_000):
                keep = False
        if not keep:
            excluded_count += 1
            continue
        filtered_candidates.append(entry)

    try:
        print(f'[scanner] filtered candidates by market metrics: kept {len(filtered_candidates)} / {len(candidates)} (excluded {excluded_count})')
    except Exception:
        pass

    # swap in filtered candidates for the orderbook phase
    candidates = filtered_candidates

    for idx, entry in enumerate(candidates):
        try:
            print(f"[scanner] processing candidate {idx+1}/{len(candidates)}: symbol={entry[0]} buy={getattr(entry[1], 'name', str(entry[1]))} sell={getattr(entry[4], 'name', str(entry[4]))}")
        except Exception:
            pass
        try:
            print(f"[scanner] processing candidate {idx+1}/{len(candidates)}: symbol={entry[0]} buy={getattr(entry[1], 'name', str(entry[1]))} sell={getattr(entry[4], 'name', str(entry[4]))}")
        except Exception:
            pass
        # candidates now include withdraw/deposit flags
        if len(entry) == 9:
            sym, buy_obj, buy_ex, buy_price, sell_obj, sell_ex, sell_price, buy_withdraw, sell_deposit = entry
        else:
            sym, buy_obj, buy_ex, buy_price, sell_obj, sell_ex, sell_price = entry
            buy_withdraw = True
            sell_deposit = True
        exec_buy_price = buy_price
        exec_sell_price = sell_price
        buy_ob = None
        def _try_order_book_for(obj, symbol: str):
            """Try several symbol variants when calling get_order_book to handle
            exchanges that use different symbol formats (e.g. BTC/USDT vs BTC-USDT).
            Returns the (orderbook, used_symbol) or (None, None) on failure.
            """
            if not hasattr(obj, 'get_order_book'):
                return None, None
            tried = []
            variants = [symbol]
            if '/' in symbol:
                variants.append(symbol.replace('/', '-'))
            if '-' in symbol:
                variants.append(symbol.replace('-', '/'))
            # try appending common quote tokens if missing
            if '/' not in symbol and '-' not in symbol:
                variants.extend([f'{symbol}/USDT', f'{symbol}-USDT', f'{symbol}/USD', f'{symbol}-USD'])
            # also try removing common suffixes
            if symbol.endswith('/USDT') or symbol.endswith('-USDT'):
                variants.append(symbol.replace('/USDT', '').replace('-USDT', ''))
            # keep unique order preserving
            seen = set()
            unique_variants = []
            for v in variants:
                if v not in seen:
                    seen.add(v)
                    unique_variants.append(v)

            for cand in unique_variants:
                try:
                    try:
                        print(f"      [scanner] trying orderbook candidate '{cand}' on {getattr(obj,'name',str(obj))}")
                    except Exception:
                        pass
                    # ask adapter for order book
                    ob = obj.get_order_book(cand)
                    if ob and isinstance(ob, dict) and (ob.get('asks') or ob.get('bids')):
                        try:
                            print(f"      [scanner] orderbook found using '{cand}' on {getattr(obj,'name',str(obj))}")
                        except Exception:
                            pass
                        return ob, cand
                except Exception as e:
                    try:
                        print(f"      [scanner] candidate '{cand}' failed: {e}")
                    except Exception:
                        pass
                    # continue trying other variants
                    continue
            return None, None

        if hasattr(buy_obj, "get_order_book"):
            try:
                ob, used = _try_order_book_for(buy_obj, sym)
                if ob is None:
                    asks = []
                else:
                    asks = ob.get("asks", [])
                vwap = vwap_price_from_orderbook(asks, amount)
                if vwap is None:
                    if allow_ticker_fallback:
                        exec_buy_price = buy_price
                    else:
                        continue
                else:
                    # liquidity filter: require some top-level size
                    if len(asks) == 0 or asks[0][1] < min_top_level_size:
                        if allow_ticker_fallback:
                            exec_buy_price = buy_price
                        else:
                            continue
                    else:
                        exec_buy_price = vwap
                        buy_ob = asks
            except Exception:
                exec_buy_price = buy_price
        sell_ob = None
        if hasattr(sell_obj, "get_order_book"):
            try:
                ob, used = _try_order_book_for(sell_obj, sym)
                if ob is None:
                    bids = []
                else:
                    bids = ob.get("bids", [])
                vwap = vwap_price_from_orderbook(bids, amount)
                if vwap is None:
                    if allow_ticker_fallback:
                        exec_sell_price = sell_price
                    else:
                        continue
                else:
                    if len(bids) == 0 or bids[0][1] < min_top_level_size:
                        if allow_ticker_fallback:
                            exec_sell_price = sell_price
                        else:
                            continue
                    else:
                        exec_sell_price = vwap
                        sell_ob = bids
            except Exception:
                exec_sell_price = sell_price

        # Before finalizing, consult adapters' get_currency_details if available
        # to set withdraw/deposit flags more authoritatively.
        base_token = sym.split('/')[0] if '/' in sym else (sym.split('-')[0] if '-' in sym else sym)
        try:
            if hasattr(buy_obj, 'get_currency_details'):
                cd = buy_obj.get_currency_details(base_token)
                if isinstance(cd, dict):
                    # Prefer explicit top-level 'withdraw' flag when present
                    if 'withdraw' in cd:
                        buy_withdraw = bool(cd.get('withdraw'))
                    # check networks entries for withdraw/deposit enables if available
                    if 'networks' in cd and isinstance(cd['networks'], dict):
                        # if any network enables withdraw, treat as withdrawable
                        nw = cd['networks']
                        any_withdraw = any(bool(v.get('withdrawEnable') or v.get('withdraw') or v.get('withdrawEnable', False)) for v in nw.values() if isinstance(v, dict))
                        if any_withdraw:
                            buy_withdraw = True
        except Exception:
            pass
        try:
            if hasattr(sell_obj, 'get_currency_details'):
                cd = sell_obj.get_currency_details(base_token)
                if isinstance(cd, dict):
                    if 'deposit' in cd:
                        sell_deposit = bool(cd.get('deposit'))
                    if 'networks' in cd and isinstance(cd['networks'], dict):
                        nw = cd['networks']
                        any_deposit = any(bool(v.get('depositEnable') or v.get('deposit') or v.get('depositEnable', False)) for v in nw.values() if isinstance(v, dict))
                        if any_deposit:
                            sell_deposit = True
        except Exception:
            pass

        # enforce per-side notional minimum using the actual orderbook if available
        def notional_available(side: list[tuple[float, float]], required_amount: float) -> float:
            # returns total notional available for up to required_amount base units
            remaining = required_amount
            tot = 0.0
            for p, s in side:
                take = min(s, remaining)
                tot += take * p
                remaining -= take
                if remaining <= 0:
                    break
            return tot if remaining <= 0 else 0.0

        if min_side_notional > 0.0:
            # both sides must have at least min_side_notional available at/executable for `amount`
            if buy_ob is None or sell_ob is None:
                # missing orderbook data -> consider not satisfying the liquidity requirement
                continue
            buy_not = notional_available(buy_ob, amount)
            sell_not = notional_available(sell_ob, amount)
            if buy_not < min_side_notional or sell_not < min_side_notional:
                continue

        buy_fee = getattr(buy_obj, "fee_rate", 0.0)
        sell_fee = getattr(sell_obj, "fee_rate", 0.0)
        effective_buy = exec_buy_price * (1.0 + buy_fee)
        effective_sell = exec_sell_price * (1.0 - sell_fee)
        transfer_cost = getattr(sell_obj, "withdraw_fee", transfer_cost_default)
        net_profit = effective_sell - effective_buy - transfer_cost
        if net_profit <= 0:
            continue
        profit_pct = net_profit / effective_buy * 100.0
        if profit_pct >= min_profit_pct:
            opportunities.append(
                Opportunity(
                    buy_exchange=buy_ex,
                    sell_exchange=sell_ex,
                    symbol=sym,
                    buy_price=effective_buy,
                    sell_price=effective_sell,
                    profit_pct=profit_pct,
                    buy_withdraw=buy_withdraw,
                    sell_deposit=sell_deposit,
                )
            )
    opportunities.sort(key=lambda o: o.profit_pct, reverse=True)
    return opportunities
