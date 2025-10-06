# Range/Grid Trading Strategy Guide

## Overview

The **Range/Grid Strategy** is designed for sideways markets where price oscillates within a defined range. It's ideal for low-volatility, mean-reverting conditions where the market is consolidating between support and resistance levels.

## How It Works

### Core Concept
- **Buy low, sell high** within a defined price range
- Places buy orders near support (lower band)
- Places sell orders near resistance (upper band)
- Multiple positions can be opened at different price levels (grid-style)
- Exits when price breaks out of the range or hits profit targets

### Key Indicators

1. **Bollinger Bands** (20-period, 2 std dev)
   - Identifies dynamic support/resistance
   - Upper band = resistance zone
   - Lower band = support zone

2. **Support/Resistance Detection**
   - Analyzes recent 50 bars to find range highs/lows
   - Requires minimum 3% range size to trade

3. **Volatility Filter**
   - Max 2% volatility threshold
   - Avoids trading during high volatility breakouts

### Entry Rules

**Long Entry (Buy):**
- Price near lower Bollinger Band
- Price at or below calculated grid buy level
- Within 1% of support level
- Volatility below threshold

**Short Entry (Sell):**
- Price near upper Bollinger Band
- Price at or above resistance level
- Within 1% of resistance level
- Volatility below threshold

### Exit Rules

**Take Profit:**
- 1.5% profit per grid level
- Long: Exit when price rises to sell level
- Short: Exit when price falls to buy level

**Stop Loss:**
- 2.5% stop loss on range breakout
- Long: Exit if price breaks below support
- Short: Exit if price breaks above resistance

## Strategy Parameters

### Default Configuration
```python
notional_per_level: $150      # Position size per grid level
lookback_bars: 50             # Bars to analyze for range
bb_period: 20                 # Bollinger Band period
bb_std: 2.0                   # BB standard deviations
range_buffer_pct: 1%          # Buffer from range edges
grid_levels: 3                # Number of grid levels
profit_per_grid: 1.5%         # Profit target per level
stop_loss_pct: 2.5%           # Stop loss on breakout
max_volatility: 2%            # Max vol to trade
min_range_size: 3%            # Min range size required
max_positions: 3              # Max concurrent positions
risk_pct: 6%                  # Position sizing (6% of equity)
```

### Time Frame
- **15-minute candles** for range detection
- Provides good balance between noise filtering and responsiveness

## When to Use Range Strategy

### ✅ Ideal Conditions
- **Sideways/Consolidating Markets**
  - Price trading in horizontal range
  - Clear support and resistance levels
  - Low trending momentum

- **Low Volatility Periods**
  - Stable price action
  - Narrow Bollinger Bands
  - Predictable oscillation

- **Mean-Reverting Assets**
  - Assets that bounce between levels
  - Strong support/resistance zones
  - Stable liquidity

### ❌ Avoid When
- **Strong Trending Markets**
  - Clear uptrend or downtrend
  - Breaking new highs/lows
  - Expanding Bollinger Bands

- **High Volatility**
  - Sharp price swings
  - Wide Bollinger Bands
  - News events/announcements

- **Narrow Ranges**
  - Range less than 3%
  - Insufficient profit potential
  - High risk/reward ratio

## Grid Trading Mechanics

### Grid Levels
The strategy divides the range into multiple levels:

```
Resistance ────────────────── Sell Zone (Short)
              ↓
Level 3 Buy ─────────────────┐
              ↓               │ 1.5% profit
Level 3 Sell ────────────────┘
              ↓
Level 2 Buy ─────────────────┐
              ↓               │ 1.5% profit
Level 2 Sell ────────────────┘
              ↓
Level 1 Buy ─────────────────┐
              ↓               │ 1.5% profit
Level 1 Sell ────────────────┘
              ↓
Support ──────────────────── Buy Zone (Long)
```

### Position Management
- **Max 3 concurrent positions** to limit exposure
- Each level trades independently
- Positions close individually at targets
- All positions close on range breakout

## Risk Management

### Position Sizing
- **6% of account equity** per position
- Calculated based on available balance
- Respects min ($20) and max ($1,500) limits

### Stop Loss Protection
- **2.5% stop loss** on range breakout
- Long positions stopped below support
- Short positions stopped above resistance
- Protects against false breakouts

### Profit Targets
- **1.5% profit per grid level**
- Net ~1.2% after fees (0.07% maker + 0.05% slippage)
- Multiple small wins accumulate over time

## Performance Optimization

### Grid Level Spacing
- Evenly distributed across range
- 1% buffer from exact support/resistance
- Prevents premature entries/exits

### Volatility Filtering
- Skips trades when volatility > 2%
- Avoids whipsaws during breakouts
- Preserves capital in uncertain conditions

### Range Validation
- Requires minimum 3% range size
- Ensures adequate profit potential
- Filters out noise/microranges

## Trading Example

### Scenario: BTC Ranging Between $50,000 - $51,500

**Range Setup:**
- Support: $50,000
- Resistance: $51,500
- Range Size: 3% ✅ (meets minimum)
- BB Upper: $51,400
- BB Lower: $50,100

**Grid Levels Calculated:**
- Level 1 Buy: $50,400 → Sell at $51,157 (1.5% profit)
- Level 2 Buy: $50,900 → Sell at $51,663 (1.5% profit)
- Level 3 Buy: $51,400 → Sell at $52,170 (1.5% profit)

**Trade Execution:**
1. Price drops to $50,400 → **Open Long** (Level 1)
2. Price rises to $51,157 → **Close Long** (+1.5%)
3. Price drops to $50,900 → **Open Long** (Level 2)
4. Price drops to $50,400 → **Open Long** (Level 1 again)
5. Both positions profit as price recovers
6. If price breaks below $49,750 (support - 2.5%) → **Close All** (Stop Loss)

**Result:** Multiple small profits from range oscillations

## Comparison with Other Strategies

| Feature | Range | Scalp | Bear | Bull |
|---------|-------|-------|------|------|
| **Market Type** | Sideways | Any | Bearish | Bullish |
| **Time Frame** | 15m | 1m | 15m | 15m |
| **Trade Frequency** | Medium | High | Low | Low |
| **Profit Target** | 1.5% | 2.5% | 2% | 2% |
| **Stop Loss** | 2.5% | 1.5% | 1% | 1% |
| **Hold Time** | Hours | Minutes | Hours | Hours |
| **Risk/Trade** | 6% | 8% | 20% | 10% |
| **Volatility Pref** | Low | Medium | High | High |

## Tips for Success

### 1. Identify Valid Ranges
- Look for at least 3-5 touches of support/resistance
- Prefer horizontal ranges over slanted
- Avoid recent breakout zones

### 2. Monitor Range Health
- Check Bollinger Band width
- Watch for narrowing bands (compression)
- Increasing volatility = potential breakout

### 3. Manage Position Exposure
- Don't force trades in unclear ranges
- Respect max position limits
- Scale down size in questionable setups

### 4. Exit on Breakouts
- Don't fight confirmed breakouts
- Accept stop losses quickly
- Switch to trend-following strategy if range breaks

### 5. Combine with Other Indicators
- Volume analysis (high volume on touches)
- RSI oscillations (oversold/overbought)
- Time of day patterns (avoid news events)

## Common Mistakes to Avoid

### ❌ Trading Fake Ranges
- **Problem:** Identifying range in trending market
- **Solution:** Wait for at least 20+ bars of consolidation

### ❌ Ignoring Volatility
- **Problem:** Trading during high volatility
- **Solution:** Respect the 2% volatility filter

### ❌ Too Tight Stop Loss
- **Problem:** Getting stopped out on normal oscillations
- **Solution:** Use 2.5% stop loss with 1% buffer

### ❌ Overtrading
- **Problem:** Opening too many positions
- **Solution:** Respect 3 position maximum

### ❌ Holding Through Breakouts
- **Problem:** Hoping range will hold
- **Solution:** Exit immediately on confirmed breakout

## Backtesting Results

*Note: Backtest with historical data before live trading*

### Expected Performance (Ideal Conditions)
- **Win Rate:** 65-75%
- **Average Win:** 1.2-1.5%
- **Average Loss:** 2.5%
- **Profit Factor:** 1.8-2.2
- **Max Drawdown:** 8-12%

### Best Asset Classes
- Major pairs with high liquidity (BTC, ETH)
- Stablecoins during accumulation
- Large-cap alts in consolidation

## Monitoring and Adjustments

### Key Metrics to Watch
- **Range Stability:** Support/resistance holding?
- **Volatility Trend:** Increasing or decreasing?
- **Grid Fill Rate:** How many levels executed?
- **Breakout Frequency:** False vs. real breakouts

### When to Pause Strategy
- Volatility consistently above 2%
- Multiple false range breakouts
- Market transitioning to trend
- News events upcoming

## Conclusion

The Range/Grid Strategy is a powerful tool for sideways markets, offering consistent small profits through mean reversion. Success requires:

1. **Patience** to wait for valid ranges
2. **Discipline** to respect stop losses
3. **Vigilance** to exit on breakouts
4. **Consistency** to let the edge play out over time

Use this strategy as part of a diversified approach, switching between strategies based on market conditions.

---

## Quick Reference

**Enable Range Strategy:**
1. Select symbol in Trading page
2. Choose "📊 Range" strategy mode
3. Click "▶️ Start Strategy"
4. Monitor for range-bound price action

**Strategy Status:** Check footer for "Range/Grid Strategy" indicator

**Live Monitoring:** Dashboard shows open positions and P&L in real-time
