from __future__ import annotations

from typing import Dict, Any, Optional
import requests
import time
import os

from .base import Exchange, Ticker

try:
    import ccxt  # type: ignore
except Exception:  # pragma: no cover - runtime import
    ccxt = None


class MEXCExchange:
    """Adapter for MEXC exchange.

    Two modes:
      - Mock mode: pass `prices` dict to constructor for local testing.
      - Live mode: if ccxt is installed, instantiate via ccxt.mexc.

    This adapter provides `fee_rate` and `withdraw_fee` attributes to integrate
    with the scanner's effective-price math.
    """

    def __init__(self, prices: Optional[Dict[str, float]] = None, api_key: Optional[str] = None, secret: Optional[str] = None, **ccxt_opts: Any):
        self._mock = prices is not None
        self._prices = prices or {}
        self.name = "mexc"
        self.fee_rate = 0.001  # default taker fee 0.1%
        self.withdraw_fee = 0.0
        self.client = None
        # per-instance cache for currencies metadata
        self._currency_cache: dict | None = None
        self._currency_cache_ts: float | None = None
        self._currency_cache_ttl = 300.0

        if not self._mock:
            if ccxt is None:
                raise ImportError("ccxt is required for live MEXC mode")
            if not hasattr(ccxt, 'mexc'):
                # some ccxt builds may not include mexc; raise informative error
                raise ImportError("ccxt does not expose 'mexc' in this environment")
            exch_cls = getattr(ccxt, 'mexc')
            cfg: Dict[str, Any] = {}
            if api_key:
                cfg['apiKey'] = api_key
            if secret:
                cfg['secret'] = secret
            if ccxt_opts:
                cfg.update(ccxt_opts)
            self.client = exch_cls(cfg)

    def get_tickers(self) -> Dict[str, Ticker]:
        if self._mock:
            out: Dict[str, Ticker] = {}
            for s, p in self._prices.items():
                out[s] = Ticker(s, float(p))
            return out

        # If an external websocket feeder is registered for this exchange and
        # ARB_USE_WS_FEED is enabled, prefer the feeder snapshot to avoid
        # blocking fetch_tickers REST calls. Fall back to ccxt fetch_tickers on
        # any failure.
        use_ws_feed = os.environ.get('ARB_USE_WS_FEED', '').lower() in ('1', 'true', 'yes')
        use_ws_feed_strict = os.environ.get('ARB_WS_FEED_STRICT', '').lower() in ('1', 'true', 'yes')
        if use_ws_feed:
            try:
                try:
                    from .ws_feed_manager import get_feeder  # type: ignore
                except Exception:
                    from arbitrage.exchanges.ws_feed_manager import get_feeder  # type: ignore
                feeder = get_feeder(self.name)
                if feeder is not None and hasattr(feeder, 'get_tickers'):
                    try:
                        data = feeder.get_tickers() or {}
                        out: Dict[str, Ticker] = {}
                        for symbol, info in data.items():
                            try:
                                if isinstance(info, dict):
                                    price = info.get('last') or info.get('price')
                                elif isinstance(info, (int, float)):
                                    price = float(info)
                                else:
                                    price = getattr(info, 'price', None)
                                if price is None:
                                    continue
                                out[symbol] = Ticker(symbol, float(price))
                            except Exception:
                                continue
                        if out:
                            return out
                        # strict mode: if feeder returned nothing and strict flag is set,
                        # do not fall back to REST; return empty result to signal no data.
                        if use_ws_feed_strict:
                            return {}
                    except Exception:
                        if use_ws_feed_strict:
                            return {}
                        pass
            except Exception:
                if use_ws_feed_strict:
                    return {}
                pass

        # live mode via ccxt as fallback
        data = self.client.fetch_tickers()
        out: Dict[str, Ticker] = {}
        for symbol, info in data.items():
            try:
                price = info.get('last') if isinstance(info, dict) else None
                if price is None:
                    bid = info.get('bid')
                    ask = info.get('ask')
                    if bid and ask:
                        price = (bid + ask) / 2
                if price is None:
                    continue
                out[symbol] = Ticker(symbol, float(price))
            except Exception:
                continue
        return out

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        if self._mock:
            # create a synthetic orderbook around the price similar to MockExchange
            mid = float(self._prices.get(symbol, 0.0))
            if mid <= 0:
                return {'asks': [], 'bids': []}
            asks = []
            bids = []
            for i in range(1, depth + 1):
                step = 0.001 * i * mid * 0.001
                price_ask = mid + step
                price_bid = mid - step
                size = max(0.001, 1.0 / i)
                asks.append((price_ask, size))
                bids.append((price_bid, size))
            bids = sorted(bids, key=lambda x: x[0], reverse=True)
            return {'asks': asks, 'bids': bids}
        # live via ccxt
        candidates = [symbol, symbol.replace('-', '/'), symbol.replace('/USD', '/USDT')]
        last_exc = None
        for cand in candidates:
            try:
                ob = self.client.fetch_order_book(cand, limit=depth)
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
                last_exc = e
                continue
        if last_exc:
            raise last_exc
        return {'asks': [], 'bids': []}

    def place_order(self, symbol: str, side: str, amount: float) -> str:
        if self._mock:
            # simple mock order id
            return f"mexc-mock-{symbol}-{side}-{amount}"
        order = self.client.create_order(symbol, 'market', side, amount)
        if isinstance(order, dict):
            return order.get('id') or order.get('info', {}).get('id') or str(order)
        return str(order)

    def supports_withdraw(self, base_symbol: str) -> bool:
        if self._mock:
            # mock mode: assume withdraws are enabled
            return True
        try:
            if hasattr(self.client, 'fetch_currencies'):
                now = time.time()
                if self._currency_cache is not None and self._currency_cache_ts is not None and (now - self._currency_cache_ts) < self._currency_cache_ttl:
                    cur = self._currency_cache
                else:
                    cur = self.client.fetch_currencies()
                    self._currency_cache = cur
                    self._currency_cache_ts = now
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
                if entry is None:
                    # try markets inference
                    md = self.get_currency_details(base_symbol)
                    if md is not None and isinstance(md, dict) and md.get('markets'):
                        # markets present but no explicit currency flags -> fall back to policy
                        entry = None
                    else:
                        # if still no entry, try exchange-specific asset status
                        try:
                            asset = self._fetch_mexc_asset_status(base_symbol)
                            if asset is not None:
                                # asset dict may contain withdraw/deposit flags or per-network info
                                return self._currency_allows(asset, 'withdraw')
                        except Exception:
                            pass
                    try:
                        env = __import__('os').getenv('ARB_FAIL_OPEN_WITHDRAW', '1')
                        if env == '0':
                            return False
                    except Exception:
                        pass
                    return True
                return self._currency_allows(entry, 'withdraw')
        except Exception:
            pass
        return True

    def supports_deposit(self, base_symbol: str) -> bool:
        if self._mock:
            return True
        try:
            if hasattr(self.client, 'fetch_currencies'):
                now = time.time()
                if self._currency_cache is not None and self._currency_cache_ts is not None and (now - self._currency_cache_ts) < self._currency_cache_ttl:
                    cur = self._currency_cache
                else:
                    cur = self.client.fetch_currencies()
                    self._currency_cache = cur
                    self._currency_cache_ts = now
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
                if entry is None:
                    md = self.get_currency_details(base_symbol)
                    if md is not None and isinstance(md, dict) and md.get('markets'):
                        entry = None
                    else:
                        try:
                            asset = self._fetch_mexc_asset_status(base_symbol)
                            if asset is not None:
                                return self._currency_allows(asset, 'deposit')
                        except Exception:
                            pass
                    try:
                        env = __import__('os').getenv('ARB_FAIL_OPEN_WITHDRAW', '1')
                        if env == '0':
                            return False
                    except Exception:
                        pass
                    return True
                return self._currency_allows(entry, 'deposit')
        except Exception:
            pass
        return True

    def _currency_allows(self, entry: object, action: str) -> bool:
        if not isinstance(entry, dict):
            return True
        act = action.lower()
        positive_keys = {act, f'{act}Enabled', f'can{act.capitalize()}', f'can_{act}'}
        negative_keys = {f'{act}Disabled', f'{act}_disabled', f'is_{act}_disabled', f'{act}Suspended'}

        def get_from(d: dict, keys: set[str]):
            for k in keys:
                if k in d:
                    return d.get(k)
            return None

        v = get_from(entry, positive_keys)
        if v is not None:
            return bool(v)
        v = get_from(entry, negative_keys)
        if v is not None:
            return not bool(v)

        info = entry.get('info') if isinstance(entry.get('info'), dict) else None
        if isinstance(info, dict):
            v = get_from(info, positive_keys)
            if v is not None:
                return bool(v)
            v = get_from(info, negative_keys)
            if v is not None:
                return not bool(v)

        networks = entry.get('networks') if isinstance(entry.get('networks'), dict) else None
        if isinstance(networks, dict):
            any_positive = False
            any_negative = False
            for net, netinfo in networks.items():
                if not isinstance(netinfo, dict):
                    continue
                v = get_from(netinfo, positive_keys)
                if v is not None and bool(v):
                    any_positive = True
                v = get_from(netinfo, negative_keys)
                if v is not None and bool(v):
                    any_negative = True
            if any_negative and not any_positive:
                return False
            if any_positive and not any_negative:
                return True

        return True

    def get_currency_details(self, base_symbol: str) -> dict | None:
        if ccxt is None:
            return None
        try:
            now = time.time()
            if self._currency_cache is not None and self._currency_cache_ts is not None and (now - self._currency_cache_ts) < self._currency_cache_ttl:
                cur = self._currency_cache
            else:
                cur = self.client.fetch_currencies()
                self._currency_cache = cur
                self._currency_cache_ts = now
            base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
            entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
            if isinstance(entry, dict):
                return entry
        except Exception:
            pass

        try:
            markets = self.client.fetch_markets()
            found = []
            for m in markets:
                try:
                    base = m.get('base') or m.get('baseId') or (m.get('symbol') or '').split('/')[0]
                    if base and base_symbol.upper() == str(base).upper():
                        found.append(m)
                except Exception:
                    continue
            if found:
                summarized = []
                for m in found:
                    try:
                        summarized.append({
                            'symbol': m.get('symbol'),
                            'active': m.get('active', True),
                            'info': {k: m.get('info', {}).get(k) if isinstance(m.get('info'), dict) else None for k in ('status', 'state', 'withdraw', 'deposit')},
                        })
                    except Exception:
                        summarized.append({'symbol': m.get('symbol')})
                return {'markets': summarized}
        except Exception:
            pass
        return None

    def _fetch_mexc_asset_status(self, base_symbol: str) -> dict | None:
        """Try to call exchange-specific public endpoints (if present on the ccxt client)
        to retrieve authoritative asset/currency status. This method attempts a small
        list of likely ccxt-generated method names and returns the first successful
        parsed result. Returns None if none found.

        Note: we intentionally try multiple method names defensively because ccxt
        exposes different raw endpoints depending on the exchange version.
        """
        if self._mock or ccxt is None or self.client is None:
            return None

        code = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
        candidates = [
            'public_get_currencies', 'publicGetCurrencies', 'public_get_assets', 'publicGetAssets',
            'public_get_currency', 'publicGetCurrency', 'private_get_asset', 'privateGetAsset',
        ]

        for name in candidates:
            fn = getattr(self.client, name, None)
            if not callable(fn):
                continue
            try:
                # some methods expect params, some don't; try both
                try:
                    res = fn({'currency': code})
                except TypeError:
                    res = fn()
                # normalize result shape
                if isinstance(res, dict):
                    # if dictionary keyed by currency codes, try to pick code
                    if code in res:
                        return res.get(code)
                    # try uppercase/lower
                    if code.upper() in res:
                        return res.get(code.upper())
                    if code.lower() in res:
                        return res.get(code.lower())
                    # otherwise return the raw dict for caller inspection
                    return res
                # if list, try to find matching entry
                if isinstance(res, list):
                    for item in res:
                        try:
                            if not isinstance(item, dict):
                                continue
                            if item.get('code') == code or item.get('id') == code or item.get('currency') == code:
                                return item
                        except Exception:
                            continue
                    # otherwise return the list under a key for caller
                    return {'items': res}
            except Exception:
                continue
        # If ccxt raw method probes didn't return useful data, try MEXC's public wallet endpoint
        try:
            # Only attempt the public wallet endpoint if explicitly allowed via env var
            # to avoid accidental scraping or blocked requests.
            allow = __import__('os').getenv('ARB_MEXC_ALLOW_PUBLIC_WALLET', '0')
            if allow != '1':
                return None
            url = 'https://www.mexc.com/api/v3/capital/config/getall'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.mexc.com/',
                'Origin': 'https://www.mexc.com',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            r = requests.get(url, headers=headers, timeout=10.0)
            if r.status_code == 200:
                j = r.json()
                # response often contains a 'data' list of currency entries
                data = j.get('data') if isinstance(j, dict) else None
                if isinstance(data, list):
                    for item in data:
                        try:
                            # keys vary: try matching common ones
                            if not isinstance(item, dict):
                                continue
                            cur = str(item.get('currency') or item.get('coin') or item.get('id') or '').upper()
                            if cur == code.upper():
                                return item
                        except Exception:
                            continue
        except Exception:
            pass

        return None
