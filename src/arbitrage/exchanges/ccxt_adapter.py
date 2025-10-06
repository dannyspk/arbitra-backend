from __future__ import annotations

from typing import Dict, Any
import os
import time

from .base import Exchange, Ticker

try:
    import ccxt  # type: ignore
except Exception:  # pragma: no cover - runtime import
    ccxt = None


class CCXTExchange:
    """A thin CCXT-backed exchange adapter.

    Usage:
      ex = CCXTExchange('binance', api_key='KEY', secret='SECRET')
      tickers = ex.get_tickers()
      oid = ex.place_order('BTC/USDT', 'buy', 0.001)

    Notes:
    - This is minimal scaffolding. In production you should add rate-limit handling,
      retries, mapping between unified symbols and exchange symbols, and error handling.
    - ccxt must be installed (pip install ccxt).
    """

    def __init__(self, id: str, api_key: str | None = None, secret: str | None = None, options: Dict[str, Any] | None = None):
        if ccxt is None:
            raise ImportError("ccxt is required for CCXTExchange. Install with `pip install ccxt`")
        self.name = id
        exchange_cls = getattr(ccxt, id)
        cfg = {}
        if api_key:
            cfg['apiKey'] = api_key
        if secret:
            cfg['secret'] = secret
        if options:
            cfg.update(options)
        # instantiate ccxt exchange
        self.client = exchange_cls(cfg)
        # simple per-instance cache for currency metadata to avoid repeated
        # network calls; stores (timestamp, data)
        self._currency_cache: dict | None = None
        self._currency_cache_ts: float | None = None
        # default cache TTL in seconds (5 minutes)
        self._currency_cache_ttl = 300.0
        # simple per-instance cache for tickers to avoid refetching every loop;
        # stores (timestamp, data). TTL is configurable via ARB_CCXT_TICKER_TTL
        # (seconds). Default to 1.0s to allow frequent but rate-limited scanning
        # without hammering the exchange.
        self._tickers_cache: dict | None = None
        self._tickers_cache_ts: float | None = None
        try:
            self._tickers_cache_ttl = float(os.environ.get('ARB_CCXT_TICKER_TTL', '1.0'))
        except Exception:
            self._tickers_cache_ttl = 1.0

        # prefer built-in rate-limiting if available to avoid bans
        try:
            # many ccxt exchanges expose enableRateLimit
            setattr(self.client, 'enableRateLimit', True)
        except Exception:
            pass
        # ensure timeout lives on the client for later use (ms)
        try:
            timeout_val = cfg.get('timeout')
            if timeout_val is not None:
                # many ccxt clients use either .timeout or .options['timeout']
                try:
                    self.client.timeout = int(timeout_val)
                except Exception:
                    try:
                        self.client.options['timeout'] = int(timeout_val)
                    except Exception:
                        pass
        except Exception:
            pass

    def get_tickers(self) -> Dict[str, Ticker]:
        # If an external websocket feeder is registered for this exchange and
        # the feature is enabled via ARB_USE_WS_FEED, prefer the in-memory
        # snapshot to avoid blocking REST calls. Fall back to the cached
        # fetch_tickers behaviour if there's no feeder or it fails.
        use_ws_feed = os.environ.get('ARB_USE_WS_FEED', '').lower() in ('1', 'true', 'yes')
        use_ws_feed_strict = os.environ.get('ARB_WS_FEED_STRICT', '').lower() in ('1', 'true', 'yes')
        if use_ws_feed:
            try:
                # import lazily to avoid import-time cycles during tests
                try:
                    from .ws_feed_manager import get_feeder  # type: ignore
                except Exception:
                    # fallback to absolute import if package context differs
                    from arbitrage.exchanges.ws_feed_manager import get_feeder  # type: ignore
                feeder = get_feeder(self.name)
                if feeder is not None and hasattr(feeder, 'get_tickers'):
                    try:
                        data = feeder.get_tickers() or {}
                        out: Dict[str, Ticker] = {}
                        for symbol, info in data.items():
                            try:
                                # feeder may return {symbol: {'last': price, ...}}
                                if isinstance(info, dict):
                                    price = info.get('last') or info.get('price')
                                elif isinstance(info, (int, float)):
                                    price = float(info)
                                else:
                                    # unknown shape, try attribute access
                                    price = getattr(info, 'price', None)
                                if price is None:
                                    continue
                                out[symbol] = Ticker(symbol, float(price))
                            except Exception:
                                continue
                        # if feeder produced any tickers, return them as the fast path
                        if out:
                            return out
                        # strict feeder-only mode: if ARB_WS_FEED_STRICT is set,
                        # do not fall back to REST and return an empty dict.
                        if use_ws_feed_strict:
                            return {}
                    except Exception:
                        # swallow feeder errors; in strict mode we must not call REST
                        if use_ws_feed_strict:
                            return {}
                        # otherwise fall back to REST below
                        pass
            except Exception:
                # if any import/lookup fails, in strict mode behave as no-data
                if use_ws_feed_strict:
                    return {}
                pass

        # Use a short-lived cache to avoid repeated network calls when scanner
        # loops frequently. TTL controlled by ARB_CCXT_TICKER_TTL.
        import time as _time
        now = _time.time()
        try:
            if self._tickers_cache is not None and self._tickers_cache_ts is not None and (now - self._tickers_cache_ts) < self._tickers_cache_ttl:
                data = self._tickers_cache
            else:
                data = self.client.fetch_tickers()
                self._tickers_cache = data
                self._tickers_cache_ts = now
        except Exception:
            # on error, fall back to last-known cache if available
            data = self._tickers_cache or {}
        out: Dict[str, Ticker] = {}
        for symbol, info in data.items():
            try:
                price = info.get('last') if isinstance(info, dict) else None
                if price is None:
                    # some exchanges use 'close' etc; fall back to average of bid/ask
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

    def place_order(self, symbol: str, side: str, amount: float) -> str:
        """Place a market order. Returns an order id or the raw order if id not available."""
        # Note: symbol format must match exchange expectations (e.g., 'BTC/USDT')
        order = self.client.create_order(symbol, 'market', side, amount)
        # try common locations for id
        if isinstance(order, dict):
            return order.get('id') or order.get('info', {}).get('id') or str(order)
        return str(order)

    def _candidate_symbols(self, symbol: str) -> list[str]:
        """Produce candidate symbol formats to try against ccxt (e.g. 'BTC-USD' -> 'BTC/USD', 'BTC/USDT')."""
        cand = []
        s = symbol.strip()
        cand.append(s)
        if "-" in s:
            cand.append(s.replace("-", "/"))
        if "/" in s:
            # try common stablecoin alias USD -> USDT
            cand.append(s.replace("/USD", "/USDT"))
        # ensure unique
        seen = set()
        out = []
        for c in cand:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def supports_withdraw(self, base_symbol: str) -> bool:
        if ccxt is None:
            return True
        try:
            if hasattr(self.client, 'fetch_currencies'):
                now = time.time()
                cur = None
                if self._currency_cache is not None and self._currency_cache_ts is not None and (now - self._currency_cache_ts) < self._currency_cache_ttl:
                    cur = self._currency_cache
                else:
                    cur = self.client.fetch_currencies()
                    self._currency_cache = cur
                    self._currency_cache_ts = now
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
                if entry is None:
                    # entry missing: decide policy based on env var
                    # Default behavior: fail-open (assume withdraw allowed)
                    # Set ARB_FAIL_OPEN_WITHDRAW=0 to treat unknown as disabled (fail-closed)
                    try:
                        env = os.getenv('ARB_FAIL_OPEN_WITHDRAW', '1')
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
        if ccxt is None:
            return True
        try:
            if hasattr(self.client, 'fetch_currencies'):
                now = time.time()
                cur = None
                if self._currency_cache is not None and self._currency_cache_ts is not None and (now - self._currency_cache_ts) < self._currency_cache_ttl:
                    cur = self._currency_cache
                else:
                    cur = self.client.fetch_currencies()
                    self._currency_cache = cur
                    self._currency_cache_ts = now
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
                if entry is None:
                    try:
                        env = os.getenv('ARB_FAIL_OPEN_WITHDRAW', '1')
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
        """Return True if the currency entry explicitly allows the action (withdraw/deposit),
        False if it explicitly disallows it, or True if unknown (fail-open).

        action must be 'withdraw' or 'deposit'. We search common keys at the top-level,
        inside 'info', and inside per-network entries under 'networks' or 'channels'.
        If any explicit negative indicator is found, return False. If an explicit
        positive indicator is found, return True.
        """
        if not isinstance(entry, dict):
            return True
        act = action.lower()
        # common positive keys
        positive_keys = {act, f'{act}Enabled', f'can{act.capitalize()}', f'can_{act}'}
        negative_keys = {f'{act}Disabled', f'{act}_disabled', f'is_{act}_disabled', f'{act}Suspended', f'{act}DisabledReason'}

        # normalize lookup helper
        def get_from(d: dict, keys: set[str]):
            for k in keys:
                if k in d:
                    return d.get(k)
            return None

        # top-level checks
        v = get_from(entry, positive_keys)
        if v is not None:
            return bool(v)
        v = get_from(entry, negative_keys)
        if v is not None:
            # if explicit negative flag present and truthy, treat as disabled
            return not bool(v)

        # inspect nested 'info'
        info = entry.get('info') if isinstance(entry.get('info'), dict) else None
        if isinstance(info, dict):
            v = get_from(info, positive_keys)
            if v is not None:
                return bool(v)
            v = get_from(info, negative_keys)
            if v is not None:
                return not bool(v)

        # inspect per-network entries if available
        networks = entry.get('networks') if isinstance(entry.get('networks'), dict) else None
        if isinstance(networks, dict):
            # if any network explicitly disables the action, consider that network disabled
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

        # unknown -> fail-open
        return True

    def get_currency_details(self, base_symbol: str) -> dict | None:
        """Return the raw currency entry from fetch_currencies() if available,
        otherwise attempt to infer details from fetch_markets(). Returns None
        if nothing useful is found.
        """
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
            # fall through to markets-based inference
            pass

        # try to infer from markets
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
                # return a compact structure summarizing markets and any info
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

    def prewarm_currency_metadata(self, timeout_seconds: float = 2.0) -> None:
        """Attempt to fetch and cache currency metadata and markets to avoid
        repeated fetch_currencies() calls during scanning. This will populate
        self._currency_cache and _currency_cache_ts. The method is best-effort
        and will swallow exceptions; call it in a thread with a timeout if you
        want to avoid blocking the main thread on slow network calls.
        """
        try:
            now = time.time()
            # if cache is fresh, nothing to do
            if self._currency_cache is not None and self._currency_cache_ts is not None and (now - self._currency_cache_ts) < self._currency_cache_ttl:
                return
            # fetch currencies (may block)
            cur = None
            try:
                if hasattr(self.client, 'fetch_currencies'):
                    cur = self.client.fetch_currencies()
            except Exception:
                cur = None
            if cur:
                self._currency_cache = cur
                self._currency_cache_ts = time.time()
                return
            # fallback: try to fetch markets and set a synthetic cache entry
            try:
                markets = self.client.fetch_markets()
                # build a minimal currencies dict from markets
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
                if cdict:
                    self._currency_cache = cdict
                    self._currency_cache_ts = time.time()
            except Exception:
                pass
            # additionally, try to fetch tickers once to populate per-symbol 24h volumes
            try:
                tks = None
                if hasattr(self.client, 'fetch_tickers'):
                    try:
                        tks = self.client.fetch_tickers()
                    except Exception:
                        # some exchanges may not support bulk fetch or may be slow
                        tks = None
                if tks:
                    # store the tickers snapshot in the instance-level short cache
                    try:
                        self._tickers_cache = tks
                        self._tickers_cache_ts = time.time()
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        """Fetch order book for a given symbol and return {'asks': [(price,size)...], 'bids': [(price,size)...]}

        Tries a few candidate symbol formats to accommodate different exchange symbol styles.
        """
        if ccxt is None:
            raise ImportError("ccxt is required for get_order_book")
        candidates = self._candidate_symbols(symbol)
        last_exc = None
        for cand in candidates:
            try:
                # Some exchanges (e.g., KuCoin) require specific allowed limits
                # (20 or 100). Try the requested depth first; on a failure due to
                # limit argument, retry with 20, and finally try without limit.
                try:
                    ob = self.client.fetch_order_book(cand, limit=depth)
                except Exception as inner_e:
                    # inspect message for limit-related complaints
                    msg = str(inner_e).lower()
                    if 'limit' in msg or 'must be' in msg or 'limit argument' in msg or 'invalid limit' in msg:
                        # try a known-allowed value for kucoin-like exchanges
                        try:
                            ob = self.client.fetch_order_book(cand, limit=20)
                        except Exception:
                            # final attempt: try without limit argument
                            ob = self.client.fetch_order_book(cand)
                    else:
                        # re-raise the inner exception to be handled by outer except
                        raise
                asks = []
                bids = []
                for a in ob.get('asks', [])[:depth]:
                    # ccxt order book entries are [price, amount]
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
                # ensure ordering: asks ascending, bids descending
                asks = sorted(asks, key=lambda x: x[0])
                bids = sorted(bids, key=lambda x: x[0], reverse=True)
                return {'asks': asks, 'bids': bids}
            except Exception as e:
                last_exc = e
                continue
        # if all candidates failed, raise the last exception for caller
        if last_exc:
            raise last_exc
        return {'asks': [], 'bids': []}

    def supports_withdraw(self, base_symbol: str) -> bool:
        """Best-effort: check ccxt markets/currencies to see if withdrawals are supported for the base token.

        Returns True if we cannot determine an explicit restriction (fail-open)."""
        try:
            # some ccxt builds expose fetch_currencies or currencies
            if hasattr(self.client, 'fetch_currencies'):
                cur = self.client.fetch_currencies()
                # currencies map: token -> { 'info': ..., 'withdraw': bool? }
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
                if isinstance(entry, dict):
                    # some exchanges include 'withdraw' boolean in the currency entry
                    if 'withdraw' in entry:
                        return bool(entry.get('withdraw'))
                    # ccxt unified may include 'active' or 'info'
                    info = entry.get('info') if isinstance(entry.get('info'), dict) else entry
                    if isinstance(info, dict) and 'can_withdraw' in info:
                        return bool(info.get('can_withdraw'))
        except Exception:
            pass
        # Unknown -> assume withdraw supported (fail-open)
        return True

    def supports_deposit(self, base_symbol: str) -> bool:
        try:
            if hasattr(self.client, 'fetch_currencies'):
                cur = self.client.fetch_currencies()
                base = base_symbol.split('/')[0] if '/' in base_symbol else base_symbol
                entry = cur.get(base) or cur.get(base.upper()) or cur.get(base.lower())
                if isinstance(entry, dict):
                    if 'deposit' in entry:
                        return bool(entry.get('deposit'))
                    info = entry.get('info') if isinstance(entry.get('info'), dict) else entry
                    if isinstance(info, dict) and 'can_deposit' in info:
                        return bool(info.get('can_deposit'))
        except Exception:
            pass
        return True
