from __future__ import annotations

from typing import List, Dict, Any
import time
import os

from .scanner import Opportunity, find_executable_opportunities


def _estimate_depth_usd_from_orderbook(ob: dict | None) -> float | None:
    if not ob or not isinstance(ob, dict):
        return None
    try:
        asks = ob.get('asks', [])
        bids = ob.get('bids', [])
        top_ask = asks[0] if asks else None
        top_bid = bids[0] if bids else None
        total = 0.0
        if top_ask:
            total += float(top_ask[0]) * float(top_ask[1])
        if top_bid:
            total += float(top_bid[0]) * float(top_bid[1])
        return total if total > 0 else None
    except Exception:
        return None


def compute_dryrun_opportunities(exchanges: List[object], amount: float = 1.0, min_profit_pct: float = 0.1, min_price_diff_pct: float = 1.0) -> List[Dict[str, Any]]:
    """Run the existing executable opportunity scanner in dry-run mode and
    enrich results with additional presentation fields expected by the
    frontend (depth_usd, size_est, gas_est, deposit/withdraw flags).

    Returns a list of plain dicts suitable for JSON serialization and
    WebSocket broadcast.
    """
    now = time.time()
    opps = find_executable_opportunities(exchanges, amount, min_profit_pct, min_price_diff_pct=min_price_diff_pct)
    out: List[Dict[str, Any]] = []
    # helper: best-effort read of a price for `symbol` from an exchange adapter
    def _extract_price_from_ticker_obj(tk) -> float | None:
        try:
            if tk is None:
                return None
            if isinstance(tk, (int, float)):
                return float(tk)
            if isinstance(tk, dict):
                for k in ('last', 'price', 'close', 'mid'):
                    if k in tk and tk.get(k) is not None:
                        try:
                            return float(tk.get(k))
                        except Exception:
                            pass
                return None
            # object-like
            if hasattr(tk, 'last') and getattr(tk, 'last') is not None:
                try:
                    return float(getattr(tk, 'last'))
                except Exception:
                    pass
            if hasattr(tk, 'price') and getattr(tk, 'price') is not None:
                try:
                    return float(getattr(tk, 'price'))
                except Exception:
                    pass
            return None
        except Exception:
            return None

    def _get_price_from_exchange(ex, symbol: str) -> float | None:
        # try direct tickers mapping first
        try:
            if hasattr(ex, 'get_tickers'):
                try:
                    tk_map = ex.get_tickers() or {}
                except Exception:
                    tk_map = {}
                if isinstance(tk_map, dict):
                    # try several candidate symbol formats
                    candidates = [symbol, symbol.replace('/', '-'), symbol.replace('-', '/'), symbol.upper(), symbol.lower()]
                    for c in candidates:
                        if c in tk_map:
                            price = _extract_price_from_ticker_obj(tk_map.get(c))
                            if price is not None:
                                return price
                    # try fuzzy: iterate keys and compare base/token
                    for k, v in tk_map.items():
                        try:
                            if k and symbol and (k.replace('/', '').replace('-', '').upper() == symbol.replace('/', '').replace('-', '').upper()):
                                price = _extract_price_from_ticker_obj(v)
                                if price is not None:
                                    return price
                        except Exception:
                            continue
        except Exception:
            pass
        # fallback: if adapter has get_order_book, derive top-of-book price
        try:
            if hasattr(ex, 'get_order_book'):
                try:
                    ob = ex.get_order_book(symbol) or {}
                except Exception:
                    ob = None
                if isinstance(ob, dict):
                    asks = ob.get('asks', [])
                    bids = ob.get('bids', [])
                    # prefer mid price if both sides available
                    try:
                        if asks and bids:
                            a = float(asks[0][0])
                            b = float(bids[0][0])
                            return (a + b) / 2.0
                        if asks:
                            return float(asks[0][0])
                        if bids:
                            return float(bids[0][0])
                    except Exception:
                        pass
        except Exception:
            pass
        return None
    for o in opps:
        try:
            # attempt to inspect orderbook depth if available on adapters
            depth_usd = None
            size_est = 0
            gas_est = 0
            buy_currency_details = None
            sell_currency_details = None
            try:
                buy_obj = next((ex for ex in exchanges if getattr(ex, 'name', '') == o.buy_exchange), None)
                sell_obj = next((ex for ex in exchanges if getattr(ex, 'name', '') == o.sell_exchange), None)
                if buy_obj and hasattr(buy_obj, 'get_order_book'):
                    ob, _ = (buy_obj.get_order_book(o.symbol) or {}, None) if False else (None, None)
                # best-effort: try to call get_order_book safely
                if buy_obj and hasattr(buy_obj, 'get_order_book'):
                    try:
                        ob = buy_obj.get_order_book(o.symbol)
                        d = _estimate_depth_usd_from_orderbook(ob)
                        if d:
                            depth_usd = d
                    except Exception:
                        pass
                if sell_obj and hasattr(sell_obj, 'get_order_book') and depth_usd is None:
                    try:
                        ob = sell_obj.get_order_book(o.symbol)
                        d = _estimate_depth_usd_from_orderbook(ob)
                        if d:
                            depth_usd = d
                    except Exception:
                        pass
                # try to get currency metadata
                if buy_obj and hasattr(buy_obj, 'get_currency_details'):
                    try:
                        buy_currency_details = buy_obj.get_currency_details(o.symbol.split('/')[0])
                    except Exception:
                        buy_currency_details = None
                if sell_obj and hasattr(sell_obj, 'get_currency_details'):
                    try:
                        sell_currency_details = sell_obj.get_currency_details(o.symbol.split('/')[0])
                    except Exception:
                        sell_currency_details = None
            except Exception:
                pass

            out.append({
                'symbol': o.symbol,
                'buy_exchange': o.buy_exchange,
                'sell_exchange': o.sell_exchange,
                'buy_price': o.buy_price,
                'sell_price': o.sell_price,
                # Include explicit per-exchange prices for frontend convenience
                'price_binance': None,
                'price_kucoin': None,
                'price_mexc': None,
                # also include capitalized keys that some frontends may bind to
                'Binance': None,
                'Kucoin': None,
                'Mexc': None,
                'profit_pct': o.profit_pct,
                'orderbook_depth_usd': depth_usd,
                'depth_usd': depth_usd,
                'size_est': amount,
                'gas_est': gas_est,
                'buy_withdraw': getattr(o, 'buy_withdraw', True),
                'sell_deposit': getattr(o, 'sell_deposit', True),
                'buy_currency_details': buy_currency_details,
                'sell_currency_details': sell_currency_details,
                'ts': now,
            })
            # attempt to populate binance/kucoin prices from provided exchange adapters
            try:
                # find adapters by name (case-insensitive contains)
                for ex in exchanges:
                    try:
                        name = getattr(ex, 'name', '') or ''
                        lname = name.lower()
                        if 'binance' in lname and out[-1].get('price_binance') is None:
                            p = _get_price_from_exchange(ex, o.symbol)
                            if p is not None:
                                out[-1]['price_binance'] = p
                                out[-1]['Binance'] = p
                        if 'kucoin' in lname and out[-1].get('price_kucoin') is None:
                            p = _get_price_from_exchange(ex, o.symbol)
                            if p is not None:
                                out[-1]['price_kucoin'] = p
                                out[-1]['Kucoin'] = p
                        if 'mexc' in lname and out[-1].get('price_mexc') is None:
                            p = _get_price_from_exchange(ex, o.symbol)
                            if p is not None:
                                out[-1]['price_mexc'] = p
                                out[-1]['Mexc'] = p
                    except Exception:
                        continue
            except Exception:
                pass

            # If still missing, try registered ws feeders (binance/kucoin) as a last resort
            try:
                try:
                    from .exchanges.ws_feed_manager import get_feeder
                except Exception:
                    get_feeder = None
                if get_feeder is not None:
                    if out[-1].get('price_binance') is None:
                        try:
                            fb = get_feeder('binance')
                            if fb is not None:
                                p = _get_price_from_exchange(fb, o.symbol)
                                if p is not None:
                                    out[-1]['price_binance'] = p
                                    out[-1]['Binance'] = p
                        except Exception:
                            pass
                    if out[-1].get('price_kucoin') is None:
                        try:
                            fk = get_feeder('kucoin')
                            if fk is not None:
                                p = _get_price_from_exchange(fk, o.symbol)
                                if p is not None:
                                    out[-1]['price_kucoin'] = p
                                    out[-1]['Kucoin'] = p
                        except Exception:
                            pass
                    if out[-1].get('price_mexc') is None:
                        try:
                            fm = get_feeder('mexc')
                            if fm is not None:
                                p = _get_price_from_exchange(fm, o.symbol)
                                if p is not None:
                                    out[-1]['price_mexc'] = p
                                    out[-1]['Mexc'] = p
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            continue
    return out
