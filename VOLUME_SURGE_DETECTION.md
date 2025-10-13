# 🔥 Volume Surge Detection - Early Mover Signals

## Overview

The Volume Surge Detection system identifies coins with **unusual volume activity BEFORE significant price movements** - a key early indicator that helps you catch big moves before retail traders notice.

## How It Works

### 🎯 Core Strategy

**Volume leads price.** Smart money accumulates before retail FOMO kicks in.

When you see:
- ✅ Volume spike 3-5x+ average
- ✅ Price still stable (< 5% change)
- ✅ Volume trend "accelerating"

→ **High probability a big move is coming!**

### 📊 Detection Algorithm

1. **Fetch Current Data**: Get 24h ticker data from Binance for all USDT pairs
2. **Historical Analysis**: For each coin, fetch 1-hour klines over 7 days (168 hours)
3. **Calculate Average**: Compute average hourly volume over the lookback period
4. **Compare Current**: Get the most recent complete 1-hour candle volume
5. **Surge Detection**: Flag when `current_volume / avg_volume >= 3.0x`
6. **Price Filter**: Only include coins where price change < 5% (catches early accumulation)
7. **Confidence Scoring**: Assign 0-100 confidence based on:
   - Surge magnitude (higher = better)
   - Volume trend (accelerating = bonus)
   - Price stability (lower move = higher confidence)

## API Endpoints

### `/api/volume-surges`

**Method**: GET

**Query Parameters**:
```
min_surge_multiplier: float = 3.0    # Minimum volume increase multiplier
max_price_change: float = 5.0        # Maximum price change % to filter already-pumped coins
lookback_hours: int = 168            # Hours for average calculation (default 7 days)
top_n: int = 20                      # Number of results to return
```

**Example Requests**:
```bash
# Default settings (3x surge, 5% max price change, 7 day lookback)
GET http://localhost:8000/api/volume-surges

# More aggressive (5x surge, 3% max price change)
GET http://localhost:8000/api/volume-surges?min_surge_multiplier=5.0&max_price_change=3.0

# Longer lookback (2 weeks)
GET http://localhost:8000/api/volume-surges?lookback_hours=336
```

**Response Format**:
```json
{
  "success": true,
  "surges": [
    {
      "symbol": "XYZUSDT",
      "base": "XYZ",
      "surge_multiplier": 5.2,
      "current_1h_volume": 850000,
      "avg_hourly_volume": 163000,
      "volume_24h": 12500000,
      "price_change_1h": 1.3,
      "price_change_24h": -2.1,
      "last_price": 0.0425,
      "volume_trend": "accelerating",
      "confidence": 87.5,
      "signal": "STRONG",
      "reason": "Strong 5.2x volume increase • price +1.3% (early move) • volume accelerating • HIGH CONFIDENCE"
    }
  ],
  "total_analyzed": 200,
  "total_surges": 8,
  "parameters": {
    "min_surge_multiplier": 3.0,
    "max_price_change": 5.0,
    "lookback_hours": 168
  }
}
```

## Signal Types

| Signal | Criteria | Meaning | Action |
|--------|----------|---------|--------|
| **STRONG** | 5x+ volume, 70%+ confidence | Very high probability big move coming | Watch closely, prepare to enter |
| **MEDIUM** | 4-5x volume, 50-70% confidence | Moderate opportunity | Monitor for confirmation |
| **WEAK** | 3-4x volume, <50% confidence | Early signal | Keep on watchlist |

## Volume Trends

- **accelerating** 📈: Recent 24h avg > older avg × 1.5 (momentum building)
- **stable** ➡️: Recent avg similar to older avg (steady interest)
- **declining** 📉: Recent avg < older avg (interest fading)

## UI Features

### Dashboard Tab: "🔥 Volume Surges"

Located in the Hot Coins Panel with:
- **Auto-refresh**: Every 2 minutes (configurable)
- **Manual refresh**: On-demand scanning
- **Visual indicators**: 
  - 🔥 STRONG signals (green)
  - ⚡ MEDIUM signals (yellow)
  - 📊 WEAK signals (gray)
- **Trend icons**: 📈 📉 ➡️
- **Confidence bars**: Visual progress bars (0-100%)

### Card Display Shows:
- Symbol with link to trading page
- Signal strength badge
- Detailed reason/explanation
- Volume metrics (surge multiplier, current, average)
- Price changes (1h, 24h)
- Confidence score with visual bar
- Volume trend indicator
- Additional details (expandable)

## Trading Strategy

### Entry Signals
1. **STRONG signal appears** with:
   - Surge multiplier > 5x
   - Price change < 3%
   - Volume trend = "accelerating"
   - Confidence > 75%

2. **Confirmation**:
   - Check order book for heavy bids
   - Look for support forming at current levels
   - Verify no bad news/fundamentals

### Position Management
- **Entry**: When volume surges but price stable
- **Stop Loss**: Below recent support (typically 5-8%)
- **Target 1**: First resistance or 10-15% gain
- **Target 2**: Second resistance or 25-40% gain
- **Exit**: When retail FOMO peaks (RSI > 80, high volume + high price change)

### Risk Management
- **Position size**: Smaller for WEAK signals, larger for STRONG
- **Max risk**: 2-3% of portfolio per position
- **Diversify**: Don't go all-in on one surge signal

## Performance Tips

### Best Times to Check
- **First hour of UTC day** (Asian market open)
- **13:30-14:30 UTC** (US market open)
- **High volatility periods** (news events, market dumps/pumps)

### False Positive Filters
The system already filters out:
- Stablecoins (USDT, USDC, BUSD, etc.)
- Leveraged tokens (3L, 3S, UP, DOWN)
- Coins that already pumped (> 5% in 1h)

### Combining Signals
For highest accuracy, combine Volume Surge with:
- **Social sentiment** (LunarCrush data when available)
- **Order book analysis** (heavy bid walls)
- **Technical indicators** (RSI, MACD, support/resistance)
- **Funding rates** (on futures markets)

## Technical Details

### Data Sources
- **Binance API**: Primary data source
  - `/api/v3/ticker/24hr` - Current tickers
  - `/api/v3/klines` - Historical 1h candles

### Calculations

**Surge Multiplier**:
```python
surge_multiplier = current_1h_volume / avg_hourly_volume
```

**Confidence Score**:
```python
confidence = min(100, (surge_multiplier / min_surge_multiplier) * 50)

# Bonuses/penalties
if volume_trend == "accelerating": confidence += 20
confidence -= abs(price_change_1h) * 2

confidence = max(0, min(100, confidence))
```

**Volume Trend**:
```python
recent_avg = avg(last_24_hours_volume)
older_avg = avg(previous_24_hours_volume)

if recent_avg > older_avg * 1.5: trend = "accelerating"
elif recent_avg > older_avg: trend = "stable"
else: trend = "declining"
```

## Limitations

1. **API Rate Limits**: Binance has rate limits - we scan top 200 by volume to stay within limits
2. **Data Lag**: 1h candles mean minimum 1 hour detection delay
3. **False Positives**: News events, whale movements can trigger false signals
4. **Market Conditions**: Works best in trending markets, less effective in ranging markets

## Future Enhancements

Planned features:
- [ ] Multi-exchange support (MEXC, Bitget, etc.)
- [ ] Shorter timeframes (5m, 15m candles)
- [ ] Order book depth analysis
- [ ] Social sentiment correlation
- [ ] Historical backtesting results
- [ ] Alert notifications (Telegram, email, push)
- [ ] ML-based confidence scoring

## Examples

### Example 1: Strong Signal
```
Symbol: AIXBT/USDT
Surge: 6.2x volume
Price Change (1h): +1.8%
Volume Trend: Accelerating
Confidence: 92%
Signal: STRONG

Action: High probability move - enter with tight stop
```

### Example 2: False Positive (Filtered Out)
```
Symbol: ABC/USDT
Surge: 4.5x volume
Price Change (1h): +12% ❌ (already pumped)
Signal: FILTERED OUT

Reason: Price already moved - missed the early entry
```

### Example 3: Weak Signal
```
Symbol: XYZ/USDT
Surge: 3.1x volume
Price Change (1h): +0.5%
Volume Trend: Declining
Confidence: 38%
Signal: WEAK

Action: Add to watchlist, wait for confirmation
```

## Support

For questions or issues:
- Check backend logs: Volume surge detection logs to console
- API endpoint: Test with `/api/volume-surges` directly
- Frontend: Check browser console for errors

## Credits

Developed as part of the Arbitrage Trading Platform
- Backend: FastAPI + httpx (async)
- Frontend: Next.js + React + TypeScript
- Data: Binance API (public endpoints)
