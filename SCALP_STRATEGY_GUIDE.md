# ⚡ Scalp Strategy Guide

## Overview

The **Scalp Strategy** is a high-frequency trading approach designed for quick entries and exits based on technical indicators. It's ideal for capturing small price movements in liquid markets with tight risk management.

---

## 🎯 Strategy Characteristics

### Timeframe
- **Primary**: 1-minute candles
- **Analysis Window**: 40+ bars (40 minutes of data)
- **Max Hold Time**: 60 minutes

### Risk/Reward Profile
- **Entry Threshold**: 0.8% deviation from 6-period SMA
- **Partial Target**: 0.45% profit (closes 50% of position)
- **Full Target**: 0.9% profit (closes entire position)
- **Stop Loss**: 1% loss (immediate exit)
- **Position Size**: 5% of account (volatility-adjusted)

---

## 📊 Technical Indicators Used

### 1. **Moving Averages**
- **SMA (6-period)**: Primary entry signal
- **Trend SMA (30-period)**: Longer-term trend filter

### 2. **Volatility**
- **Rolling Volatility (6-period)**: Adjusts position size
- Higher volatility = smaller position size
- Lower volatility = larger position size (up to max)

### 3. **Support/Resistance**
- **Pivot Points**: Local highs and lows within 20-bar window
- **ATR Bands**: Dynamic support/resistance levels
- Only enters near support (longs) or resistance (shorts)

### 4. **Momentum**
- **Short-term (6-period)**: Confirms entry direction
- **12h/24h momentum**: Filters against strong counter-trends

### 5. **Funding Rate** (Futures only)
- Nudges direction based on perpetual swap funding
- Positive funding → Short bias
- Negative funding → Long bias

---

## 🚀 How to Execute

### Option 1: Via Web UI (Recommended)

1. **Navigate to Trading Page**
   - Go to http://localhost:3000/trading

2. **Select a Symbol**
   - Use the searchable dropdown
   - Choose liquid pairs like BTCUSDT, ETHUSDT

3. **Choose Scalp Mode**
   - Click the **⚡ Scalp** button in Strategy Type section

4. **Start Strategy**
   - Click **Start Strategy** button
   - Strategy runs in paper trading mode by default
   - Check Live Strategy Dashboard for signals

5. **Monitor Execution**
   - Watch the Live Strategy Dashboard section
   - Signals appear in real-time
   - Position updates shown with entry price, P&L, and status

### Option 2: Via Python Code

```python
import asyncio
from arbitrage.live_strategy import LiveStrategy

async def run_scalp():
    strategy = LiveStrategy(
        symbol='BTCUSDT',
        mode='scalp',
        interval='1m'
    )
    await strategy.start()
    
    # Keep running
    try:
        await asyncio.sleep(3600)  # Run for 1 hour
    finally:
        await strategy.stop()

# Run it
asyncio.run(run_scalp())
```

### Option 3: Via Backend API

```bash
# Start scalp strategy
curl -X POST http://127.0.0.1:8000/api/live-strategy/start \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "mode": "scalp"}'

# Check status
curl http://127.0.0.1:8000/api/live-strategy/status

# Stop strategy
curl -X POST http://127.0.0.1:8000/api/live-strategy/stop
```

---

## 🎛️ Configuration Parameters

### Basic Parameters
```python
QuickScalpStrategy(
    notional_per_trade=100.0,    # Base position size in USDT
    sma_window=6,                # Short-term SMA window
    vol_window=6,                # Volatility calculation window
    entry_threshold=0.008,       # 0.8% deviation to enter
    exit_target=0.009,           # 0.9% profit to exit
    partial_target=0.0045,       # 0.45% for partial exit
    stop_loss=0.01,              # 1% stop loss
    max_holding_bars=60,         # Max 60 minutes hold
)
```

### Advanced Filters
```python
QuickScalpStrategy(
    # ... basic params ...
    trend_filter=True,           # Only trade with trend
    trend_window=30,             # Trend SMA window
    sr_lookback=20,              # Support/resistance lookback
    sr_threshold_pct=0.005,      # 0.5% near SR levels
    momentum_threshold=0.01,     # Momentum filter strength
    atr_multiplier=1.5,          # ATR band width
)
```

---

## 📈 Entry Logic

### Long Entry Conditions
✅ Price < SMA AND slope positive (mean reversion)
✅ Price near support level (within 0.5%)
✅ Positive short-term momentum
✅ Longer-term trend not strongly bearish
✅ Position size adjusted by volatility

### Short Entry Conditions
✅ Price > SMA AND slope negative (mean reversion)
✅ Price near resistance level (within 0.5%)
✅ Negative short-term momentum
✅ Longer-term trend not strongly bullish
✅ Position size adjusted by volatility

---

## 🚪 Exit Logic

### Profit Exits
1. **Partial Exit** (50% position):
   - When P&L reaches +0.45%
   - Locks in some profit, lets rest run

2. **Full Exit** (remaining position):
   - When P&L reaches +0.9%
   - Take full profit and close

### Loss Exit
- **Stop Loss**: -1% P&L
- Immediate full exit to limit loss

### Time-Based Exit
- **Max Hold**: 60 minutes (60 bars on 1m timeframe)
- Forces exit even if not at target/stop
- Prevents holding stale positions

---

## 💡 Best Practices

### 1. **Symbol Selection**
- ✅ Choose liquid pairs (BTC, ETH, major alts)
- ✅ Check 24h volume > $50M
- ❌ Avoid low-cap, illiquid tokens

### 2. **Market Conditions**
- ✅ Works best in ranging/choppy markets
- ✅ Mean reversion style benefits from oscillation
- ⚠️ Less effective in strong trending markets

### 3. **Risk Management**
- Start with 5% position sizing
- Max 3-5 concurrent positions
- Don't override stop losses
- Use paper trading first!

### 4. **Monitoring**
- Check Live Dashboard regularly
- Watch for repeated stop-outs
- Adjust parameters if needed

### 5. **Paper Trading First**
- **Always test in paper mode first**
- Strategy defaults to paper trading
- Set `ARB_LIVE_DEFAULT_EXEC_MODE=live` for real trades
- Monitor for at least 24 hours before going live

---

## 🔧 Troubleshooting

### Strategy Not Entering Trades
**Possible Causes:**
- Filters too strict (trend filter, momentum filter)
- Not enough price deviation from SMA
- Price not near support/resistance levels

**Solutions:**
- Lower `entry_threshold` to 0.006 (0.6%)
- Disable trend filter: `trend_filter=False`
- Increase `sr_threshold_pct` to 0.01 (1%)

### Too Many Stop-Outs
**Possible Causes:**
- High volatility
- Stop loss too tight
- Poor entry timing

**Solutions:**
- Increase `stop_loss` to 0.015 (1.5%)
- Let volatility scaling work (reduces size in high vol)
- Add momentum filter

### Positions Held Too Long
**Possible Causes:**
- Targets too far
- Time exit not triggering

**Solutions:**
- Lower `exit_target` to 0.007 (0.7%)
- Reduce `max_holding_bars` to 30 (30 minutes)

---

## 📊 Performance Metrics

### Expected Statistics (in suitable market conditions)
- **Win Rate**: 55-65%
- **Avg Win**: 0.6-0.9%
- **Avg Loss**: 0.8-1.0%
- **Risk/Reward**: ~1:1
- **Trades per Day**: 10-30 (depending on volatility)
- **Max Drawdown**: 3-5% (with proper sizing)

---

## ⚙️ Customization Examples

### Conservative Scalper (Tighter Risk)
```python
QuickScalpStrategy(
    notional_per_trade=50.0,     # Smaller size
    entry_threshold=0.010,       # Wait for larger deviation
    exit_target=0.006,           # Take profit early
    stop_loss=0.008,             # Tighter stop
    max_holding_bars=30,         # Exit faster
    trend_filter=True,           # Only with trend
)
```

### Aggressive Scalper (More Trades)
```python
QuickScalpStrategy(
    notional_per_trade=200.0,    # Larger size
    entry_threshold=0.005,       # Enter on small moves
    exit_target=0.012,           # Let winners run
    stop_loss=0.015,             # Wider stop
    max_holding_bars=90,         # Hold longer
    trend_filter=False,          # Trade both ways
)
```

---

## 🔒 Safety Features

1. **Paper Trading Default**: All strategies default to paper mode
2. **Position Limits**: Max notional capped at $1000 per trade
3. **Volatility Adjustment**: Auto-reduces size in high volatility
4. **Time Stops**: Forces exit after max hold time
5. **Funding Awareness**: Considers perpetual funding costs

---

## 📞 Support

For issues or questions:
1. Check the Live Dashboard for execution details
2. Review backend logs: `uvicorn.log`
3. Check strategy signals in Trading page
4. Verify symbol has sufficient liquidity

---

## ⚠️ Disclaimer

**This strategy is for educational purposes.**

- Past performance does not guarantee future results
- Always test thoroughly in paper mode first
- Start with small position sizes
- Never risk more than you can afford to lose
- Crypto markets are highly volatile
- Monitor your positions actively

---

**Happy Scalping! ⚡**
