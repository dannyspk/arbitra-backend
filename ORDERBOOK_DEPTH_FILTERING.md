# Orderbook Depth Filtering for Arbitrage

## Problem
The arbitrage scanner was showing opportunities that couldn't actually be executed because there wasn't enough liquidity at the quoted prices. For example:
- Exchange A shows BTC at $100,000 (but only $10 available at that price)
- Exchange B shows BTC at $102,000 (but only $5 available at that price)
- Scanner showed 2% arbitrage opportunity, but you couldn't actually trade it

## Solution
Added orderbook depth checking that verifies **at least $50 of liquidity exists at the specific arbitrage prices**.

### Changes Made

**File: `src/arbitrage/web.py`**

1. **Updated `fetch_orderbook_depth()` function** (Line ~525):
   - Added `target_buy_price` parameter - checks asks at or below this price
   - Added `target_sell_price` parameter - checks bids at or above this price
   - Added 0.5% price tolerance to account for minor slippage
   - Only counts liquidity that can be filled at the quoted arbitrage prices

2. **Updated arbitrage scanner** (Line ~1296):
   - Passes the actual buy/sell prices to depth checker
   - For buy exchange: checks if asks have $50 at the cheap price
   - For sell exchange: checks if bids have $50 at the expensive price
   - Skips opportunities that don't meet liquidity requirements

### How It Works

**For BUY side (cheap exchange):**
- Checks orderbook asks (sell orders)
- Only counts asks at or below target price + 0.5%
- Must have at least $50 worth of liquidity
- Example: If target is $2.00, checks asks from $2.00 to $2.01

**For SELL side (expensive exchange):**
- Checks orderbook bids (buy orders)
- Only counts bids at or above target price - 0.5%
- Must have at least $50 worth of liquidity
- Example: If target is $2.08, checks bids from $2.08 down to $2.06

### Example

**Before:**
```
Exchange A: $2.00 (only $10 available)
Exchange B: $2.08 (only $15 available)
Result: Showed as opportunity ❌
```

**After:**
```
Exchange A: $2.00 (only $10 available)
Exchange B: $2.08 (only $15 available)
Result: Filtered out (insufficient liquidity) ✓
```

**Valid Opportunity:**
```
Exchange A: $2.00 ($150 available at this price)
Exchange B: $2.08 ($200 available at this price)
Result: Shows as executable opportunity ✓
```

### Impact

- **Fewer false opportunities** - Only shows trades that can actually be executed
- **Better execution rates** - $50 minimum ensures you can trade meaningful amounts
- **More accurate profitability** - Accounts for real market depth

### API Response

Each opportunity now includes:
```json
{
  "symbol": "BTCUSDT",
  "buy_exchange": "Binance",
  "buy_price": 100000,
  "buy_depth_usd": 150.00,  // ← Liquidity available at buy price
  "sell_exchange": "MEXC",
  "sell_price": 102000,
  "sell_depth_usd": 200.00,  // ← Liquidity available at sell price
  "has_sufficient_liquidity": true,
  "is_executable": true
}
```

### Testing

Run the test script to see the logic in action:
```powershell
python test_orderbook_depth.py
```

This will show:
- Live orderbook data from Binance
- How depth is calculated at specific price levels
- Whether $50 threshold is met

## Next Steps

Restart the backend to apply changes:
```powershell
# In the python3.12 terminal, press Ctrl+C
# Then restart with your dev command
```

The dashboard will now show only arbitrage opportunities with sufficient liquidity for execution.
