from __future__ import annotations

import json
import os
import time
import uuid
from typing import List, Dict, Optional

from .executor import DryRunExecutor, Executor
from .exchanges.mock_exchange import MockExchange

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


class StrategyExecutor:
    """Simple orchestrator to execute signals produced by the verbose runner.

    Modes:
      - dry: use DryRunExecutor to simulate accounting
      - paper: use MockExchange to simulate exchange fills and log orders
    """

    def __init__(self, mode: str = 'dry', mock_prices: Optional[Dict[str, float]] = None, fee_rate: float = 0.0007):
        self.mode = mode
        self.mock_prices = mock_prices or {}
        self.fee_rate = fee_rate
        # dry executor for backtest-like accounting
        self.dry = DryRunExecutor(fee_rate=self.fee_rate, slippage_bps=0.0005)
        # mock exchange for paper trading
        self.mock = MockExchange('mock', self.mock_prices, fee_rate=self.fee_rate)

    def _load_signals(self, csv_path: str) -> List[Dict]:
        import pandas as _pd
        df = _pd.read_csv(csv_path)
        # ensure expected columns exist
        out = []
        for _, r in df.iterrows():
            raw_act = r.get('action')
            if _pd.isna(raw_act):
                action = None
            else:
                action = str(raw_act).strip()
            out.append({
                'timestamp': r.get('timestamp'),
                'action': action,
                'long_signal': bool(r.get('long_signal')) if 'long_signal' in r else False,
                'short_quick': bool(r.get('short_quick')) if 'short_quick' in r else False,
                'pos_side': None if (not 'pos_side' in r or _pd.isna(r.get('pos_side'))) else r.get('pos_side'),
                'pos_size': float(r.get('pos_size')) if 'pos_size' in r and not _pd.isna(r.get('pos_size')) else None,
                'close': float(r.get('close')) if 'close' in r and not _pd.isna(r.get('close')) else None,
            })
        return out

    def run_from_signals_file(self, csv_path: str, run_id: Optional[str] = None, execute: bool = False) -> Dict:
        """Run signals from a CSV and return an execution trace.

        If execute is False, operate in dry mode and return accounting. If execute is True and mode=='paper', use MockExchange.
        """
        if run_id is None:
            run_id = uuid.uuid4().hex
        signals = self._load_signals(csv_path)
        trace = {'run_id': run_id, 'mode': self.mode if execute else 'dry', 'start_time': time.time(), 'events': []}

        # derive a symbol from the csv filename when possible (e.g., var/alpineusdt_15m.csv)
        sym = os.path.basename(csv_path).lower()
        if sym.endswith('_15m.csv'):
            sym = sym[:-len('_15m.csv')].upper()
        else:
            sym = sym.split('.')[0].upper()

        def _make_serializable(o):
            # recursively convert dataclasses/objects to dicts where possible
            import collections
            if o is None:
                return None
            if isinstance(o, (str, int, float, bool)):
                return o
            if isinstance(o, dict):
                return {k: _make_serializable(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_make_serializable(v) for v in o]
            # dataclass-like objects: try vars()
            try:
                d = vars(o)
                return {k: _make_serializable(v) for k, v in d.items()}
            except Exception:
                # fallback to string representation
                try:
                    return str(o)
                except Exception:
                    return None

        for s in signals:
            action = s.get('action')
            price = s.get('close')
            if not action:
                continue
            # map action strings to DryRunExecutor actions
            if action.startswith('open_'):
                side = 'long' if 'long' in action else 'short'
                # determine size: prefer pos_size from signal else use dry executor default via amount
                size = s.get('pos_size')
                if not execute:
                    # use DryRunExecutor enter
                    decision = {'action': 'enter', 'direction': side, 'size': size or 0}
                    res = self.dry.step(s.get('timestamp'), price, decision)
                    trace['events'].append({'type': 'enter', 'side': side, 'price': price, 'res': _make_serializable(res)})
                else:
                    # paper mode: place on mock exchange and simulate fills from order book
                    oid = self.mock.place_order(sym, 'buy' if side == 'long' else 'sell', size or 0)
                    notional = (size or 0) * (price or 0)
                    trace['events'].append({'type': 'place', 'oid': oid, 'side': side, 'price': price, 'size': size, 'notional': notional})
                    # simulate fills using order book; produce immediate simulated fill events
                    fills, remainder = self._simulate_fills(sym, side, size or 0, price)
                    for f in fills:
                        fee = f['qty'] * f['price'] * self.fee_rate
                        trace['events'].append({'type': 'fill', 'oid': oid, 'side': side, 'qty': f['qty'], 'price': f['price'], 'fee': fee, 'ts': f['ts']})
                    if remainder > 0:
                        # simulate timeout/cancel after waiting window
                        trace['events'].append({'type': 'partial_unfilled', 'oid': oid, 'remaining_qty': remainder})

            elif action.startswith('close_') or action == '':
                # close current position
                if not execute:
                    decision = {'action': 'exit'}
                    res = self.dry.step(s.get('timestamp'), price, decision)
                    trace['events'].append({'type': 'exit', 'price': price, 'res': _make_serializable(res)})
                else:
                    # simulate close on mock and fills
                    oid = self.mock.place_order(sym, 'sell', s.get('pos_size') or 0)
                    trace['events'].append({'type': 'place_close', 'oid': oid, 'price': price, 'size': s.get('pos_size')})
                    fills, remainder = self._simulate_fills(sym, 'sell', s.get('pos_size') or 0, price)
                    for f in fills:
                        fee = f['qty'] * f['price'] * self.fee_rate
                        trace['events'].append({'type': 'fill', 'oid': oid, 'side': 'sell', 'qty': f['qty'], 'price': f['price'], 'fee': fee, 'ts': f['ts']})
                    if remainder > 0:
                        trace['events'].append({'type': 'partial_unfilled', 'oid': oid, 'remaining_qty': remainder})

        # finalize trace after processing all signals
        trace['end_time'] = time.time()
        # persist trace
        out_dir = os.path.join(ROOT, 'var', 'executions')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'{run_id}.json')
        with open(out_path, 'w', encoding='utf-8') as fh:
            json.dump(trace, fh, indent=2)

        # append minimal log
        log_path = os.path.join(ROOT, 'var', 'executions.log')
        with open(log_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'run_id': run_id, 'ts': time.time(), 'mode': trace['mode'], 'events': len(trace['events'])}) + '\n')

        return {'run_id': run_id, 'trace_path': out_path, 'events': len(trace['events'])}

        # helper to simulate fills from mock order book levels
    def _simulate_fills(self, symbol: str, side: str, qty: float, target_price: Optional[float]) -> (List[Dict], float):
        """Simulate fills against the MockExchange synthetic order book.

        Returns a list of fills (dict with qty, price, ts) and remaining_qty.
        """
        fills = []
        if qty <= 0:
            return fills, 0.0
        # ask levels for buys, bids for sells
        ob = self.mock.get_order_book(symbol, depth=20)
        levels = ob.get('asks') if side == 'long' else ob.get('bids')
        rem = float(qty)
        now = time.time()
        for i, (lvl_price, lvl_qty) in enumerate(levels):
            # lvl_qty as provided by mock is base asset qty
            take = min(rem, float(lvl_qty))
            if take <= 0:
                continue
            # use level price as executed price (or target_price if provided and more aggressive)
            exec_price = float(lvl_price)
            # if target_price exists and would be more aggressive, prefer it
            try:
                if target_price is not None:
                    tp = float(target_price)
                    # for buys, lower price is better for maker but taker will pay ask; we'll keep lvl price
            except Exception:
                pass
            fills.append({'qty': take, 'price': exec_price, 'ts': now + i * 0.01})
            rem -= take
            if rem <= 1e-12:
                break
        return fills, rem

    def process_live_action(self, action: dict, run_id: Optional[str] = None, execute: bool = True) -> Dict:
        """Process a single live action dict and return a small trace summary.

        action shape expected: { 'id', 'timestamp', 'symbol', 'action', 'pos_size', 'price_hint', 'reason' }
        """
        if run_id is None:
            run_id = uuid.uuid4().hex
        trace = {'run_id': run_id, 'mode': self.mode if execute else 'dry', 'start_time': time.time(), 'events': []}
        sym = action.get('symbol') or 'UNKNOWN'
        act = action.get('action') or ''
        price = action.get('price_hint')
        size = action.get('pos_size') or 0

        def _make_serializable(o):
            try:
                return json.loads(json.dumps(o))
            except Exception:
                return str(o)

        # Map live actions to existing flows
        if act.startswith('open_'):
            side = 'long' if 'long' in act else 'short'
            if not execute:
                decision = {'action': 'enter', 'direction': side, 'size': size}
                res = self.dry.step(action.get('timestamp'), price, decision)
                trace['events'].append({'type': 'enter', 'side': side, 'price': price, 'res': _make_serializable(res)})
            else:
                oid = self.mock.place_order(sym, 'buy' if side == 'long' else 'sell', size)
                trace['events'].append({'type': 'place', 'oid': oid, 'side': side, 'price': price, 'size': size})
                fills, remainder = self._simulate_fills(sym, side, size, price)
                for f in fills:
                    fee = f['qty'] * f['price'] * self.fee_rate
                    trace['events'].append({'type': 'fill', 'oid': oid, 'side': side, 'qty': f['qty'], 'price': f['price'], 'fee': fee, 'ts': f['ts']})
                if remainder > 0:
                    trace['events'].append({'type': 'partial_unfilled', 'oid': oid, 'remaining_qty': remainder})

        elif act.startswith('close_') or act == 'close' or act == 'close_long' or act == 'close_short':
            if not execute:
                decision = {'action': 'exit'}
                res = self.dry.step(action.get('timestamp'), price, decision)
                trace['events'].append({'type': 'exit', 'price': price, 'res': _make_serializable(res)})
            else:
                oid = self.mock.place_order(sym, 'sell', size)
                trace['events'].append({'type': 'place_close', 'oid': oid, 'price': price, 'size': size})
                fills, remainder = self._simulate_fills(sym, 'sell', size, price)
                for f in fills:
                    fee = f['qty'] * f['price'] * self.fee_rate
                    trace['events'].append({'type': 'fill', 'oid': oid, 'side': 'sell', 'qty': f['qty'], 'price': f['price'], 'fee': fee, 'ts': f['ts']})
                if remainder > 0:
                    trace['events'].append({'type': 'partial_unfilled', 'oid': oid, 'remaining_qty': remainder})
        else:
            trace['events'].append({'type': 'noop', 'raw': _make_serializable(action)})

        trace['end_time'] = time.time()
        out_dir = os.path.join(ROOT, 'var', 'executions')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'{run_id}.json')
        try:
            with open(out_path, 'w', encoding='utf-8') as fh:
                json.dump(trace, fh, indent=2)
        except Exception:
            pass
        # append minimal log
        log_path = os.path.join(ROOT, 'var', 'executions.log')
        try:
            with open(log_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps({'run_id': run_id, 'ts': time.time(), 'mode': trace['mode'], 'events': len(trace['events'])}) + '\n')
        except Exception:
            pass

        return {'run_id': run_id, 'trace_path': out_path, 'events': len(trace['events'])}
