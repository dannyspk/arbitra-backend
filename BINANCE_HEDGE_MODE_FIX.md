# Binance Futures Hedge Mode Fix

## Issue
```
[ERROR] Failed to execute live order on Binance: binance {"code":-4061,"msg":"Order's position side does not match user's setting."}
```

## Root Cause
Binance Futures account is set to **Hedge Mode**, which allows simultaneous long and short positions on the same symbol. In Hedge Mode, you MUST specify the `positionSide` parameter:
- `positionSide: 'LONG'` - For opening/closing long positions
- `positionSide: 'SHORT'` - For opening/closing short positions

## What Was Fixed

### 1. Opening Positions (Lines 3006-3026 in web.py)
**Before:**
```python
order = await asyncio.to_thread(
    exchange.create_market_order,
    symbol,
    order_side,
    size
)
```

**After:**
```python
order_side = 'buy' if side == 'long' else 'sell'
position_side = 'LONG' if side == 'long' else 'SHORT'

order_params = {
    'positionSide': position_side  # Required for Hedge Mode
}

order = await asyncio.to_thread(
    exchange.create_market_order,
    symbol,
    order_side,
    size,
    None,  # price (None for market orders)
    order_params
)
```

### 2. Closing Positions (Lines 3096-3131 in web.py)
**Added complete Binance close logic:**
```python
# Close position by placing opposite order
close_side = 'sell' if position.side == 'long' else 'buy'
position_side = 'LONG' if position.side == 'long' else 'SHORT'

order_params = {
    'positionSide': position_side,  # Must match position we're closing
    'reduceOnly': True  # Ensures we only close, not open opposite
}

close_order = await asyncio.to_thread(
    exchange.create_market_order,
    symbol,
    close_side,
    position.size,
    None,
    order_params
)
```

## How It Works Now

### Opening a LONG Position
- `order_side = 'buy'` (we're buying the asset)
- `positionSide = 'LONG'` (opening a long position)
- Binance knows this is for the LONG side in Hedge Mode

### Opening a SHORT Position
- `order_side = 'sell'` (we're selling/shorting the asset)
- `positionSide = 'SHORT'` (opening a short position)
- Binance knows this is for the SHORT side in Hedge Mode

### Closing a LONG Position
- `order_side = 'sell'` (selling to close the long)
- `positionSide = 'LONG'` (closing the LONG side position)
- `reduceOnly = True` (prevents opening a new SHORT position)

### Closing a SHORT Position
- `order_side = 'buy'` (buying to close the short)
- `positionSide = 'SHORT'` (closing the SHORT side position)
- `reduceOnly = True` (prevents opening a new LONG position)

## Binance Position Modes

### One-Way Mode (Default for most users)
- Can only have ONE position per symbol (either long OR short)
- Don't need to specify `positionSide`
- Simpler for beginners

### Hedge Mode (Your Current Setting)
- Can have BOTH long AND short positions simultaneously
- MUST specify `positionSide` parameter
- More advanced, allows hedging strategies

## How to Check Your Mode
1. Go to Binance Futures
2. Top right corner → Click your profile
3. Look for "Position Mode"
   - **One-Way Mode**: Simple (no positionSide needed)
   - **Hedge Mode**: Advanced (positionSide required) ← You're here

## Testing
Try placing a small order now. It should work with the positionSide parameter!

**Example order flow:**
1. Click "LONG" on BTC/USDT
2. Confirm the order
3. Backend sends: `buy` order with `positionSide: 'LONG'`
4. ✅ Order executes successfully on Binance Futures

## Additional Safety Features
- **Type validation**: All prices/sizes converted to proper types
- **Error handling**: Clear error messages if Binance rejects order
- **reduceOnly flag**: Prevents accidentally opening opposite position when closing
- **Logging**: All live orders logged with order ID and details
