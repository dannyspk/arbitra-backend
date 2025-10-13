# Breakout Scanner - Pattern-Based Early Detection

## Overview
The Breakout Scanner identifies coins breaking out of tight consolidation patterns with volume confirmation. This complements volume surge detection by focusing on price patterns rather than just volume spikes.

**Supports both LONG and SHORT positions** with directional filtering.

## Strategy
Detects coins that have been consolidating in a tight range and are now breaking out with momentum. These setups often lead to significant moves as compressed volatility expands.

- **BULLISH breakouts**: Price breaks ABOVE consolidation (long positions)
- **BEARISH breakouts**: Price breaks BELOW consolidation (short positions)

## Endpoint
```
GET /api/breakout-scanner
```

### Parameters
- `consolidation_hours` (default: 72) - Minimum hours in consolidation (3 days)
- `min_breakout_pct` (default: 2.0) - Minimum % move to confirm breakout
- `min_volume_increase` (default: 1.5) - Volume multiplier vs consolidation average
- `top_n` (default: 5) - Number of results to return
- `max_market_cap` (default: 500000000) - Maximum market cap filter ($500M for mid-low caps)
- `direction` (default: "both") - Filter by "bullish" (longs), "bearish" (shorts), or "both"

### Example Requests
```bash
# All breakouts
http://127.0.0.1:8000/api/breakout-scanner

# Long positions only
http://127.0.0.1:8000/api/breakout-scanner?direction=bullish

# Short positions only
http://127.0.0.1:8000/api/breakout-scanner?direction=bearish&max_market_cap=200000000
```

## Pattern Detection

### 1. Consolidation Analysis
- Analyzes minimum 72 hours of price action
- Calculates consolidation high, low, and range percentage
- Identifies pattern type based on tightness:
  - **Tight Squeeze**: < 5% range (highest probability)
  - **Consolidation**: 5-7% range
  - **Range**: > 7% range

### 2. Breakout Detection
- **Bullish Breakout**: Current price > consolidation high
- **Bearish Breakout**: Current price < consolidation low
- Measures breakout strength (percentage move beyond range)
- Tracks hours since breakout began (fresher = better)

### 3. Volume Confirmation
- Compares recent 24h volume vs consolidation period average
- Minimum 1.5x increase required
- Higher volume = stronger confirmation

## Confidence Scoring

Total score out of 100:
1. **Consolidation Tightness** (35 points max)
   - <5% range: 35 points (Tight Squeeze)
   - 5-7% range: 25 points (Consolidation)
   - >7% range: 15 points (Range)

2. **Breakout Strength** (30 points max)
   - >5% move: 30 points
   - 3-5% move: 20 points
   - 2-3% move: 10 points

3. **Volume Increase** (25 points max)
   - >3x volume: 25 points
   - 2-3x volume: 15 points
   - 1.5-2x volume: 5 points

4. **Freshness Bonus** (10 points max)
   - ≤2 hours: 10 points (Very fresh - best entry)
   - 2-6 hours: 5 points (Fresh - good entry)
   - >6 hours: 0 points (Aging)

### Signal Classification
- **VERY_STRONG**: >80% confidence
- **STRONG**: 65-80% confidence
- **MEDIUM**: 50-65% confidence
- **WEAK**: <50% confidence

## Market Cap Filtering
- Default: $500M maximum (focuses on mid-low cap coins)
- Fetches real-time market cap from CoinGecko API
- Color-coded display:
  - **Green**: <$100M (micro-cap, highest potential)
  - **Yellow**: $100M-$500M (small-mid cap)
  - **Gray**: >$500M or N/A

## Response Format
```json
{
  "success": true,
  "breakouts": [
    {
      "symbol": "BTCUSDT",
      "base": "BTC",
      "breakout_direction": "BULLISH",
      "breakout_strength": 3.25,
      "consolidation_range_pct": 4.2,
      "consolidation_high": 45500,
      "consolidation_low": 43700,
      "current_price": 46950,
      "volume_increase": 2.8,
      "hours_since_breakout": 2,
      "pattern_type": "Tight Squeeze",
      "confidence": 85.5,
      "signal": "VERY_STRONG",
      "volume_24h": 15000000,
      "market_cap": 450000000,
      "reason": "🚀 BULLISH breakout +3.25% from Tight Squeeze (4.2% range) with 2.8x volume surge - detected 2h ago"
    }
  ],
  "total_analyzed": 200,
  "total_breakouts": 12,
  "parameters": {
    "consolidation_hours": 72,
    "min_breakout_pct": 2.0,
    "min_volume_increase": 1.5,
    "max_market_cap": 500000000
  }
}
```

## UI Component

### Location
`web/frontend/components/BreakoutScanner.tsx`

### Features
- Auto-refresh every 3 minutes (toggle-able)
- **Direction filter buttons**:
  - **Both** (purple) - Shows all breakouts
  - **🚀 Longs** (green) - Only bullish breakouts (spot trading)
  - **📉 Shorts** (red) - Only bearish breakouts (futures/margin)
- Real-time breakout cards with:
  - Direction indicator (🚀 bullish / 📉 bearish)
  - Signal strength badge
  - Confidence bar with color coding
  - Pattern type display
  - Time since breakout (color-coded by freshness)
  - Market cap with color-coded risk levels
  - Consolidation range metrics
  - Human-readable reasoning

### Integration
Accessed via "💥 Breakouts" tab in HotCoinsPanel

## Direction Filtering

### Use Cases
- **Both** (default): Market scanning, finding all opportunities
- **Bullish only**: Spot traders, bull market conditions
- **Bearish only**: Futures traders, bear market conditions

See `BREAKOUT_LONG_SHORT_GUIDE.md` for detailed long/short trading strategies.

## Trading Strategy

### Entry Signals
1. **VERY_STRONG signals** (>80% confidence):
   - Tight squeeze (<5% range)
   - Strong breakout (>5% move)
   - High volume (>3x average)
   - Fresh (≤2h ago)
   - **Action**: Immediate entry or wait for minor pullback

2. **STRONG signals** (65-80% confidence):
   - Good consolidation pattern
   - Decent breakout strength
   - Volume confirmation present
   - **Action**: Enter on pullback to breakout level

### Best Practices
- **Timing**: FRESH breakouts (≤2h) have highest probability
- **Entry**: Wait for pullback to breakout level for best risk/reward
- **Confirmation**: Always verify volume increase
- **Pattern**: Tightest squeezes (<5% range) most reliable
- **Market Cap**: <$100M coins have highest volatility (risk/reward)

### Risk Management
- Set stop loss just below consolidation low (bullish) or above consolidation high (bearish)
- Target 2-3x the consolidation range as profit target
- Trail stops as price extends beyond pattern
- Avoid breakouts older than 6 hours (momentum often faded)

## Technical Implementation

### Data Flow
1. Fetch 24h ticker data from Binance (USDT pairs)
2. Filter for volume >$100k and exclude stablecoins/leveraged tokens
3. Fetch market cap data from CoinGecko
4. Apply market cap filter (default $500M max)
5. Analyze top 200 by volume
6. For each coin:
   - Fetch 1h klines (sufficient history)
   - Split into consolidation period + recent 24h
   - Calculate consolidation metrics
   - Detect breakout direction and strength
   - Confirm with volume
   - Calculate confidence score
7. Sort by confidence and return top N

### Performance Optimization
- Async/await for parallel API calls
- Batch CoinGecko requests (250 coins per batch)
- Rate limiting (0.5s delay between batches)
- Early termination after 50 results found
- Analyzes only top 200 by volume

### Error Handling
- Graceful fallback if CoinGecko fails (shows N/A for market cap)
- Individual coin failures don't break the scan
- Comprehensive logging for debugging
- HTTP timeout handling (30s)

## Comparison with Volume Surge Detection

| Feature | Breakout Scanner | Volume Surge |
|---------|-----------------|--------------|
| Focus | Price patterns | Volume spikes |
| Timeframe | 72h+ consolidation | 1h + 4h multi-frame |
| Entry Type | Pattern breakout | Volume explosion |
| Best For | Trend following | Early momentum |
| Risk Level | Medium (pattern confirmation) | Higher (pure volume) |
| Complementary | Yes - use together for strongest signals |

## Next Steps

### Recommended Additions
1. **Composite Score**: Combine breakout + volume surge signals
2. **Order Book Analysis**: Add depth confirmation
3. **Multi-Timeframe**: Analyze 4h breakouts for larger moves
4. **Historical Backtest**: Track success rate of signals
5. **Alerts**: Push notifications for VERY_STRONG signals

## Files Modified
- `src/arbitrage/api/social_sentiment.py` - Added `/api/breakout-scanner` endpoint
- `web/frontend/components/BreakoutScanner.tsx` - New UI component
- `web/frontend/components/HotCoinsPanel.tsx` - Added "💥 Breakouts" tab

## Created: October 10, 2025
