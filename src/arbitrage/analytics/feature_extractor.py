from __future__ import annotations

import time
import math
from collections import deque, defaultdict
from typing import Dict, Any, Iterable, List, Optional

from arbitrage.exchanges.ws_feed_manager import get_feeder

def _summarize(payload: dict) -> dict:
    try:
        # keep small summary to avoid storing huge payloads
        keys = list(payload.keys()) if isinstance(payload, dict) else []
        return {'keys': keys[:5], 'len': len(str(payload))}
    except Exception:
        return {'keys': [], 'len': 0}


class FeatureExtractor:
    """Extract lightweight latency-friendly features from registered feeders.

    Features computed per-symbol (BASE/QUOTE form) across exchanges:
      - orderbook_notional: sum(topN price*qty) for top N levels (default N=5)
      - spread: (ask_top - bid_top) / mid
    Also keeps simple trade/quote volume history for z-score over short windows.

    Usage:
      fe = FeatureExtractor(['binance','kucoin','mexc'])
      while True:
          feats = fe.poll_once()
          # feats is dict: symbol -> {exchange: {features...}, combined: {...}}
          time.sleep(1.0)
    """

    def __init__(self, exchanges: Optional[List[str]] = None, top_n: int = 5, window_seconds: int = 60):
        self.exchanges = [e.lower() for e in (exchanges or ['binance', 'kucoin', 'mexc'])]
        self.top_n = int(top_n)
        self.window = int(window_seconds)

        # history buffers: symbol -> deque of (ts, quote_volume)
        self._vol_history: Dict[str, deque] = defaultdict(lambda: deque())
        # last computed values cache
        self._last: Dict[str, Any] = {}
        # alert rules: list of (name, callable(feature_dict) -> bool)
        # stored as tuples (name, fn, dedupe_seconds)
        self.alert_rules: List[tuple[str, Any, int]] = []
        # CSV logging path (append mode)
        self.csv_path: Optional[str] = None
        # dedupe tracker: (rule_name, symbol) -> last_alert_ts
        self._last_alert_ts: Dict[tuple[str, str], float] = {}

        # previous top notional per symbol/exchange to estimate orderflow
        self._prev_notional: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(dict)
        # ewma prices per symbol/exchange
        self._ewma: Dict[str, Dict[str, float]] = defaultdict(dict)
        # previous ewma to compute ewma returns
        self._prev_ewma: Dict[str, Dict[str, float]] = defaultdict(dict)
        # default EWMA half-life seconds
        self.ewma_halflife = 60.0
    # optional webhook URL to POST alerts to
    self.webhook_url: Optional[str] = None

    # --- utility helpers
    def _now(self) -> float:
        return time.time()

    def _sum_top_notional(self, ob: dict) -> float:
        if not ob:
            return 0.0
        asks = ob.get('asks', [])[: self.top_n]
        bids = ob.get('bids', [])[: self.top_n]
        s = 0.0
        for p, q in (asks + bids):
            try:
                s += float(p) * float(q)
            except Exception:
                continue
        return s

    def _sum_side_notional(self, ob: dict, side: str) -> float:
        if not ob:
            return 0.0
        arr = ob.get(side, [])[: self.top_n]
        s = 0.0
        for p, q in arr:
            try:
                s += float(p) * float(q)
            except Exception:
                continue
        return s

    def _update_ewma(self, sym: str, ex: str, price: float) -> Optional[float]:
        # compute alpha from half-life
        try:
            halflife = max(1.0, float(self.ewma_halflife))
            alpha = 1 - math.exp(math.log(0.5) / halflife)
            prev = self._ewma.get(sym, {}).get(ex)
            if prev is None:
                self._ewma.setdefault(sym, {})[ex] = float(price)
                return None
            else:
                new = alpha * float(price) + (1 - alpha) * prev
                # store previous before updating
                self._prev_ewma.setdefault(sym, {})[ex] = prev
                self._ewma.setdefault(sym, {})[ex] = new
                try:
                    if prev and prev != 0:
                        return (new / prev) - 1.0
                except Exception:
                    return None
        except Exception:
            return None

    def _top_prices_and_spread(self, ob: dict) -> Optional[Dict[str, float]]:
        asks = ob.get('asks', [])
        bids = ob.get('bids', [])
        if not asks or not bids:
            return None
        try:
            ask = float(asks[0][0])
            bid = float(bids[0][0])
            mid = (ask + bid) / 2.0 if (ask + bid) != 0 else None
            spread = (ask - bid) / mid if mid and mid != 0 else None
            return {'ask': ask, 'bid': bid, 'mid': mid, 'spread': spread}
        except Exception:
            return None

    # --- main polling
    def poll_once(self) -> Dict[str, Any]:
        """Poll feeders once and return computed features.

        Returns dict keyed by symbol (BASE/QUOTE) with per-exchange features and a combined summary.
        """
        now = self._now()
        per_symbol: Dict[str, Dict[str, Any]] = defaultdict(dict)

        for ex in self.exchanges:
            feeder = get_feeder(ex)
            if not feeder:
                continue

            # try feeder.get_tickers() first (many feeders provide BASE/QUOTE keys)
            tickers = None
            try:
                tickers = feeder.get_tickers() if hasattr(feeder, 'get_tickers') else None
            except Exception:
                tickers = None

            # iterate symbols discovered via tickers or via configured hub
            symbols = []
            if isinstance(tickers, dict) and tickers:
                symbols = list(tickers.keys())
            else:
                # fallback to common hotcoins (small set) by probing feeder books
                # Attempt to peek keys from feeder._books if present (best-effort)
                try:
                    books = getattr(feeder, '_books', {})
                    symbols = []
                    for k in list(books.keys())[:200]:
                        # convert normalized key 'BTCUSDT' -> 'BTC/USDT'
                        s = k
                        # naive split on common quotes
                        for q in ('USDT','USDC','BUSD','BTC','ETH'):
                            if s.endswith(q) and len(s) > len(q):
                                symbols.append(f"{s[:-len(q)]}/{q}")
                                break
                except Exception:
                    symbols = []

            for sym in symbols:
                try:
                    # ask feeder for order book; accept multiple symbol formats
                    ob = None
                    try:
                        ob = feeder.get_order_book(sym, depth=self.top_n) if hasattr(feeder, 'get_order_book') else None
                    except Exception:
                        # try alternative key formats
                        try:
                            ob = feeder.get_order_book(sym.replace('/', '').replace('-', ''), depth=self.top_n)
                        except Exception:
                            ob = None

                    if not ob:
                        continue

                    # compute features
                    notional = self._sum_top_notional(ob)
                    tp = self._top_prices_and_spread(ob)
                    asks_not = self._sum_side_notional(ob, 'asks')
                    bids_not = self._sum_side_notional(ob, 'bids')

                    ex_map = per_symbol[sym].setdefault('by_exchange', {})
                    ex_map[ex] = {
                        'orderbook_notional': notional,
                        'asks_notional': asks_not,
                        'bids_notional': bids_not,
                        'spread': tp.get('spread') if tp else None,
                        'ask': tp.get('ask') if tp else None,
                        'bid': tp.get('bid') if tp else None,
                    }

                    # estimate orderflow: compare with previous notional snapshot
                    prev_map = self._prev_notional.get(sym, {}).get(ex)
                    of_imb = None
                    try:
                        if prev_map:
                            delta_bids = bids_not - (prev_map.get('bids_notional') or 0.0)
                            delta_asks = asks_not - (prev_map.get('asks_notional') or 0.0)
                            denom = (abs(delta_bids) + abs(delta_asks)) or 1.0
                            of_imb = (delta_bids - delta_asks) / denom
                    except Exception:
                        of_imb = None
                    # store current notional for next poll
                    self._prev_notional.setdefault(sym, {})[ex] = {'bids_notional': bids_not, 'asks_notional': asks_not}

                    # update EWMA price / return
                    ewma_ret = None
                    try:
                        last_price = None
                        if tp:
                            # prefer mid
                            last_price = tp.get('mid') or tp.get('ask') or tp.get('bid')
                        # fallback to tickers
                        if last_price is None and isinstance(tickers, dict):
                            tk = tickers.get(sym) or tickers.get(sym.replace('/', '').replace('-', ''))
                            if isinstance(tk, dict):
                                last_price = float(tk.get('last') or tk.get('price') or 0.0)
                        if last_price:
                            ewma_ret = self._update_ewma(sym, ex, last_price)
                    except Exception:
                        ewma_ret = None

                    # attach orderflow and ewma into exchange map
                    ex_map[ex]['orderflow_imbalance'] = of_imb
                    ex_map[ex]['ewma_return'] = ewma_ret

                    # update short-term quote volume history if ticker data present
                    qv = None
                    try:
                        if isinstance(tickers, dict):
                            tk = tickers.get(sym) or tickers.get(sym.replace('/', '').replace('-', ''))
                            if isinstance(tk, dict):
                                qv = float(tk.get('quoteVolume') or tk.get('volume') or 0.0)
                    except Exception:
                        qv = None

                    if qv is not None:
                        h = self._vol_history[sym]
                        h.append((now, qv))
                        # evict old
                        while h and (now - h[0][0]) > self.window:
                            h.popleft()

                except Exception:
                    continue

        # compute aggregated signals and z-scores
        out: Dict[str, Any] = {}
        for sym, info in per_symbol.items():
            try:
                by_ex = info.get('by_exchange', {})
                # build notional map
                not_map = {ex: (by_ex.get(ex, {}).get('orderbook_notional') or 0.0) for ex in by_ex.keys()}
                # compute ratio between max and median (robust) as a simple imbalance signal
                vals = sorted([v for v in not_map.values() if v is not None])
                imbalance = None
                if vals:
                    mx = vals[-1]
                    med = vals[len(vals)//2] if len(vals) > 1 else vals[0]
                    try:
                        imbalance = mx / (med if med and med > 0 else 1.0)
                    except Exception:
                        imbalance = None

                # spread ratios
                spread_map = {ex: by_ex.get(ex, {}).get('spread') for ex in by_ex.keys()}

                # compute volume z-score over window
                h = self._vol_history.get(sym) or deque()
                vol_z = None
                try:
                    if h and len(h) >= 3:
                        vals = [v for _, v in h]
                        mean = sum(vals) / len(vals)
                        sd = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals)) if len(vals) > 1 else 0.0
                        recent = vals[-1]
                        vol_z = (recent - mean) / sd if sd and sd > 0 else None
                except Exception:
                    vol_z = None

                # orderflow imbalance aggregated across exchanges (max abs)
                of_map = {ex: by_ex.get(ex, {}).get('orderflow_imbalance') for ex in by_ex.keys()}
                ewma_map = {ex: by_ex.get(ex, {}).get('ewma_return') for ex in by_ex.keys()}

                out[sym] = {
                    'by_exchange': by_ex,
                    'imbalance': imbalance,
                    'spread_map': spread_map,
                    'volume_zscore': vol_z,
                    'orderflow_map': of_map,
                    'ewma_map': ewma_map,
                }
            except Exception:
                continue

        self._last = out
        # optionally log rows to CSV
        if self.csv_path:
            try:
                self._append_csv_rows(out)
            except Exception:
                pass

        # optionally evaluate alert rules
        alerts = self.evaluate_alerts(out)
        if alerts:
            # attach last alerts for external inspection
            out['_alerts'] = alerts
            # create a local alert log entry so the server notifier and UI can
            # surface alerts even when no external webhook is configured.
            try:
                import sys
                from datetime import datetime as _dt
                mod = sys.modules.get('arbitrage.web')
                if mod is not None and hasattr(mod, 'server_logs'):
                    try:
                        mod.server_logs.append({
                            'ts': _dt.utcnow().isoformat(),
                            'level': 'warning',
                            'src': 'feature_extractor',
                            'text': f'alerts: {len(alerts)} items',
                            'alerts': alerts,
                        })
                    except Exception:
                        pass
            except Exception:
                pass

            # send webhook(s) if configured
            try:
                if self.webhook_url:
                    # send one POST with all alerts
                    self._post_webhook({'alerts': alerts, 'ts': int(time.time())})
            except Exception:
                pass

        return out

    # --- CSV logging
    def set_csv(self, path: Optional[str]):
        """Enable CSV append logging to `path`. Pass None to disable."""
        self.csv_path = path

    def _append_csv_rows(self, out: Dict[str, Any]):
        import csv
        now = int(time.time())
        # ensure header
        first = not __import__('os').path.exists(self.csv_path)
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            if first:
                writer.writerow(['ts', 'symbol', 'imbalance', 'volume_zscore', 'by_exchange'])
            for sym, info in out.items():
                if sym == '_alerts':
                    continue
                try:
                    imbalance = info.get('imbalance')
                    volz = info.get('volume_zscore')
                    byex = info.get('by_exchange')
                    writer.writerow([now, sym, imbalance, volz, repr(byex)])
                except Exception:
                    continue

    # --- alerting
    def add_rule(self, name: str, fn) -> None:
        """Add an alert rule. fn takes (symbol, info) and returns truthy if alert.

        Optional: pass dedupe_seconds as attribute on fn (fn.dedupe_seconds) or
        supply via second tuple item; default dedupe is 300s.
        """
        dedupe = getattr(fn, 'dedupe_seconds', 300)
        self.alert_rules.append((name, fn, int(dedupe)))

    def evaluate_alerts(self, features: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        for sym, info in features.items():
            if sym == '_alerts':
                continue
            for name, fn, dedupe_seconds in self.alert_rules:
                try:
                    if not fn(sym, info):
                        continue
                    key = (name, sym)
                    now = time.time()
                    last_ts = self._last_alert_ts.get(key)
                    if last_ts and (now - last_ts) < dedupe_seconds:
                        # suppressed due to dedupe
                        continue
                    # record alert
                    self._last_alert_ts[key] = now
                    alerts.append({'rule': name, 'symbol': sym, 'info': info})
                except Exception:
                    continue
        return alerts

    # --- snapshot dump
    def dump_snapshots(self, out_dir: str) -> Optional[str]:
        """Dump current registered feeder snapshots into timestamped JSON in out_dir.

        Returns path written or None.
        """
        import os, json
        os.makedirs(out_dir, exist_ok=True)
        ts = int(time.time())
        path = os.path.join(out_dir, f'snap_{ts}.json')
        data = {}
        for ex in self.exchanges:
            feeder = get_feeder(ex)
            if not feeder:
                continue
            try:
                # attempt to read feeder._books or use get_order_book for known symbols
                books = getattr(feeder, '_books', None)
                if isinstance(books, dict) and books:
                    data[ex] = books
                    continue
                # else try to build from tickers/list of symbols
                data[ex] = {}
                tickers = feeder.get_tickers() if hasattr(feeder, 'get_tickers') else {}
                for s in (tickers or {}).keys():
                    try:
                        ob = feeder.get_order_book(s, depth=self.top_n) if hasattr(feeder, 'get_order_book') else None
                        data[ex][s] = ob
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh)
            return path
        except Exception:
            return None

    def _post_webhook(self, payload: dict) -> bool:
        """Post JSON payload to configured webhook URL. Returns True on success."""
        if not self.webhook_url:
            return False
        try:
            import urllib.request as _urlreq
            import json, time
            data = json.dumps(payload).encode('utf-8')
            req = _urlreq.Request(self.webhook_url, data=data, headers={'Content-Type': 'application/json'})
            with _urlreq.urlopen(req, timeout=5) as resp:
                ok = resp.status == 200 or resp.status == 201
                # Do not persist delivery history - this runtime only posts to the configured URL
                return ok
        except Exception:
            try:
                import time
            except Exception:
                pass
            return False

    # --- backtest helper: compute features from snapshot dict
    def compute_from_snapshots(self, snapshots: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Compute features from a snapshots map: exchange -> symbol -> orderbook dict.

        Expected orderbook format: {'asks': [[price,qty],...], 'bids': [[price,qty],...]}
        Returns same structure as poll_once output.
        """
        per_symbol: Dict[str, Dict[str, Any]] = defaultdict(dict)
        now = self._now()

        for ex, sym_map in (snapshots or {}).items():
            ex = ex.lower()
            for sym, ob in (sym_map or {}).items():
                try:
                    # normalize symbol to BASE/QUOTE if needed
                    s = sym
                    if isinstance(sym, str) and ('/' not in sym and '-' not in sym):
                        # attempt naive split
                        for q in ('USDT','USDC','BUSD','BTC','ETH'):
                            if s.endswith(q) and len(s) > len(q):
                                s = f"{s[:-len(q)]}/{q}"
                                break

                    notional = self._sum_top_notional(ob)
                    tp = self._top_prices_and_spread(ob) or {}
                    ex_map = per_symbol[s].setdefault('by_exchange', {})
                    ex_map[ex] = {'orderbook_notional': notional, 'spread': tp.get('spread'), 'ask': tp.get('ask'), 'bid': tp.get('bid')}
                except Exception:
                    continue

        # compute aggregated signals and return
        out: Dict[str, Any] = {}
        for sym, info in per_symbol.items():
            try:
                by_ex = info.get('by_exchange', {})
                not_map = {ex: (by_ex.get(ex, {}).get('orderbook_notional') or 0.0) for ex in by_ex.keys()}
                vals = sorted([v for v in not_map.values() if v is not None])
                imbalance = None
                if vals:
                    mx = vals[-1]
                    med = vals[len(vals)//2] if len(vals) > 1 else vals[0]
                    imbalance = mx / (med if med and med > 0 else 1.0)
                spread_map = {ex: by_ex.get(ex, {}).get('spread') for ex in by_ex.keys()}
                out[sym] = {'by_exchange': by_ex, 'imbalance': imbalance, 'spread_map': spread_map, 'volume_zscore': None}
            except Exception:
                continue

        return out


__all__ = ['FeatureExtractor']
