from dataclasses import dataclass
from collections import deque
from typing import Deque, List, Optional
import math


@dataclass
class TradeDecision:
    action: str  # 'enter' | 'exit' | 'hold' | 'reduce'
    direction: Optional[str] = None  # 'long' | 'short'
    size: float = 0.0  # notional in quote currency (e.g., USDT)
    reason: Optional[str] = None
    fraction: Optional[float] = None  # for reduce: fraction to close (0-1)


class QuickScalpStrategy:
    """A small, deterministic intraday scalp strategy used for dry-runs and backtests.

    Enhancements:
    - Position sizing scaled by short-term volatility (lower size for higher vol).
    - Time-based exit (max_holding_bars).
    - Partial exits when partial profit target is reached.

    Contract:
    - decide(price, recent_closes, funding_rate, position=None, bars_held=0)
      position: optional position-like object with attributes entry_price and direction
      bars_held: integer number of bars the position has been held
    """

    def __init__(
        self,
        notional_per_trade: float = 100.0,
        sma_window: int = 6,
        vol_window: int = 6,
        entry_threshold: float = 0.008,  # 0.8% deviation from sma
        exit_target: float = 0.009,  # 0.9% profit
        partial_target: float = 0.0045,  # 0.45% -> take partial profit
        stop_loss: float = 0.01,  # 1% loss
        max_holding_bars: int = 60,  # e.g., 60 minutes
        funding_influence: float = 0.5,  # scale factor to nudge direction when funding present
        min_notional: float = 10.0,
        max_notional: float = 1000.0,
        target_vol: float = 0.01,  # target volatility used to scale size (1% returns stdev)
        round_to: float = 0.01,
        # trend filtering / support-resistance gating
        trend_window: int = 30,
        sr_lookback: int = 20,
        sr_threshold_pct: float = 0.005,  # 0.5% proximate to SR level
        trend_filter: bool = True,
        # pivot/ATR and momentum filtering
        atr_multiplier: float = 1.5,
        momentum_window: int = 6,
        momentum_threshold: float = 0.01,  # 1% negative momentum => strong bearish
    ):
        self.notional_per_trade = notional_per_trade
        self.sma_window = sma_window
        self.vol_window = vol_window
        self.entry_threshold = entry_threshold
        self.exit_target = exit_target
        self.partial_target = partial_target
        self.stop_loss = stop_loss
        self.max_holding_bars = max_holding_bars
        self.funding_influence = funding_influence
        self.min_notional = min_notional
        self.max_notional = max_notional
        self.target_vol = target_vol
        self.round_to = round_to
        # trend / support-resistance params
        self.trend_window = trend_window
        self.sr_lookback = sr_lookback
        self.sr_threshold_pct = sr_threshold_pct
        self.trend_filter = trend_filter
        # pivot/ATR and momentum filtering
        self.atr_multiplier = atr_multiplier
        self.momentum_window = momentum_window
        # make short-term momentum require a stronger positive signal by default
        self.momentum_threshold = momentum_threshold
        # additional strict short-term positive threshold (fractional returns)
        self.short_momentum_min = 0.001  # require >0.1% avg return over momentum_window
        # higher-timeframe momentum (bars count, defaults assume 1m bars: 12h=720,24h=1440)
        self.htf_12h_bars = 720
        self.htf_24h_bars = 1440
        # require a larger negative HTF momentum by default
        self.htf_momentum_threshold = 0.03
        # allow using HTF volatility or SMA slope to confirm HTF bearish regime
        self.htf_volatility_max = 0.02  # if HTF volatility below this, consider regime stable
        self.htf_sma_slope_min = -0.002  # require HTF SMA slope to be <= this (i.e., slightly negative)
        # robust pivot params
        self.pivot_radius = max(1, self.sr_lookback // 6)
        self.pivot_min_distance = max(6, self.sr_lookback // 4)
        self.pivot_prominence_pct = 0.005
        # risk-based sizing and ATR stop/target
        self.risk_per_trade = 25.0  # $ risk per trade (dollar-denominated)
        self.k_stop = 1.25
        self.k_target = 2.0
        # floor for ATR-based stop distance as fraction of price to avoid tiny stops
        self.min_stop_pct = 0.002

        # Simple rolling window for SMA if needed by caller-less usage
        self._close_window: Deque[float] = deque(maxlen=sma_window)

    def update_close(self, close: float):
        self._close_window.append(close)

    def compute_sma(self, recent_closes: List[float]) -> Optional[float]:
        data = list(recent_closes)[-self.sma_window :]
        if len(data) < 2:
            return None
        return sum(data) / len(data)

    def compute_volatility(self, recent_closes: List[float]) -> Optional[float]:
        data = list(recent_closes)[-self.vol_window - 1 :]
        if len(data) < 3:
            return None
        # compute returns
        rets = []
        for i in range(1, len(data)):
            prev = data[i - 1]
            cur = data[i]
            if prev == 0:
                continue
            rets.append((cur - prev) / prev)
        if len(rets) < 2:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(var)

    def compute_slope(self, close: float, sma: float) -> float:
        if sma == 0:
            return 0.0
        return (close - sma) / sma

    def compute_atr_like(self, recent_closes: List[float]) -> Optional[float]:
        """Approximate ATR using average true-range-like absolute returns.

        Returns ATR as a fractional value (e.g., 0.01 == 1%). Works with closes only.
        """
        data = list(recent_closes)[-max(self.vol_window, 3) - 1 :]
        if len(data) < 3:
            return None
        trs = []
        for i in range(1, len(data)):
            prev = data[i - 1]
            cur = data[i]
            if prev == 0:
                continue
            trs.append(abs(cur - prev) / prev)
        if not trs:
            return None
        return sum(trs) / len(trs)

    def find_latest_pivots(
        self,
        recent_closes: List[float],
        radius: Optional[int] = None,
        min_distance: Optional[int] = None,
        prominence_pct: Optional[float] = None,
    ) -> (Optional[float], Optional[float]):
        """Robust pivot finder.

        Scans the last `sr_lookback` bars for local pivot highs and lows.
        A pivot is a local extremum within +/- radius bars and must be separated
        from the previous pivot by at least `min_distance` bars. The pivot value
        must exceed surrounding values by at least `prominence_pct` fraction to
        avoid tiny noise pivots.

        Returns (latest_pivot_high, latest_pivot_low) where either may be None.
        """
        data = list(recent_closes)
        n = len(data)
        if radius is None:
            radius = self.pivot_radius
        if min_distance is None:
            min_distance = self.pivot_min_distance
        if prominence_pct is None:
            prominence_pct = self.pivot_prominence_pct

        if n < 2 or radius < 1:
            return None, None

        start = max(0, n - self.sr_lookback)
        pivot_highs = []  # list of tuples (index, value)
        pivot_lows = []

        for i in range(start, n):
            lo = max(start, i - radius)
            hi = min(n, i + radius + 1)
            window = data[lo:hi]
            if not window or len(window) < 2:
                continue
            val = data[i]
            # exclude edges where window is incomplete
            # compute max/min excluding self for prominence
            others = window[:]
            mid = i - lo
            others.pop(mid)
            max_others = max(others)
            min_others = min(others)

            # check for pivot high
            if val > max_others and (val - max_others) / max_others >= prominence_pct:
                # ensure spacing from previous pivots
                if not pivot_highs or (i - pivot_highs[-1][0]) >= min_distance:
                    pivot_highs.append((i, val))

            # check for pivot low
            if val < min_others and (min_others - val) / min_others >= prominence_pct:
                if not pivot_lows or (i - pivot_lows[-1][0]) >= min_distance:
                    pivot_lows.append((i, val))

        latest_high = pivot_highs[-1][1] if pivot_highs else None
        latest_low = pivot_lows[-1][1] if pivot_lows else None
        return latest_high, latest_low

    def compute_momentum(self, recent_closes: List[float], window: int) -> Optional[float]:
        data = list(recent_closes)[-window - 1 :]
        if len(data) < 2:
            return None
        rets = []
        for i in range(1, len(data)):
            prev = data[i - 1]
            cur = data[i]
            if prev == 0:
                continue
            rets.append((cur - prev) / prev)
        if not rets:
            return None
        return sum(rets) / len(rets)

    def _size_by_vol(self, vol: Optional[float]) -> float:
        # If vol not available, return base notional
        if vol is None or vol == 0:
            size = self.notional_per_trade
        else:
            # scale inversely with vol relative to target_vol
            scale = self.target_vol / vol
            # clamp scale to [0.5, 2.0]
            scale = max(0.5, min(2.0, scale))
            size = self.notional_per_trade * scale

        # clamp to configured bounds
        size = max(self.min_notional, min(self.max_notional, size))
        # round to configured granularity
        if self.round_to and self.round_to > 0:
            size = round(size / self.round_to) * self.round_to
        return size

    def size_by_risk(self, price: float, atr: Optional[float], direction: str) -> float:
        """Compute position size (notional in quote) based on dollar risk and ATR stop.

        - If ATR available: stop distance = k_stop * ATR * price (fractional * price gives absolute price distance)
        - Desired notional ~= risk_per_trade * (price / stop_distance)
        - Round and clamp to min/max notional
        """
        # require ATR; if missing, fallback
        if atr is None or atr <= 0:
            return None

        # enforce a minimum ATR-derived stop as a fraction of price
        effective_atr = max(atr, self.min_stop_pct)
        # absolute stop distance in quote currency per unit
        stop_dist_abs = self.k_stop * effective_atr * price
        if stop_dist_abs <= 0:
            return None

        # desired notional to risk exactly risk_per_trade: R / (k_stop * atr)
        desired_notional = self.risk_per_trade / (self.k_stop * effective_atr)

        # If desired notional is below min_notional, skip trade (too small)
        if desired_notional < self.min_notional:
            return None

        # If desired notional is above max_notional, skip trade (would exceed allowed cap)
        if desired_notional > self.max_notional:
            return None

        size = desired_notional
        if self.round_to and self.round_to > 0:
            size = round(size / self.round_to) * self.round_to
        # final clamp (in case rounding pushed it out)
        if size < self.min_notional or size > self.max_notional:
            return None
        return size

    def decide(
        self,
        price: float,
        recent_closes: List[float],
        funding_rate: Optional[float],
        position=None,
        bars_held: int = 0,
    ) -> TradeDecision:
        """Make a decision given the latest market state.

        - When no position: entry rule based on slope vs SMA; size scaled by volatility.
        - When in a position: check partial exit, full exit by target/stop/time.
        """
        sma = self.compute_sma(recent_closes)
        vol = self.compute_volatility(recent_closes)
        if sma is None:
            return TradeDecision(action="hold", reason="insufficient history for sma")

        slope = self.compute_slope(price, sma)

        # compute longer-term trend, pivot SR and ATR bands, and momentum
        trend_sma = None
        trend_dir = None
        pivot_high = None
        pivot_low = None
        atr = None
        momentum = None
        if len(recent_closes) >= max(self.trend_window, self.sr_lookback, self.vol_window):
            # simple trend: compare price to moving average over trend_window
            trend_slice = list(recent_closes)[-self.trend_window :]
            if len(trend_slice) >= 2:
                trend_sma = sum(trend_slice) / len(trend_slice)
                if trend_sma != 0:
                    # small epsilon to avoid flipping on noise
                    eps = 1e-6
                    if price > trend_sma * (1.0 + eps):
                        trend_dir = "up"
                    elif price < trend_sma * (1.0 - eps):
                        trend_dir = "down"

            # pivot-based support/resistance
            radius = max(1, self.sr_lookback // 2)
            pivot_high, pivot_low = self.find_latest_pivots(recent_closes, radius)

            # ATR-like bands
            atr = self.compute_atr_like(recent_closes)

            # momentum (average returns over momentum_window)
            momentum = self.compute_momentum(recent_closes, self.momentum_window)

        # Nudge direction by funding rate
        funding_nudge = 0.0
        if funding_rate is not None:
            funding_nudge = self.funding_influence * funding_rate

        effective_slope = slope + funding_nudge

        # If currently in a position, evaluate exits or partial exits
        if position is not None:
            entry_price = getattr(position, "entry_price", None)
            direction = getattr(position, "direction", None)
            if entry_price is None or direction is None:
                return TradeDecision(action="hold", reason="bad_position_object")

            # compute percent move in direction
            if direction == "long":
                pct = (price - entry_price) / entry_price
            else:
                pct = (entry_price - price) / entry_price

            # Partial exit when we hit partial_target
            if pct >= self.partial_target:
                return TradeDecision(action="reduce", fraction=0.5, reason=f"partial_target hit pct={pct:.4f}")

            # Full exit on target or stop loss
            if pct >= self.exit_target:
                return TradeDecision(action="exit", reason=f"target hit pct={pct:.4f}")
            if pct <= -self.stop_loss:
                return TradeDecision(action="exit", reason=f"stop loss pct={pct:.4f}")

            # Time-based forced exit
            if bars_held >= self.max_holding_bars:
                return TradeDecision(action="exit", reason="time-based exit")

            return TradeDecision(action="hold", reason=f"in_position pct={pct:.4f}")

        # No position: entry rule
        if abs(effective_slope) >= self.entry_threshold:
            direction = "long" if effective_slope > 0 else "short"

            # trend filter: only trade in direction of longer-term trend when enabled
            if self.trend_filter and trend_dir is not None:
                if trend_dir == "up" and direction == "short":
                    return TradeDecision(action="hold", reason=f"trend up - skip short entry")
                if trend_dir == "down" and direction == "long":
                    return TradeDecision(action="hold", reason=f"trend down - skip long entry")

            # strong bearish momentum filter (short-term and higher timeframes):
            if direction == "long":
                if momentum is not None and momentum <= -abs(self.momentum_threshold):
                    return TradeDecision(action="hold", reason=f"strong bearish momentum - skip long entry mom={momentum:.4f}")

                # higher timeframe momentum: if we have enough recent_closes, compute
                # approximate momentum over 12h and 24h windows (bars are assumed to be 1m in default tools)
                htf12_mom = None
                htf24_mom = None
                if len(recent_closes) >= self.htf_12h_bars + 1:
                    htf12_mom = self.compute_momentum(recent_closes[-self.htf_12h_bars - 1 :], self.htf_12h_bars)
                if len(recent_closes) >= self.htf_24h_bars + 1:
                    htf24_mom = self.compute_momentum(recent_closes[-self.htf_24h_bars - 1 :], self.htf_24h_bars)

                # Strengthened HTF gating: require HTF12 to be sufficiently negative
                # AND confirm the HTF regime either by low HTF volatility (stable downtrend)
                # or by a negative HTF SMA slope. Also require short-term momentum to be
                # convincingly positive (above short_momentum_min).
                if htf12_mom is not None:
                    # compute HTF volatility and HTF SMA slope if enough data
                    htf12_vol = None
                    htf12_sma_slope = None
                    # htf12 slice = last htf_12h_bars+1 closes
                    if len(recent_closes) >= self.htf_12h_bars + 2:
                        htf_slice = list(recent_closes)[-self.htf_12h_bars - 1 :]
                        # HTF volatility (using same compute_volatility but adapted)
                        try:
                            htf12_vol = self.compute_volatility(htf_slice)
                        except Exception:
                            htf12_vol = None
                        # HTF SMA slope: compare latest price to HTF SMA
                        try:
                            htf12_sma = sum(htf_slice[-self.sma_window:]) / len(htf_slice[-self.sma_window:])
                            htf12_sma_slope = (htf_slice[-1] - htf12_sma) / htf12_sma if htf12_sma != 0 else None
                        except Exception:
                            htf12_sma_slope = None

                    # require HTF momentum to be below negative threshold
                    if not (htf12_mom <= -abs(self.htf_momentum_threshold)):
                        return TradeDecision(action="hold", reason=f"HTF12 not sufficiently bearish htf12={htf12_mom:.6f}")

                    # require either low HTF volatility OR negative HTF SMA slope as confirmation
                    vol_ok = (htf12_vol is not None and htf12_vol <= self.htf_volatility_max)
                    slope_ok = (htf12_sma_slope is not None and htf12_sma_slope <= self.htf_sma_slope_min)
                    if not (vol_ok or slope_ok):
                        return TradeDecision(action="hold", reason=f"HTF12 not confirmed by vol/slope vol={htf12_vol},slope={htf12_sma_slope}")

                    # require short-term momentum to be convincingly positive
                    if momentum is None or momentum <= self.short_momentum_min:
                        return TradeDecision(action="hold", reason=f"short-term momentum too weak mom={momentum}")

                if htf24_mom is not None and htf24_mom <= -abs(self.htf_momentum_threshold):
                    return TradeDecision(action="hold", reason=f"24h bearish momentum - skip long htf24={htf24_mom:.4f}")

            # support/resistance gating using pivot detection and ATR-bands
            # Use pivot if available; otherwise back off to recent high/low fallback
            recent_high = None
            recent_low = None
            if pivot_low is not None or pivot_high is not None:
                recent_low = pivot_low
                recent_high = pivot_high
            else:
                sr_slice = list(recent_closes)[-self.sr_lookback :]
                if len(sr_slice) > 0:
                    recent_high = max(sr_slice)
                    recent_low = min(sr_slice)

            # ATR-based bands (if ATR available)
            lower_band = None
            upper_band = None
            if atr is not None:
                lower_band = price * (1.0 - self.atr_multiplier * atr)
                upper_band = price * (1.0 + self.atr_multiplier * atr)

            if recent_low is not None and recent_high is not None:
                if direction == "long":
                    ok_pivot = False
                    ok_atr = False
                    if recent_low is not None:
                        if price <= recent_low * (1.0 + self.sr_threshold_pct):
                            ok_pivot = True
                    if lower_band is not None:
                        if price <= lower_band * (1.0 + self.sr_threshold_pct):
                            ok_atr = True
                    if not (ok_pivot or ok_atr):
                        return TradeDecision(action="hold", reason=f"not near support: price {price:.6f} > low {recent_low if recent_low is not None else 'na'}")
                else:
                    ok_pivot = False
                    ok_atr = False
                    if recent_high is not None:
                        if price >= recent_high * (1.0 - self.sr_threshold_pct):
                            ok_pivot = True
                    if upper_band is not None:
                        if price >= upper_band * (1.0 - self.sr_threshold_pct):
                            ok_atr = True
                    if not (ok_pivot or ok_atr):
                        return TradeDecision(action="hold", reason=f"not near resistance: price {price:.6f} < high {recent_high if recent_high is not None else 'na'}")

            size = self._size_by_vol(vol)
            reason = f"slope={slope:.4f},funding={funding_rate if funding_rate is not None else 0:.6f},vol={vol if vol is not None else 'na'},trend={trend_dir},sr_low={recent_low},sr_high={recent_high},atr={atr if atr is not None else 'na'},mom={momentum if momentum is not None else 'na'}"
            return TradeDecision(action="enter", direction=direction, size=size, reason=reason)

        return TradeDecision(action="hold", reason=f"slope={slope:.4f}")


class RangeGridStrategy:
    """A range/grid trading strategy for sideways markets.
    
    Trades within a defined price range by buying near support and selling near resistance.
    Uses Bollinger Bands and pivot points to identify range boundaries.
    Ideal for low volatility, mean-reverting markets.
    
    Features:
    - Identifies range boundaries using recent highs/lows and Bollinger Bands
    - Buys near lower band/support, sells near upper band/resistance
    - Multiple small positions can be opened within the range (grid style)
    - Exits when price breaks out of range or hits profit targets
    - Volatility filter to avoid trading during high volatility breakouts
    """
    
    def __init__(
        self,
        notional_per_level: float = 100.0,
        lookback_bars: int = 50,
        bb_period: int = 20,
        bb_std: float = 2.0,
        range_buffer_pct: float = 0.01,  # 1% buffer from exact range boundaries
        grid_levels: int = 3,  # Number of grid levels to trade
        profit_per_grid: float = 0.015,  # 1.5% profit target per grid level
        stop_loss_pct: float = 0.025,  # 2.5% stop loss (range breakout)
        max_volatility: float = 0.02,  # Max 2% volatility to trade (filter breakouts)
        min_range_size: float = 0.03,  # Minimum 3% range size to trade
        max_positions: int = 3,  # Maximum concurrent grid positions
        min_notional: float = 20.0,
        max_notional: float = 1000.0,
        round_to: float = 0.01,
    ):
        self.notional_per_level = notional_per_level
        self.lookback_bars = lookback_bars
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.range_buffer_pct = range_buffer_pct
        self.grid_levels = grid_levels
        self.profit_per_grid = profit_per_grid
        self.stop_loss_pct = stop_loss_pct
        self.max_volatility = max_volatility
        self.min_range_size = min_range_size
        self.max_positions = max_positions
        self.min_notional = min_notional
        self.max_notional = max_notional
        self.round_to = round_to
        
        # Track multiple grid positions
        self._grid_positions: List[dict] = []
    
    def compute_bollinger_bands(self, recent_closes: List[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """Compute Bollinger Bands (middle, upper, lower)."""
        data = list(recent_closes)[-self.bb_period:]
        if len(data) < self.bb_period:
            return None, None, None
        
        middle = sum(data) / len(data)
        variance = sum((x - middle) ** 2 for x in data) / len(data)
        std_dev = math.sqrt(variance)
        
        upper = middle + (self.bb_std * std_dev)
        lower = middle - (self.bb_std * std_dev)
        
        return middle, upper, lower
    
    def compute_range_bounds(self, recent_closes: List[float]) -> tuple[Optional[float], Optional[float]]:
        """Identify range support and resistance using recent highs/lows."""
        data = list(recent_closes)[-self.lookback_bars:]
        if len(data) < 10:
            return None, None
        
        resistance = max(data)
        support = min(data)
        
        return support, resistance
    
    def compute_volatility(self, recent_closes: List[float]) -> Optional[float]:
        """Compute recent volatility (standard deviation of returns)."""
        data = list(recent_closes)[-20:]
        if len(data) < 3:
            return None
        
        returns = []
        for i in range(1, len(data)):
            if data[i-1] == 0:
                continue
            returns.append((data[i] - data[i-1]) / data[i-1])
        
        if len(returns) < 2:
            return None
        
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        return math.sqrt(variance)
    
    def is_in_range(self, price: float, support: float, resistance: float) -> bool:
        """Check if price is within the defined range."""
        range_size = (resistance - support) / support
        return range_size >= self.min_range_size
    
    def get_grid_levels(self, support: float, resistance: float) -> List[tuple[float, float]]:
        """Calculate buy and sell levels for grid trading.
        
        Returns list of (buy_level, sell_level) tuples.
        """
        levels = []
        range_size = resistance - support
        step = range_size / (self.grid_levels + 1)
        
        for i in range(1, self.grid_levels + 1):
            buy_level = support + (step * i) - (support * self.range_buffer_pct)
            sell_level = buy_level * (1 + self.profit_per_grid)
            
            # Ensure sell level doesn't exceed resistance
            if sell_level < resistance * (1 - self.range_buffer_pct):
                levels.append((buy_level, sell_level))
        
        return levels
    
    def decide(
        self,
        price: float,
        recent_closes: List[float],
        funding_rate: Optional[float] = None,
        position=None,
        bars_held: int = 0,
    ) -> TradeDecision:
        """Make trading decision for range/grid strategy."""
        
        # Need sufficient history
        if len(recent_closes) < max(self.lookback_bars, self.bb_period):
            return TradeDecision(action="hold", reason="insufficient history")
        
        # Compute indicators
        support, resistance = self.compute_range_bounds(recent_closes)
        bb_mid, bb_upper, bb_lower = self.compute_bollinger_bands(recent_closes)
        volatility = self.compute_volatility(recent_closes)
        
        if support is None or resistance is None or bb_lower is None or bb_upper is None:
            return TradeDecision(action="hold", reason="indicators unavailable")
        
        # Volatility filter: avoid trading during high volatility (potential breakout)
        if volatility is not None and volatility > self.max_volatility:
            return TradeDecision(action="hold", reason=f"high volatility {volatility:.4f} - potential breakout")
        
        # Check if market is in a valid range
        if not self.is_in_range(price, support, resistance):
            return TradeDecision(action="hold", reason=f"range too narrow: {((resistance-support)/support*100):.2f}%")
        
        # If in position, manage exits
        if position is not None:
            entry_price = getattr(position, "entry_price", None)
            direction = getattr(position, "direction", None)
            
            if entry_price is None or direction is None:
                return TradeDecision(action="hold", reason="invalid position")
            
            # Calculate P&L
            if direction == "long":
                pct = (price - entry_price) / entry_price
                
                # Check for range breakout (stop loss)
                if price < support * (1 - self.range_buffer_pct):
                    return TradeDecision(action="exit", reason=f"range breakdown: price {price:.2f} < support {support:.2f}")
                
                # Take profit at grid level
                if pct >= self.profit_per_grid:
                    return TradeDecision(action="exit", reason=f"grid profit target hit: {pct*100:.2f}%")
                
            else:  # short
                pct = (entry_price - price) / entry_price
                
                # Check for range breakout (stop loss)
                if price > resistance * (1 + self.range_buffer_pct):
                    return TradeDecision(action="exit", reason=f"range breakout: price {price:.2f} > resistance {resistance:.2f}")
                
                # Take profit at grid level
                if pct >= self.profit_per_grid:
                    return TradeDecision(action="exit", reason=f"grid profit target hit: {pct*100:.2f}%")
            
            # Stop loss on excessive drawdown
            if pct <= -self.stop_loss_pct:
                return TradeDecision(action="exit", reason=f"stop loss: {pct*100:.2f}%")
            
            return TradeDecision(action="hold", reason=f"in position: {pct*100:.2f}%")
        
        # No position: look for entry opportunities
        grid_levels = self.get_grid_levels(support, resistance)
        
        if not grid_levels:
            return TradeDecision(action="hold", reason="no valid grid levels")
        
        # Check if price is near any buy level (lower part of range)
        for buy_level, sell_level in grid_levels:
            # Buy signal: price near lower band or support
            if price <= buy_level and price >= bb_lower * (1 - self.range_buffer_pct):
                size = self.notional_per_level
                size = max(self.min_notional, min(self.max_notional, size))
                
                if self.round_to and self.round_to > 0:
                    size = round(size / self.round_to) * self.round_to
                
                reason = f"buy at grid level: {buy_level:.2f}, target: {sell_level:.2f}, range: [{support:.2f}, {resistance:.2f}]"
                return TradeDecision(action="enter", direction="long", size=size, reason=reason)
        
        # Check if price is near resistance (short opportunity in range)
        if price >= bb_upper * (1 - self.range_buffer_pct) and price <= resistance * (1 + self.range_buffer_pct):
            size = self.notional_per_level
            size = max(self.min_notional, min(self.max_notional, size))
            
            if self.round_to and self.round_to > 0:
                size = round(size / self.round_to) * self.round_to
            
            reason = f"short at resistance: {resistance:.2f}, range: [{support:.2f}, {resistance:.2f}]"
            return TradeDecision(action="enter", direction="short", size=size, reason=reason)
        
        return TradeDecision(action="hold", reason=f"price {price:.2f} not at grid level, range: [{support:.2f}, {resistance:.2f}]")


__all__ = ["QuickScalpStrategy", "RangeGridStrategy", "TradeDecision"]
