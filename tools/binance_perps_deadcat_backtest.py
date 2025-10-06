#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance Perps Backtest: Bearish Trend + Dead Cat Bounce Scalp (hybrid)
---------------------------------------------------------------------
- Exchange: Binance USDT-M Futures (linear perps)
- Timeframes: 1d (trend filter) + 15m (execution)
- Directional bias: Short-only in daily bear trend, optional long scalps on dead-cat bounces
- Risk model: fixed fractional risk per trade, ATR-based SL/TP
- Outputs: summary stats + trade log CSV

Usage examples:
---------------
# 1) Direct CCXT fetch (requires internet; run locally)
python binance_perps_deadcat_backtest.py --symbol BTC/USDT --since_days 180

# 2) Use local CSV klines (no internet). CSV must have: timestamp,open,high,low,close,volume (ms)
python binance_perps_deadcat_backtest.py --symbol BTC/USDT --csv_15m path/to/15m.csv --csv_1d path/to/1d.csv
"""
import argparse
import math
from dataclasses import dataclass
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd

# Optional: CCXT for live fetch
try:
    import ccxt
    CCXT_AVAILABLE = True
except Exception:
    CCXT_AVAILABLE = False


# ---------- Indicator helpers ----------
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).ewm(alpha=1/length, adjust=False).mean()
    roll_down = pd.Series(down, index=series.index).ewm(alpha=1/length, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    return 100 - (100 / (1 + rs))

def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return true_range(df).rolling(length).mean()

def slope(series: pd.Series, window: int = 3) -> pd.Series:
    return series.diff(window) / window

def local_minima(series: pd.Series, window: int = 5) -> pd.Series:
    return series[(series.shift(1) > series) & (series.shift(-1) > series)].rolling(window, center=True).apply(lambda x: x[window//2] == np.min(x), raw=False)

def local_maxima(series: pd.Series, window: int = 5) -> pd.Series:
    return series[(series.shift(1) < series) & (series.shift(-1) < series)].rolling(window, center=True).apply(lambda x: x[window//2] == np.max(x), raw=False)


# ---------- Data fetching ----------
def fetch_ohlcv_binance_usdm(symbol: str, timeframe: str, since_ms: Optional[int] = None, limit: int = 1500) -> pd.DataFrame:
    ex = ccxt.binanceusdm({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
    all_rows = []
    since = since_ms
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not batch:
            break
        all_rows += batch
        if len(batch) < limit:
            break
        since = batch[-1][0] + 1
    df = pd.DataFrame(all_rows, columns=['timestamp','open','high','low','close','volume'])
    for c in ['open','high','low','close','volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna().reset_index(drop=True)
    return df


# ---------- Strategy config ----------
@dataclass
class Config:
    symbol: str = "BTC/USDT"
    exec_tf: str = "15m"
    trend_tf: str = "1d"
    since_days: int = 180

    # Trend filter (1D)
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_bear_line: int = 50     # allow short entries when RSI pulls back above this in bear

    # Execution (15m) indicators
    rsi_len: int = 14
    atr_len: int = 14
    ema_entry_fast: int = 9
    ema_entry_mid: int = 20
    ema_entry_slow: int = 50

    # Short continuation params
    short_rsi_min: float = 50.0       # require RSI > this to short (pullback)
    short_cross_20: bool = True       # require cross below 20 EMA (rejection) for short
    short_tp_atr: float = 1.5
    short_sl_atr: float = 1.0

    # Dead-cat bounce scalp (optional long)
    enable_long_bounce: bool = True
    long_rsi_max_oversold: float = 25.0
    require_bullish_div: bool = True
    long_tp_atr: float = 1.2
    long_sl_atr: float = 0.8

    # Portfolio / execution
    initial_equity: float = 10000.0
    risk_per_trade: float = 0.01      # 1% risk
    fee_pct: float = 0.0005           # 5 bps per side
    one_position_at_a_time: bool = True
    cooldown_bars: int = 2            # bars to wait after exit

    # Data input (optional CSVs)
    csv_15m: Optional[str] = None
    csv_1d: Optional[str] = None


# ---------- Dead-cat bounce divergence detection ----------
def bullish_divergence(prices: pd.Series, rsi_series: pd.Series, lookback: int = 50) -> pd.Series:
    """Very simple divergence: consecutive local price lows down, RSI lows up."""
    # identify local minima
    price_min = (prices.shift(1) > prices) & (prices.shift(-1) > prices)
    rsi_min = (rsi_series.shift(1) > rsi_series) & (rsi_series.shift(-1) > rsi_series)

    div = pd.Series(False, index=prices.index)
    last_low_idx: Optional[int] = None
    last_low_price: Optional[float] = None
    last_low_rsi: Optional[float] = None

    for i in range(len(prices)):
        if price_min.iloc[i] and rsi_min.iloc[i]:
            if last_low_idx is not None and (i - last_low_idx) <= lookback:
                # price makes lower low AND RSI makes higher low
                if prices.iloc[i] < last_low_price and rsi_series.iloc[i] > last_low_rsi:
                    div.iloc[i] = True
            last_low_idx = i
            last_low_price = prices.iloc[i]
            last_low_rsi = rsi_series.iloc[i]
    return div.ffill().fillna(False)


# ---------- Backtest Engine ----------
@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry: float
    size: float
    sl: float
    tp: float
    exit_time: Optional[pd.Timestamp] = None
    exit: Optional[float] = None
    pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    reason: str = ""


def run_backtest(cfg: Config, df15: pd.DataFrame, df1d: pd.DataFrame) -> Tuple[pd.DataFrame, List[Trade], dict]:
    # Prepare time index
    df15 = df15.copy()
    df15['timestamp'] = pd.to_datetime(df15['timestamp'], unit='ms', utc=True)
    df15.set_index('timestamp', inplace=True)
    df15.sort_index(inplace=True)

    df1d = df1d.copy()
    df1d['timestamp'] = pd.to_datetime(df1d['timestamp'], unit='ms', utc=True)
    df1d.set_index('timestamp', inplace=True)
    df1d.sort_index(inplace=True)

    # Indicators on 1D
    d = df1d.copy()
    d['ema_fast'] = ema(d['close'], cfg.ema_fast)
    d['ema_mid'] = ema(d['close'], cfg.ema_mid)
    d['ema_slow'] = ema(d['close'], cfg.ema_slow)
    d['rsi'] = rsi(d['close'], 14)
    d['slope_fast'] = slope(d['ema_fast'], 1)
    # Bearish day definition
    d['bearish_day'] = (
        (d['ema_fast'] < d['ema_mid']) &
        (d['ema_mid'] < d['ema_slow']) &
        (d['close'] < d['ema_mid']) &
        (d['slope_fast'] < 0)
    )

    # Broadcast bearish flag down to 15m bars
    daily_flag = d['bearish_day'].reindex(df15.index, method='ffill')
    df15['bearish_day'] = daily_flag.fillna(False)

    # 15m indicators
    df15['ema9']  = ema(df15['close'], cfg.ema_entry_fast)
    df15['ema20'] = ema(df15['close'], cfg.ema_entry_mid)
    df15['ema50'] = ema(df15['close'], cfg.ema_entry_slow)
    df15['rsi']   = rsi(df15['close'], cfg.rsi_len)
    df15['atr']   = atr(df15, cfg.atr_len).fillna(method='bfill')  # seed early values

    # Divergence series for bounce longs
    if cfg.enable_long_bounce:
        df15['bull_div'] = bullish_divergence(df15['close'], df15['rsi'], lookback=80)
    else:
        df15['bull_div'] = False

    equity = cfg.initial_equity
    trades: List[Trade] = []
    in_position = False
    pos_side = None
    size = 0.0
    entry_price = 0.0
    sl = 0.0
    tp = 0.0
    entry_time = None
    cooldown = 0

    # Performance tracking
    equity_curve = []

    for ts, row in df15.iterrows():
        price = float(row['close'])
        atr_v = max(float(row['atr']), 1e-6)  # guard
        rsi_v = float(row['rsi']) if not math.isnan(row['rsi']) else 50.0

        if cooldown > 0:
            cooldown -= 1

        # Update open position
        if in_position:
            hit_tp = (pos_side == 'short' and price <= tp) or (pos_side == 'long' and price >= tp)
            hit_sl = (pos_side == 'short' and price >= sl) or (pos_side == 'long' and price <= sl)

            exit_reason = None
            exit_px = None

            if hit_tp and hit_sl:
                # If both in same bar, assume worst (SL first). Could refine with intrabar logic.
                hit_tp = False

            if hit_tp:
                exit_px = tp
                exit_reason = 'TP'
            elif hit_sl:
                exit_px = sl
                exit_reason = 'SL'
            else:
                # Optional time-based or RSI-based exit rules could be added here
                pass

            if exit_reason:
                fee_mult = (1 - cfg.fee_pct) if pos_side == 'long' else (1 + cfg.fee_pct)
                # PnL = size*(exit - entry) for long; for short it's size*(entry - exit)
                if pos_side == 'long':
                    gross = size * (exit_px - entry_price)
                else:
                    gross = size * (entry_price - exit_px)
                fees = (abs(size) * entry_price * cfg.fee_pct) + (abs(size) * exit_px * cfg.fee_pct)
                pnl = gross - fees
                equity += pnl
                # R multiple (risk in $ is |size| * |entry - sl|)
                risk_per_unit = abs(entry_price - sl)
                risk_dollars = abs(size) * risk_per_unit if risk_per_unit > 0 else np.nan
                r_mult = pnl / risk_dollars if risk_dollars and risk_dollars > 0 else np.nan

                trades.append(Trade(
                    side=pos_side, entry_time=entry_time, entry=entry_price, size=size,
                    sl=sl, tp=tp, exit_time=ts, exit=exit_px, pnl=pnl, r_multiple=r_mult,
                    reason=exit_reason
                ))
                in_position = False
                pos_side = None
                size = 0.0
                cooldown = cfg.cooldown_bars

        # Entry logic
        if not in_position and cooldown == 0 and row['bearish_day']:
            # SHORT continuation setup
            short_cond = True
            short_cond &= (row['close'] < row['ema50'])
            short_cond &= (rsi_v >= cfg.short_rsi_min)
            if cfg.short_cross_20:
                short_cond &= (df15['close'].shift(1).loc[ts] > df15['ema20'].shift(1).loc[ts]) and (price < row['ema20'])

            # LONG bounce scalp (optional)
            long_cond = False
            if cfg.enable_long_bounce:
                long_cond = (rsi_v < cfg.long_rsi_max_oversold)
                if cfg.require_bullish_div:
                    long_cond &= bool(row['bull_div'])
                long_cond &= (row['close'] > row['ema9'])  # momentum confirmation

            # Priority: shorts first; if both trigger, prefer short in a bear day
            if short_cond:
                pos_side = 'short'
                entry_price = price
                risk_per_unit = cfg.short_sl_atr * atr_v
                dollar_risk = equity * cfg.risk_per_trade
                size = max(dollar_risk / max(risk_per_unit, 1e-6), 0.0)
                sl = entry_price + cfg.short_sl_atr * atr_v
                tp = entry_price - cfg.short_tp_atr * atr_v
                in_position = True
                entry_time = ts

            elif long_cond:
                pos_side = 'long'
                entry_price = price
                risk_per_unit = cfg.long_sl_atr * atr_v
                dollar_risk = equity * cfg.risk_per_trade
                size = max(dollar_risk / max(risk_per_unit, 1e-6), 0.0)
                sl = entry_price - cfg.long_sl_atr * atr_v
                tp = entry_price + cfg.long_tp_atr * atr_v
                in_position = True
                entry_time = ts

        equity_curve.append((ts, equity))

    # If position still open at the end, close at last price
    if in_position:
        last_ts = df15.index[-1]
        last_px = float(df15['close'].iloc[-1])
        if pos_side == 'long':
            gross = size * (last_px - entry_price)
        else:
            gross = size * (entry_price - last_px)
        fees = (abs(size) * entry_price * cfg.fee_pct) + (abs(size) * last_px * cfg.fee_pct)
        pnl = gross - fees
        equity += pnl
        risk_per_unit = abs(entry_price - sl)
        risk_dollars = abs(size) * risk_per_unit if risk_per_unit > 0 else np.nan
        r_mult = pnl / risk_dollars if risk_dollars and risk_dollars > 0 else np.nan

        trades.append(Trade(
            side=pos_side, entry_time=entry_time, entry=entry_price, size=size,
            sl=sl, tp=tp, exit_time=last_ts, exit=last_px, pnl=pnl, r_multiple=r_mult,
            reason='EOD'
        ))

    # Build outputs
    eq_df = pd.DataFrame(equity_curve, columns=['timestamp', 'equity']).set_index('timestamp')
    trades_df = pd.DataFrame([t.__dict__ for t in trades])
    trades_df = trades_df[['side','entry_time','entry','size','sl','tp','exit_time','exit','pnl','r_multiple','reason']]

    # Metrics
    pnl_series = trades_df['pnl'].fillna(0.0)
    wins = (pnl_series > 0).sum()
    losses = (pnl_series < 0).sum()
    win_rate = wins / max(wins+losses, 1)
    pf = pnl_series[pnl_series > 0].sum() / abs(pnl_series[pnl_series < 0].sum()) if (pnl_series[pnl_series < 0].sum()) != 0 else np.nan

    # 15m bars per day ~ 96; convert to daily returns for Sharpe
    eq_ret = eq_df['equity'].pct_change().fillna(0.0)
    # aggregate to daily
    daily_ret = eq_ret.resample('1D').apply(lambda x: (1+x).prod()-1).dropna()
    sharpe = daily_ret.mean()/ (daily_ret.std()+1e-12) * math.sqrt(252) if len(daily_ret) > 2 else np.nan
    max_dd = ((eq_df['equity'].cummax() - eq_df['equity']) / eq_df['equity'].cummax()).max()

    summary = {
        'symbol': cfg.symbol,
        'bars': len(df15),
        'trades': len(trades_df),
        'wins': int(wins),
        'losses': int(losses),
        'win_rate': round(float(win_rate), 4),
        'profit_factor': round(float(pf), 3) if not math.isnan(pf) else None,
        'final_equity': round(float(eq_df['equity'].iloc[-1]), 2),
        'return_pct': round(100*(eq_df['equity'].iloc[-1]/cfg.initial_equity-1), 2),
        'sharpe_daily': round(float(sharpe), 3) if not math.isnan(sharpe) else None,
        'max_drawdown_pct': round(100*float(max_dd), 2) if not math.isnan(max_dd) else None
    }

    return eq_df, trades_df, summary


# ---------- CLI & IO ----------
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Flexible columns; require timestamp(ms) and ohlcv
    cols = {c.lower(): c for c in df.columns}
    req = ['timestamp','open','high','low','close','volume']
    for r in req:
        if r not in [c.lower() for c in df.columns]:
            raise ValueError(f"CSV missing column: {r}")
    df = df[[cols['timestamp'], cols['open'], cols['high'], cols['low'], cols['close'], cols['volume']]]
    df.columns = ['timestamp','open','high','low','close','volume']
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default='BTC/USDT', type=str)
    ap.add_argument('--exec_tf', default='15m', type=str)
    ap.add_argument('--trend_tf', default='1d', type=str)
    ap.add_argument('--since_days', default=180, type=int)

    ap.add_argument('--csv_15m', default=None, type=str)
    ap.add_argument('--csv_1d', default=None, type=str)

    ap.add_argument('--disable_long_bounce', action='store_true')
    ap.add_argument('--risk_per_trade', default=0.01, type=float)
    ap.add_argument('--fee_bps', default=5, type=float)

    args = ap.parse_args()

    cfg = Config(
        symbol=args.symbol,
        exec_tf=args.exec_tf,
        trend_tf=args.trend_tf,
        since_days=args.since_days,
        enable_long_bounce=not args.disable_long_bounce,
        risk_per_trade=args.risk_per_trade,
        fee_pct=args.fee_bps / 10000.0,
        csv_15m=args.csv_15m,
        csv_1d=args.csv_1d
    )

    # Load data
    if cfg.csv_15m and cfg.csv_1d:
        df15 = load_csv(cfg.csv_15m)
        df1d = load_csv(cfg.csv_1d)
    else:
        if not CCXT_AVAILABLE:
            raise SystemExit("ccxt not installed and no CSVs provided. Install ccxt or pass --csv_15m/--csv_1d.")
        ex = ccxt.binanceusdm()
        now_ms = ex.milliseconds()
        since_ms_1d = now_ms - cfg.since_days * 24 * 60 * 60 * 1000
        since_ms_15m = since_ms_1d  # cover same span
        df1d = fetch_ohlcv_binance_usdm(cfg.symbol, cfg.trend_tf, since_ms_1d)
        df15 = fetch_ohlcv_binance_usdm(cfg.symbol, cfg.exec_tf, since_ms_15m)

    eq_df, trades_df, summary = run_backtest(cfg, df15, df1d)

    # Save outputs
    base = cfg.symbol.replace('/','_')
    trades_path = f"{base}_deadcat_trades.csv"
    equity_path = f"{base}_deadcat_equity.csv"
    trades_df.to_csv(trades_path, index=False)
    eq_df.to_csv(equity_path)

    # Print summary
    print("==== Backtest Summary ====")
    for k, v in summary.items():
        print(f"{k:>18}: {v}")
    print(f"\nSaved trade log -> {trades_path}")
    print(f"Saved equity curve -> {equity_path}")


if __name__ == '__main__':
    main()
