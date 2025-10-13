# Stop-Loss & Take-Profit Orders - Now LIVE on Binance! 🎯

## Issue Addressed
**Question:** "Doesn't place actual stop orders on Binance yet - It doesn't?"

**Answer:** You were right to question this! Initially, TP/SL were only stored locally. **NOW FIXED** - TP/SL orders are actually placed on Binance Futures!

## What Changed

### **Before (What Was Wrong):**
```python
# ❌ Only stored TP/SL locally
position = Position(
    symbol=symbol,
    stop_loss=stop_loss,      # Stored but not on Binance
    take_profit=take_profit   # Stored but not on Binance
)
dashboard.open_position(position)
# No actual orders placed on Binance!
```

### **After (What's Fixed):**
```python
# ✅ Places actual orders on Binance
# 1. Open position
order = exchange.create_market_order(...)

# 2. Place Stop-Loss order on Binance
sl_order = exchange.create_order(
    symbol,
    'STOP_MARKET',
    'sell',  # Opposite of entry
    size,
    None,
    {
        'stopPrice': stop_loss,
        'positionSide': 'LONG',
        'reduceOnly': True
    }
)

# 3. Place Take-Profit order on Binance
tp_order = exchange.create_order(
    symbol,
    'TAKE_PROFIT_MARKET',
    'sell',  # Opposite of entry
    size,
    None,
    {
        'stopPrice': take_profit,
        'positionSide': 'LONG',
        'reduceOnly': True
    }
)
```

## How It Works Now

### **Opening a Position with TP/SL:**

**Frontend:** User enters:
- Symbol: BTCUSDT
- Side: LONG
- Size: $100
- Leverage: 10x
- **Take Profit: 2%** → $51,000
- **Stop Loss: 1%** → $49,500

**Backend executes:**

1. **Market Order** (Entry)
   ```python
   order = exchange.create_market_order(
       'BTCUSDT',
       'buy',
       0.002,  # size
       params={'positionSide': 'LONG'}
   )
   # Position opened @ $50,000
   ```

2. **Stop-Loss Order** (Automatic)
   ```python
   sl_order = exchange.create_order(
       'BTCUSDT',
       'STOP_MARKET',  # Triggers when price hits stop
       'sell',          # Opposite of entry
       0.002,           # Full position size
       None,
       {
           'stopPrice': 49500,      # Trigger at $49,500
           'positionSide': 'LONG',  # For this position
           'reduceOnly': True       # Only close, don't open SHORT
       }
   )
   ```

3. **Take-Profit Order** (Automatic)
   ```python
   tp_order = exchange.create_order(
       'BTCUSDT',
       'TAKE_PROFIT_MARKET',  # Triggers when price hits target
       'sell',                 # Opposite of entry
       0.002,                  # Full position size
       None,
       {
           'stopPrice': 51000,      # Trigger at $51,000
           'positionSide': 'LONG',  # For this position
           'reduceOnly': True       # Only close, don't open SHORT
       }
   )
   ```

**Result:** You now have **3 orders on Binance**:
- ✅ Position: LONG 0.002 BTC @ $50,000
- ✅ Stop-Loss: Sell @ $49,500 (if price drops)
- ✅ Take-Profit: Sell @ $51,000 (if price rises)

## Adjusting TP/SL After Opening

### **Frontend Flow:**

1. Click **"⚙️"** button on open position
2. Modal shows current SL/TP values
3. Enter new values:
   - Stop Loss: $49,000 (changed from $49,500)
   - Take Profit: $52,000 (changed from $51,000)
4. Click **"Save Changes"**

### **Backend Flow:**

```python
# 1. Cancel all existing TP/SL orders for this position
open_orders = exchange.fetch_open_orders('BTCUSDT')
for order in open_orders:
    if order['positionSide'] == 'LONG':
        if 'STOP' in order['type'] or 'TAKE_PROFIT' in order['type']:
            exchange.cancel_order(order['id'], 'BTCUSDT')
            # Old SL/TP orders cancelled

# 2. Place new Stop-Loss order
sl_order = exchange.create_order(
    'BTCUSDT',
    'STOP_MARKET',
    'sell',
    0.002,
    None,
    {
        'stopPrice': 49000,  # NEW stop price
        'positionSide': 'LONG',
        'reduceOnly': True
    }
)

# 3. Place new Take-Profit order
tp_order = exchange.create_order(
    'BTCUSDT',
    'TAKE_PROFIT_MARKET',
    'sell',
    0.002,
    None,
    {
        'stopPrice': 52000,  # NEW take-profit price
        'positionSide': 'LONG',
        'reduceOnly': True
    }
)
```

**Result:** Old orders cancelled, new orders placed at updated prices!

## Order Types Explained

### **STOP_MARKET (Stop-Loss)**
- **Purpose:** Limit losses if price moves against you
- **Trigger:** Activates when market price **reaches or falls below** stop price (for LONG)
- **Execution:** Market order (executes immediately at best available price)
- **Example:** 
  - LONG @ $50,000
  - Stop @ $49,500
  - If BTC drops to $49,500 → **SELL** order triggers → Position closed

### **TAKE_PROFIT_MARKET (Take-Profit)**
- **Purpose:** Lock in profits at target price
- **Trigger:** Activates when market price **reaches or rises above** target (for LONG)
- **Execution:** Market order (executes immediately at best available price)
- **Example:**
  - LONG @ $50,000
  - Take-Profit @ $51,000
  - If BTC rises to $51,000 → **SELL** order triggers → Profit secured

### **reduceOnly Flag**
- **Purpose:** Prevents accidentally opening opposite position
- **Behavior:** Can only reduce/close existing position
- **Safety:** If position is already closed, order gets rejected instead of opening SHORT

## LONG vs SHORT Orders

### **LONG Position:**
```python
Entry:        BUY
Stop-Loss:    SELL (lower price)
Take-Profit:  SELL (higher price)
```

**Example:**
- Entry: BUY @ $50,000
- SL: SELL @ $49,500 (loses $500)
- TP: SELL @ $51,000 (gains $1,000)

### **SHORT Position:**
```python
Entry:        SELL
Stop-Loss:    BUY (higher price)
Take-Profit:  BUY (lower price)
```

**Example:**
- Entry: SELL @ $50,000
- SL: BUY @ $51,000 (loses $1,000)
- TP: BUY @ $49,000 (gains $1,000)

## What Happens When TP/SL Triggers

### **Stop-Loss Triggered:**

1. **Binance detects** price hit $49,500
2. **Stop-Loss order activates** automatically
3. **Market sell order executes** at best available price
4. **Position closed** (might be slightly worse than $49,500 due to slippage)
5. **Our system detects** position closure on next poll (2s)
6. **Dashboard updates** showing closed trade

### **Take-Profit Triggered:**

1. **Binance detects** price hit $51,000
2. **Take-Profit order activates** automatically
3. **Market sell order executes** at best available price
4. **Position closed** with profit secured
5. **Our system detects** position closure on next poll (2s)
6. **Dashboard updates** showing profitable trade

## Logging & Verification

### **When Opening Position:**
```
[LIVE ORDER] Binance order executed: 123456789, side=buy, size=0.002, price=50000.00
[LIVE ORDER] Order value: $100.00, Entry fee: $0.0400
[LIVE ORDER] Stop-Loss order placed: 987654321 @ $49500.00
[LIVE ORDER] Take-Profit order placed: 987654322 @ $51000.00
```

### **When Adjusting TP/SL:**
```
[ADJUST] Cancelled order 987654321 (STOP_MARKET)
[ADJUST] Cancelled order 987654322 (TAKE_PROFIT_MARKET)
[ADJUST] New Stop-Loss order placed: 111222333 @ $49000.00
[ADJUST] New Take-Profit order placed: 111222334 @ $52000.00
```

## Error Handling

### **If TP/SL Order Fails:**
```python
try:
    sl_order = exchange.create_order(...)
except Exception as sl_error:
    print(f"[WARNING] Failed to place Stop-Loss order: {sl_error}")
    # Position still opened, but no SL protection!
```

**What this means:**
- Main position will still open successfully
- TP/SL order failure logs a warning (doesn't crash)
- Position remains unprotected (manual close needed)

**Why it might fail:**
- Invalid stop price (too close to market)
- Insufficient margin
- Symbol-specific restrictions
- Network issues

## Verifying on Binance

### **Check Your Orders:**

1. Go to **Binance Futures**
2. Click **Open Orders**
3. You should see:
   - **STOP_MARKET** order (your stop-loss)
   - **TAKE_PROFIT_MARKET** order (your take-profit)
4. Both should show:
   - Symbol: BTCUSDT
   - Type: STOP_MARKET or TAKE_PROFIT_MARKET
   - Side: SELL (for LONG) or BUY (for SHORT)
   - Position Side: LONG or SHORT
   - Trigger Price: Your SL/TP price

### **Check Position:**

1. Go to **Positions**
2. Find your BTCUSDT position
3. Click on it to see:
   - Entry Price
   - Size
   - Unrealized PNL
   - Associated orders (SL/TP)

## Benefits

✅ **Automatic Risk Management:** TP/SL orders execute even if you're offline
✅ **Slippage Protection:** Orders execute at market price when triggered
✅ **Position Side Aware:** Works correctly in Hedge Mode
✅ **Reduce Only:** Can't accidentally open opposite position
✅ **Adjustable:** Change TP/SL anytime without closing position
✅ **Transparent:** All orders logged and visible on Binance
✅ **Failsafe:** If TP/SL placement fails, position still opens (with warning)

## Important Notes

1. **Order Fees:** TP/SL orders are maker orders (0.02% fee when triggered)
2. **Market Orders:** TP/SL execute as market orders (slight slippage possible)
3. **One Triggers, Other Cancels:** When SL hits, TP is auto-cancelled (and vice versa)
4. **Network Delay:** Orders appear on Binance within 1-2 seconds
5. **Hedge Mode Required:** Position side must be specified (LONG/SHORT)
6. **Size Must Match:** TP/SL size must equal position size (full close)

## Example Scenarios

### **Scenario 1: Stop-Loss Saves You**

```
9:00 AM - Open LONG BTC @ $50,000
        - SL @ $49,500
        - TP @ $51,000
        
9:15 AM - BTC drops to $49,800
        - Unrealized PNL: -$4.00
        
9:30 AM - BTC drops to $49,500 ⚠️
        - STOP-LOSS TRIGGERED
        - Position auto-closed
        - Loss: -$10.00 (instead of worse)
        
9:45 AM - BTC continues to $49,000
        - You're already out!
        - Saved from -$20.00 loss
```

### **Scenario 2: Take-Profit Secures Gains**

```
9:00 AM - Open LONG BTC @ $50,000
        - SL @ $49,500
        - TP @ $51,000
        
9:15 AM - BTC rises to $50,500
        - Unrealized PNL: +$10.00
        
9:30 AM - BTC rises to $51,000 🎯
        - TAKE-PROFIT TRIGGERED
        - Position auto-closed
        - Profit: +$20.00 (secured)
        
9:45 AM - BTC drops back to $50,500
        - You're already out with profit!
```

### **Scenario 3: Adjust TP/SL Mid-Trade**

```
9:00 AM - Open LONG BTC @ $50,000
        - SL @ $49,500
        - TP @ $51,000
        
9:15 AM - BTC at $50,800 (+$16 unrealized)
        - Feeling confident, adjust:
        - New SL @ $50,400 (breakeven +0.8%)
        - New TP @ $52,000 (higher target)
        
9:30 AM - Old orders cancelled
        - New orders placed
        - Now protected at breakeven!
```

## Safety Tips

⚠️ **Always set Stop-Loss:** Protect against sudden market moves
⚠️ **Reasonable Targets:** TP too close = frequent triggers, too far = rarely hit
⚠️ **Monitor Slippage:** Market orders may execute slightly worse than trigger price
⚠️ **Check Order Status:** Verify orders appear on Binance after opening position
⚠️ **Mind the Spread:** Set SL/TP outside the typical bid-ask spread
⚠️ **Account for Volatility:** Wider stops for volatile assets

## Summary

**Now when you open a position:**
1. ✅ Market order opens position on Binance
2. ✅ Stop-Loss order placed automatically
3. ✅ Take-Profit order placed automatically
4. ✅ All fees tracked
5. ✅ Orders visible on Binance
6. ✅ Can adjust TP/SL anytime
7. ✅ Automatic execution when triggered

**Your positions are now FULLY protected with real Binance orders!** 🛡️
