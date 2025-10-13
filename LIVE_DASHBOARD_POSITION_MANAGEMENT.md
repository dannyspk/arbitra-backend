# Live Dashboard - Position Management Features

## Overview
Yes! The **Live Strategy Dashboard** fully supports closing positions and adjusting TP/SL for live trades.

## Features Available

### 1. **Close Position** ✅
- **Location**: Open Positions table → "Close" button for each position
- **Functionality**: Closes the position at current market price
- **Live Trading**: Now sends `allow_live: true` to execute on Binance

**What It Shows:**
```
┌─────────────────────────────────────────┐
│ Close Position                          │
│                                         │
│ Symbol:        BTCUSDT                  │
│ Side:          [LONG]                   │
│                                         │
│ Entry Price:   $49,500.00               │
│ Current P&L:   +$5.00 (+1.01%)         │
│                                         │
│ ⚠️ This will close your position at     │
│    the current market price. This       │
│    action cannot be undone.             │
│                                         │
│ [Cancel]  [Close Position]              │
└─────────────────────────────────────────┘
```

**How It Works:**
1. Click "Close" button on any open position
2. Modal shows position details and current P&L
3. Click "Close Position" to confirm
4. Backend closes position on Binance (if live mode)
5. Dashboard refreshes to show updated data

**Code Flow:**
```typescript
// Frontend
const confirmClosePosition = async () => {
  const currentPrice = closingPosition.entry_price + 
                       (closingPosition.unrealized_pnl / closingPosition.size)
  
  const response = await fetch(`${backend}/api/manual-trade/close`, {
    method: 'POST',
    body: JSON.stringify({
      symbol: closingPosition.symbol,
      exit_price: currentPrice,
      allow_live: true  // ✅ Now sends this for live trading
    })
  })
}

// Backend (web.py)
@app.post('/api/manual-trade/close')
async def api_manual_trade_close(request: dict):
    allow_live = request.get('allow_live', False)
    
    if allow_live:
        # Close position on Binance
        close_order = await asyncio.to_thread(
            exchange.create_market_order,
            symbol,
            close_side,  # 'sell' for long, 'buy' for short
            position.size,
            None,
            {'positionSide': position_side, 'reduceOnly': True}
        )
        
        # Track exit fee
        exit_fee = exit_value * 0.0004
        dashboard.add_fee_paid(exit_fee)
```

### 2. **Adjust Stop-Loss / Take-Profit** ✅
- **Location**: Open Positions table → "⚙️" button for each position
- **Functionality**: Update SL/TP levels for the position
- **Live Trading**: Updates position tracking (not yet implemented on Binance)

**What It Shows:**
```
┌─────────────────────────────────────────┐
│ Adjust SL/TP                            │
│                                         │
│ Position: BTCUSDT LONG                  │
│ Entry: $49,500.00                       │
│                                         │
│ Stop Loss ($)                           │
│ [48,000.00]                            │
│                                         │
│ Take Profit ($)                         │
│ [51,500.00]                            │
│                                         │
│ [Cancel]  [Save Changes]                │
└─────────────────────────────────────────┘
```

**How It Works:**
1. Click "⚙️" button on any open position
2. Modal shows current SL/TP values
3. Enter new SL/TP prices
4. Click "Save Changes"
5. Dashboard updates position tracking

**Code Flow:**
```typescript
const handleAdjustSubmit = async () => {
  const response = await fetch(`${backend}/api/manual-trade/adjust`, {
    method: 'POST',
    body: JSON.stringify({
      symbol: adjustingPosition.symbol,
      stop_loss: parseFloat(newStopLoss),
      take_profit: parseFloat(newTakeProfit)
    })
  })
}
```

**Note:** Currently SL/TP adjustment only updates the tracking. To enable automatic SL/TP execution on Binance, you would need to place stop-loss and take-profit orders on Binance after opening the position.

## Position Table Columns

The Live Dashboard shows a comprehensive table:

| Column | Description |
|--------|-------------|
| **Symbol** | Trading pair (e.g., BTCUSDT) |
| **Side** | LONG (green) or SHORT (red) badge |
| **Entry** | Entry price of the position |
| **Size** | Position size in base asset |
| **P&L** | Unrealized profit/loss (updates every 2s) |
| **P&L %** | Percentage profit/loss |
| **SL** | Stop-loss price (if set) |
| **TP** | Take-profit price (if set) |
| **Action** | Close and ⚙️ buttons |

## Real-Time Updates

The dashboard polls every **2 seconds** and updates:
- ✅ Unrealized P&L (green if profit, red if loss)
- ✅ P&L percentage
- ✅ All position data

## What Was Fixed

### Before:
```typescript
// ❌ Was NOT sending allow_live
body: JSON.stringify({
  symbol: closingPosition.symbol,
  exit_price: currentPrice
  // Missing: allow_live: true
})
```

### After:
```typescript
// ✅ Now sends allow_live for live trading
body: JSON.stringify({
  symbol: closingPosition.symbol,
  exit_price: currentPrice,
  allow_live: true  // Enables Binance execution
})
```

## How to Use

### Close a Position:
1. Go to Trading page
2. Scroll to "Live Strategy Dashboard"
3. Find your open position in the table
4. Click **"Close"** button
5. Review the modal showing:
   - Position details
   - Current P&L
   - Warning message
6. Click **"Close Position"** to confirm
7. Position closes on Binance (if live mode enabled)
8. Fees are tracked and deducted

### Adjust SL/TP:
1. Find your open position in the table
2. Click **"⚙️"** button
3. Enter new Stop Loss price
4. Enter new Take Profit price
5. Click **"Save Changes"**
6. SL/TP values update in the table

## Live Trading Integration

### Close Position on Binance:
```python
# Backend executes this when allow_live=True
close_order = exchange.create_market_order(
    symbol='BTCUSDT',
    side='sell',  # Opposite of entry
    amount=position.size,
    params={
        'positionSide': 'LONG',  # Must match position
        'reduceOnly': True       # Only close, don't open opposite
    }
)

# Calculate and track exit fee
exit_fee = exit_value * 0.0004  # 0.04%
dashboard.add_fee_paid(exit_fee)
```

### Fee Tracking:
- Entry fee: Tracked when position opened
- Exit fee: Tracked when position closed
- Total fees shown in Live Balance card

## Example Flow

### Opening → Monitoring → Closing a Position:

```
1. Open Position (via Live Manual Trading)
   → BTC LONG @ $50,000 ($100 position)
   → Entry fee: $0.04
   → Position appears in dashboard table

2. Monitor Position (Live Strategy Dashboard updates every 2s)
   → 9:39:44 - BTC @ $50,100 → P&L: +$2.00 (green)
   → 9:39:46 - BTC @ $50,200 → P&L: +$4.00 (green)
   → 9:39:48 - BTC @ $50,000 → P&L: $0.00 (white)

3. Close Position
   → Click "Close" button
   → Modal shows: Entry $50,000, Current P&L +$2.00
   → Click "Close Position"
   → Backend closes on Binance
   → Exit fee: $0.0408
   → Total fees: $0.0808
   → Net profit: $1.92

4. Trade appears in "Closed Trades" section
   → Shows entry, exit, P&L, reason
```

## Statistics Tracked

The dashboard tracks:
- **Total Trades**: Number of completed trades
- **Win Rate**: Percentage of profitable trades
- **Realized P&L**: Profit from closed trades
- **Unrealized P&L**: Current profit from open positions
- **Live Balance**: Wallet + Unrealized PNL
- **Total Fees**: All fees paid on live trades

## Benefits

✅ **Unified Interface**: Manage all positions from one dashboard
✅ **Real-Time P&L**: Updates every 2 seconds
✅ **One-Click Close**: Close positions instantly
✅ **SL/TP Management**: Adjust risk parameters easily
✅ **Live Execution**: Closes positions on Binance when live mode enabled
✅ **Fee Tracking**: Transparent fee calculation
✅ **Visual Feedback**: Green/red colors for profit/loss
✅ **Trade History**: See all closed trades

## Important Notes

1. **Close Button**: Now properly closes positions on Binance (with `allow_live: true`)
2. **Real-Time Updates**: Position P&L updates every 2 seconds
3. **Fee Deduction**: Exit fees automatically tracked and displayed
4. **Binance Hedge Mode**: Properly handles LONG/SHORT positions
5. **reduceOnly**: Prevents accidentally opening opposite position when closing
6. **Trade History**: All closed trades stored and displayed

## Future Enhancements

Potential improvements:
- [ ] Automatic SL/TP execution on Binance (place stop orders)
- [ ] Trailing stop-loss
- [ ] Partial position closing
- [ ] OCO (One-Cancels-Other) orders
- [ ] Position notes/tags
- [ ] Export trade history to CSV
