from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Optional
from urllib import request as _urllib_request, parse as _urllib_parse

from .strategy_executor import StrategyExecutor
from .live_dashboard import get_dashboard, Signal, Position

# Minimal Binance futures klines URL (public)
BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"


class LiveStrategy:
    """Run the bear strategy logic on live market klines and emit actions.

    This is a lightweight live engine intended to reproduce the same rule
    set as tools/run_bear_verbose.py but driven by live klines. It emits a
    simple action object and passes it to StrategyExecutor for execution.
    """

    def __init__(self, symbol: str, mode: str = 'bear', interval: str = '15m'):
        self.symbol = symbol.upper()
        self.mode = mode.lower()
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self._seen_actions: set[str] = set()
        
        # Validate mode
        valid_modes = ['bear', 'bull', 'scalp', 'range']
        if self.mode not in valid_modes:
            raise ValueError(f"Invalid mode '{self.mode}'. Must be one of {valid_modes}")
        
        # Mode-specific parameters
        if self.mode == 'bear':
            # Bear market (short-bias): parameters copied from run_bear_verbose
            self.p15_thresh = 5.0
            self.p30_thresh = 10.0
            self.p60_thresh = 12.0
            self.sl_pct = 0.01
            self.tp_pct = 0.02
            self.risk_pct = 0.2
        elif self.mode == 'bull':
            # Bull market (long-bias): parameters from backtest_bull_trend_long
            self.p15_thresh = 7.0
            self.p30_thresh = 12.0
            self.p60_thresh = 15.0
            self.sl_pct = 0.01
            self.tp_pct = 0.02
            self.risk_pct = 0.1  # 10% position sizing for bull
        elif self.mode == 'scalp':
            # Scalp mode: Quick entries/exits based on QuickScalpStrategy
            # Use 1m interval for scalping, fetch more bars for indicators
            self.interval = '1m'
            # Import and initialize QuickScalpStrategy
            from .strategy import QuickScalpStrategy
            self.scalp_strategy = QuickScalpStrategy(
                notional_per_trade=200.0,    # Larger base size for better absolute profits
                sma_window=6,
                vol_window=6,
                entry_threshold=0.012,       # 1.2% deviation (more selective entries)
                exit_target=0.025,           # 2.5% profit target (net ~2.1% after fees)
                partial_target=0.015,        # 1.5% partial (net ~1.2% after fees)
                stop_loss=0.015,             # 1.5% stop loss (wider breathing room)
                max_holding_bars=120,        # 120 minutes (2 hours max hold)
                trend_filter=True,           # Enable trend filtering
                sr_threshold_pct=0.008,      # 0.8% near SR levels (slightly relaxed)
                momentum_threshold=0.01,     # Momentum filter
                min_notional=20.0,           # Min $20 position
                max_notional=2000.0,         # Max $2000 position (increased)
            )
            self.sl_pct = 0.015
            self.tp_pct = 0.025
            self.risk_pct = 0.08  # 8% position sizing for scalping (increased)
        
        elif self.mode == 'range':
            # Range/Grid mode: Trade sideways markets with defined support/resistance
            # Use 15m interval for range detection
            self.interval = '15m'
            # Import and initialize RangeGridStrategy
            from .strategy import RangeGridStrategy
            self.range_strategy = RangeGridStrategy(
                notional_per_level=150.0,    # $150 per grid level
                lookback_bars=50,            # Look back 50 bars for range
                bb_period=20,                # 20-period Bollinger Bands
                bb_std=2.0,                  # 2 standard deviations
                range_buffer_pct=0.01,       # 1% buffer from range edges
                grid_levels=3,               # 3 levels within range
                profit_per_grid=0.015,       # 1.5% profit per level
                stop_loss_pct=0.025,         # 2.5% stop on range break
                max_volatility=0.02,         # Max 2% vol to trade
                min_range_size=0.03,         # Min 3% range size
                max_positions=3,             # Max 3 concurrent positions
                min_notional=20.0,
                max_notional=1500.0,
            )
            self.sl_pct = 0.025
            self.tp_pct = 0.015
            self.risk_pct = 0.06  # 6% position sizing for range trading
        
        self.fee_pct = 0.0007
        self.slip_pct = 0.0005
        # executor (paper/dry) - default to paper for safety
        self.exec_mode = os.environ.get('ARB_LIVE_DEFAULT_EXEC_MODE', 'paper')
        self.se = StrategyExecutor(mode=self.exec_mode)
        
        # Dashboard integration
        self.dashboard = get_dashboard()
        self._current_position: Optional[Position] = None

    def _fetch_klines(self, limit: int = 5):
        """Fetch recent klines. Prefer a registered websocket feeder if available,
        otherwise fall back to Binance REST klines.
        """
        # Try feeder first
        try:
            from .exchanges.ws_feed_manager import get_feeder
            feeder = get_feeder('binance')
            if feeder is not None:
                # prefer feeder-provided klines/candles if available
                if hasattr(feeder, 'get_klines'):
                    try:
                        res = feeder.get_klines(self.symbol, self.interval, limit)
                        return res or []
                    except Exception:
                        pass
                if hasattr(feeder, 'get_candles'):
                    try:
                        res = feeder.get_candles(self.symbol, self.interval, limit)
                        return res or []
                    except Exception:
                        pass
                # fallback: if feeder exposes a simple price history buffer, try to read closes
                if hasattr(feeder, 'get_price_history'):
                    try:
                        ph = feeder.get_price_history(self.symbol, limit)
                        # return list of [open_time, open, high, low, close, ...] like REST
                        out = []
                        for ts, price in ph:
                            out.append([ts, price, price, price, price, 0])
                        return out
                    except Exception:
                        pass
        except Exception:
            pass

        # Fallback to REST fetch from Binance futures
        params = {'symbol': self.symbol, 'interval': self.interval, 'limit': limit}
        q = _urllib_parse.urlencode(params)
        url = f"{BINANCE_FUTURES_KLINES_URL}?{q}"
        req = _urllib_request.Request(url, headers={'User-Agent': 'arb-live-strategy/1.0'})
        try:
            with _urllib_request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data
        except Exception:
            return []

    def _make_action(self, action: str, price: float, pos_size: Optional[float], reason: str):
        aid = uuid.uuid4().hex
        act = {
            'id': aid,
            'timestamp': int(time.time() * 1000),
            'symbol': self.symbol,
            'action': action,
            'pos_size': pos_size,
            'price_hint': price,
            'reason': reason,
        }
        return act

    async def _loop(self, poll_s: float = 15.0):
        # rolling buffer of closes (most recent last) length >= 5 to compute 15/30/60m
        closes = []
        # For scalp mode, fetch more initial bars
        initial_fetch = 50 if self.mode == 'scalp' else 5
        print(f"[LiveStrategy] Starting {self.mode} strategy loop for {self.symbol} (interval={self.interval})")
        
        while not self._stop:
            # fetch several recent klines and compute close list
            fetch_limit = initial_fetch if len(closes) < initial_fetch else 5
            data = await asyncio.to_thread(self._fetch_klines, fetch_limit)
            new_closes = []
            try:
                for k in data:
                    # kline format: [open_time, open, high, low, close, ...]
                    c = float(k[4])
                    new_closes.append(c)
            except Exception:
                new_closes = []
            if new_closes:
                closes = new_closes
            
            if len(closes) > 0:
                print(f"[LiveStrategy {self.symbol}] Closes buffer: {len(closes)} bars, current price: {closes[-1]:.2f}")
            
            # Update position P&L with current price
            if closes and self._current_position:
                current_price = closes[-1]
                self.dashboard.update_position_pnl(self.symbol, current_price)

            # need at least 5 15m closes to compute pct15 (1), pct30 (2), pct60 (4)
            if len(closes) >= 5:
                price = closes[-1]
                def pct(n):
                    try:
                        prev = closes[-1 - n]
                        if prev == 0:
                            return None
                        return (price - prev) / prev * 100.0
                    except Exception:
                        return None

                pct15 = pct(1)
                pct30 = pct(2)
                pct60 = pct(4)

                # Mode-specific signal generation
                if self.mode == 'bear':
                    # Bear mode: long when deeply oversold, short quick on pumps
                    long_signal = False
                    short_quick = False
                    signal_reason = None
                    
                    if pct15 is not None and pct30 is not None and pct60 is not None:
                        # Calculate adaptive 60-min threshold based on max drop in last 60 minutes
                        # This catches extreme volatile moves that might not recover
                        # We look for the WORST drop at any point in the last 60 minutes
                        max_drop_60m = 0.0
                        if len(closes) >= 5:  # Need at least 5 bars (60 mins of 15m candles)
                            for i in range(1, min(5, len(closes))):
                                prev = closes[-1 - i]
                                if prev > 0:
                                    drop = ((price - prev) / prev) * 100.0
                                    if drop < max_drop_60m:
                                        max_drop_60m = drop
                        
                        # Standard entry: strict conditions
                        standard_condition = (pct15 <= -self.p15_thresh) and (pct30 <= -self.p30_thresh) and (pct60 <= -self.p60_thresh)
                        
                        # Adaptive entry: if max drop in 60min exceeds -12%, use relaxed conditions
                        # This catches scenarios where price crashed -20% then recovered
                        # We still want to enter because the volatility suggests more downside
                        extreme_drop_detected = max_drop_60m <= -self.p60_thresh  # Worse than -12%
                        
                        # Scale relaxation based on severity of max drop
                        # -12% to -15%: relax pct30 to -8% (20% relaxation)
                        # -15% to -20%: relax pct30 to -6% (40% relaxation)
                        # -20%+:        relax pct30 to -5% (50% relaxation)
                        if max_drop_60m <= -20.0:
                            relaxed_p30 = -(self.p30_thresh * 0.5)  # -5%
                        elif max_drop_60m <= -15.0:
                            relaxed_p30 = -(self.p30_thresh * 0.6)  # -6%
                        else:
                            relaxed_p30 = -(self.p30_thresh * 0.8)  # -8%
                        
                        adaptive_condition = (pct15 <= -self.p15_thresh) and (pct30 <= relaxed_p30)
                        
                        if standard_condition:
                            long_signal = True
                            signal_reason = f'standard_oversold: pct15={pct15:.2f}%, pct30={pct30:.2f}%, pct60={pct60:.2f}%'
                        elif extreme_drop_detected and adaptive_condition:
                            # Extreme volatility detected - use relaxed entry
                            long_signal = True
                            signal_reason = f'extreme_volatility: max_drop_60m={max_drop_60m:.2f}%, current: pct15={pct15:.2f}%, pct30={pct30:.2f}%, pct60={pct60:.2f}%'
                    
                    short_quick = True if (pct15 is not None and pct15 >= 5.0) else False

                    # Check if position already exists before opening new one
                    current_pos = self.dashboard.get_position(self.symbol)
                    
                    if long_signal and current_pos is None:
                        reason = signal_reason if signal_reason else 'long_signal'
                        act = self._make_action('open_long', price, None, reason)
                        await self._emit_action(act)
                    elif short_quick and current_pos is None:
                        act = self._make_action('open_short', price, None, 'short_quick')
                        await self._emit_action(act)
                    elif current_pos is not None:
                        # Position exists - check stop-loss and take-profit
                        should_close = False
                        close_reason = ''
                        
                        if current_pos.side == 'long':
                            if price <= current_pos.stop_loss:
                                should_close = True
                                close_reason = 'stop_loss'
                            elif price >= current_pos.take_profit:
                                should_close = True
                                close_reason = 'take_profit'
                        else:  # short
                            if price >= current_pos.stop_loss:
                                should_close = True
                                close_reason = 'stop_loss'
                            elif price <= current_pos.take_profit:
                                should_close = True
                                close_reason = 'take_profit'
                        
                        if should_close:
                            action_type = 'close_long' if current_pos.side == 'long' else 'close_short'
                            act = self._make_action(action_type, price, None, close_reason)
                            await self._emit_action(act)

                elif self.mode == 'bull':
                    # Bull mode: short when deeply overbought, long quick on dips
                    short_signal = False
                    long_quick = False
                    if pct15 is not None and pct30 is not None and pct60 is not None:
                        if (pct15 >= self.p15_thresh) and (pct30 >= self.p30_thresh) and (pct60 >= self.p60_thresh):
                            short_signal = True
                    long_quick = True if (pct15 is not None and pct15 <= -5.0) else False

                    # Check if position already exists before opening new one
                    current_pos = self.dashboard.get_position(self.symbol)
                    
                    if short_signal and current_pos is None:
                        act = self._make_action('open_short', price, None, 'short_signal')
                        await self._emit_action(act)
                    elif long_quick and current_pos is None:
                        act = self._make_action('open_long', price, None, 'long_quick')
                        await self._emit_action(act)
                    elif current_pos is not None:
                        # Position exists - check stop-loss and take-profit
                        should_close = False
                        close_reason = ''
                        
                        if current_pos.side == 'long':
                            if price <= current_pos.stop_loss:
                                should_close = True
                                close_reason = 'stop_loss'
                            elif price >= current_pos.take_profit:
                                should_close = True
                                close_reason = 'take_profit'
                        else:  # short
                            if price >= current_pos.stop_loss:
                                should_close = True
                                close_reason = 'stop_loss'
                            elif price <= current_pos.take_profit:
                                should_close = True
                                close_reason = 'take_profit'
                        
                        if should_close:
                            action_type = 'close_long' if current_pos.side == 'long' else 'close_short'
                            act = self._make_action(action_type, price, None, close_reason)
                            await self._emit_action(act)

                elif self.mode == 'scalp':
                    # Scalp mode: Use QuickScalpStrategy for decisions
                    # Need at least 30+ bars for strategy indicators
                    print(f"[Scalp] Checking decision... bars={len(closes)}, need 40+")
                    if len(closes) >= 40:
                        # Check current position from dashboard
                        current_pos = self.dashboard.get_position(self.symbol) if hasattr(self.dashboard, 'get_position') else self._current_position
                        
                        # Get funding rate (optional, can be None)
                        funding_rate = None
                        try:
                            # Attempt to fetch current funding rate from Binance
                            from urllib import request as _req, parse as _p
                            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={self.symbol}"
                            with _req.urlopen(url, timeout=5) as r:
                                data = json.load(r)
                                funding_rate = float(data.get('lastFundingRate', 0))
                        except Exception:
                            pass
                        
                        # Calculate bars held if in position
                        bars_held = 0
                        if current_pos is not None:
                            entry_time = getattr(current_pos, 'entry_time', None)
                            if entry_time:
                                bars_held = int((time.time() * 1000 - entry_time) / 60000)  # Minutes
                        
                        # Get strategy decision
                        decision = self.scalp_strategy.decide(
                            price=price,
                            recent_closes=closes,
                            funding_rate=funding_rate,
                            position=current_pos,
                            bars_held=bars_held
                        )
                        
                        # Execute based on decision
                        if decision.action == 'enter':
                            action_type = 'open_long' if decision.direction == 'long' else 'open_short'
                            act = self._make_action(action_type, price, decision.size, decision.reason)
                            await self._emit_action(act)
                        
                        elif decision.action == 'exit' and current_pos is not None:
                            action_type = 'close_long' if current_pos.side == 'long' else 'close_short'
                            act = self._make_action(action_type, price, None, decision.reason)
                            await self._emit_action(act)
                        
                        elif decision.action == 'reduce' and current_pos is not None and decision.fraction:
                            # Partial exit - close fraction of position
                            action_type = 'close_long' if current_pos.side == 'long' else 'close_short'
                            # Calculate size to close
                            close_size = getattr(current_pos, 'size', 0) * decision.fraction if hasattr(current_pos, 'size') else None
                            act = self._make_action(action_type, price, close_size, f"partial_exit({decision.fraction:.0%}): {decision.reason}")
                            await self._emit_action(act)

                elif self.mode == 'range':
                    # Range/Grid mode: Use RangeGridStrategy for decisions
                    # Need at least 50+ bars for range detection
                    if len(closes) >= 60:
                        # Check current position from dashboard
                        current_pos = self.dashboard.get_position(self.symbol) if hasattr(self.dashboard, 'get_position') else self._current_position
                        
                        # Calculate bars held if in position
                        bars_held = 0
                        if current_pos is not None:
                            entry_time = getattr(current_pos, 'entry_time', None)
                            if entry_time:
                                bars_held = int((time.time() * 1000 - entry_time) / 60000)  # Minutes
                        
                        # Get strategy decision
                        decision = self.range_strategy.decide(
                            price=price,
                            recent_closes=closes,
                            funding_rate=None,
                            position=current_pos,
                            bars_held=bars_held
                        )
                        
                        # Execute based on decision
                        if decision.action == 'enter':
                            action_type = 'open_long' if decision.direction == 'long' else 'open_short'
                            act = self._make_action(action_type, price, decision.size, decision.reason)
                            await self._emit_action(act)
                        
                        elif decision.action == 'exit' and current_pos is not None:
                            action_type = 'close_long' if current_pos.side == 'long' else 'close_short'
                            act = self._make_action(action_type, price, None, decision.reason)
                            await self._emit_action(act)

            await asyncio.sleep(poll_s)

    async def _emit_action(self, action: dict):
        # idempotency: ignore if seen recently
        aid = action.get('id')
        if not aid or aid in self._seen_actions:
            return
        self._seen_actions.add(aid)
        
        # Create signal record for dashboard
        signal = Signal(
            id=aid,
            timestamp=action.get('timestamp', int(time.time() * 1000)),
            symbol=action.get('symbol', self.symbol),
            action=action.get('action', 'unknown'),
            price=action.get('price_hint', 0.0),
            size=action.get('pos_size'),
            reason=action.get('reason', ''),
            status='pending'
        )
        self.dashboard.add_signal(signal)
        
        # compute pos_size using live account equity if possible
        try:
            pos_size = await self._compute_pos_size(action.get('price_hint'))
            action['pos_size'] = pos_size
            signal.size = pos_size
        except Exception:
            # leave pos_size as-is (None) if computation fails
            pass

        # pass to StrategyExecutor for processing in background thread
        try:
            # ensure execution happens in thread to avoid blocking
            res = await asyncio.to_thread(lambda: self.se.process_live_action(action, run_id=None, execute=(self.exec_mode!='dry')))
            
            # Update signal status based on result
            if res and not res.get('error'):
                self.dashboard.update_signal_status(aid, 'executed', order_id=res.get('order_id'))
                
                # Track position if order executed
                price = action.get('price_hint')
                size = action.get('pos_size')
                if price and size:
                    action_type = action.get('action', '')
                    
                    if action_type == 'open_long':
                        # Open long position
                        position = Position(
                            symbol=self.symbol,
                            side='long',
                            entry_price=price,
                            size=size,
                            entry_time=int(time.time() * 1000),
                            stop_loss=price * (1 - self.sl_pct),
                            take_profit=price * (1 + self.tp_pct)
                        )
                        self.dashboard.open_position(position)
                        self._current_position = position
                        
                    elif action_type == 'open_short':
                        # Open short position
                        position = Position(
                            symbol=self.symbol,
                            side='short',
                            entry_price=price,
                            size=size,
                            entry_time=int(time.time() * 1000),
                            stop_loss=price * (1 + self.sl_pct),
                            take_profit=price * (1 - self.tp_pct)
                        )
                        self.dashboard.open_position(position)
                        self._current_position = position
                        
                    elif action_type in ['close_long', 'close_short']:
                        # Close position
                        trade = self.dashboard.close_position(self.symbol, price, reason='signal')
                        self._current_position = None
                        if trade:
                            print(f"[LiveStrategy] Trade completed: {trade.symbol} {trade.side} P&L=${trade.pnl:.2f} ({trade.pnl_pct:.2f}%)")
                        else:
                            print(f"[LiveStrategy] WARNING: close_position returned None for {self.symbol}")
            else:
                error_msg = res.get('error', 'unknown error') if res else 'no response'
                self.dashboard.update_signal_status(aid, 'failed', error=error_msg)
            
            return res
        except Exception as e:
            self.dashboard.update_signal_status(aid, 'failed', error=str(e))
            return {'error': 'failed to process action'}

    async def _compute_pos_size(self, price: Optional[float]) -> Optional[float]:
        """Compute position size based on live account equity via CCXT when available.

        Returns base asset quantity (size) or None on failure.
        """
        if price is None or price <= 0:
            return None

        # attempt to use CCXTExchange if API keys present
        try:
            key = (os.environ.get('BINANCE_API_KEY') or '').strip()
            secret = (os.environ.get('BINANCE_API_SECRET') or '').strip()
            if not key or not secret:
                return None
            # import CCXTExchange lazily in thread
            from .exchanges.ccxt_adapter import CCXTExchange

            def _get_balance():
                try:
                    inst = CCXTExchange('binance', api_key=key, secret=secret, options={'defaultType': 'future'})
                    bal = inst.client.fetch_balance()
                    # try unified 'total' or 'USDT' key for futures wallet
                    total = bal.get('total') or {}
                    usdt = None
                    # prefer USDT
                    for k in ('USDT', 'usdt'):
                        if k in total:
                            usdt = float(total.get(k) or 0.0)
                            break
                    if usdt is None:
                        # some exchanges expose 'USDT' under other keys or provide 'total' as flat
                        # try to guess by scanning numeric values
                        vals = [float(v) for v in (total.values() or []) if isinstance(v, (int, float))]
                        usdt = vals[0] if vals else 0.0
                    return usdt
                except Exception:
                    return None

            usdt_bal = await asyncio.to_thread(_get_balance)
            if usdt_bal is None:
                return None
            amount = usdt_bal * self.risk_pct
            size = amount / float(price) if price > 0 else None
            return size
        except Exception:
            return None

    def start(self):
        if self._task is not None and not self._task.done():
            return False
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        
        # Register with dashboard
        self.dashboard.start_strategy(self.symbol, self.exec_mode, self.mode)
        
        return True

    async def stop(self):
        self._stop = True
        if self._task is not None:
            try:
                await self._task
            except Exception:
                pass
        self._task = None
        
        # Unregister from dashboard
        self.dashboard.stop_strategy()
        
        return True

    def running(self):
        return self._task is not None and not self._task.done()
