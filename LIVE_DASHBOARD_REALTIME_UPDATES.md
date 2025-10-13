# Live Strategy Dashboard - Real-Time Updates

## Issue Fixed
The "Live Strategy Dashboard" was showing **Test Mode** data ($499.99 test balance) instead of **Live Mode** data, and unrealized PNL was not updating in real-time for live trades.

## What Changed

### Backend (`web.py`)

**Enhanced `/api/dashboard` endpoint:**

```python
@app.get('/api/dashboard')
async def api_dashboard():
    # ... update PNL for all positions with current prices ...
    
    # Get dashboard state
    state = dashboard.get_full_state()
    
    # NEW: Check if live trading is enabled
    live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'
    
    if live_enabled:
        # Fetch live Binance balance
        balance_info = await asyncio.to_thread(_get_binance_futures_balance)
        
        if balance_info.get('success'):
            # Calculate net balance with fees and PNL
            wallet_balance = balance_info.get('balance', 0.0)
            net_info = dashboard.calculate_net_balance(wallet_balance)
            
            # Replace test balance with live balance
            state['balance'] = {
                'current': net_info['net_balance'],
                'initial': wallet_balance,
                'pnl': net_info['unrealized_pnl'] + net_info['realized_pnl'],
                'pnl_pct': ...,
                'live': True,  # Flag indicating live mode
                'wallet_balance': wallet_balance,
                'unrealized_pnl': net_info['unrealized_pnl'],
                'realized_pnl': net_info['realized_pnl'],
                'total_fees_paid': net_info['total_fees_paid']
            }
    
    return state
```

**Key Changes:**
- ✅ Detects if `ARB_ALLOW_LIVE_ORDERS=1` is set
- ✅ Fetches real Binance Futures balance
- ✅ Calculates net balance including fees and PNL
- ✅ Returns `live: true` flag to frontend
- ✅ Includes wallet balance, unrealized PNL, realized PNL, and fees

### Frontend (`LiveDashboard.tsx`)

**Updated TypeScript Interface:**
```typescript
interface DashboardData {
  balance: {
    current: number
    initial: number
    pnl: number
    pnl_pct: number
    live?: boolean                  // NEW: Live mode flag
    wallet_balance?: number         // NEW: Binance wallet balance
    unrealized_pnl?: number         // NEW: PNL from open positions
    realized_pnl?: number           // NEW: PNL from closed trades
    total_fees_paid?: number        // NEW: All fees paid
  }
  // ... other fields ...
}
```

**Updated Balance Card:**
```tsx
<div className="text-xs text-slate-400 mb-1 uppercase tracking-wide flex items-center gap-2">
  {data.balance?.live ? (
    <>
      Live Balance
      <span className="px-1.5 py-0.5 bg-cyan-500/20 border border-cyan-500/30 rounded text-[10px] text-cyan-400 font-bold">REAL</span>
    </>
  ) : (
    'Test Balance'
  )}
</div>

<div className={`text-2xl font-bold ${(data.balance?.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
  ${data.balance?.current.toFixed(2) || '500.00'}
</div>

{data.balance?.live ? (
  <div className="text-xs text-slate-500 mt-1 space-y-0.5">
    {/* Show unrealized PNL if exists */}
    {data.balance.unrealized_pnl !== undefined && data.balance.unrealized_pnl !== 0 && (
      <div className={data.balance.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
        Unrealized: {data.balance.unrealized_pnl >= 0 ? '+' : ''}${data.balance.unrealized_pnl.toFixed(2)}
      </div>
    )}
    {/* Show fees if any were paid */}
    {data.balance.total_fees_paid !== undefined && data.balance.total_fees_paid > 0 && (
      <div className="text-orange-400">
        Fees: -${data.balance.total_fees_paid.toFixed(4)}
      </div>
    )}
  </div>
) : (
  <div className="text-xs text-slate-500 mt-1">
    {/* Test mode shows PNL percentage */}
    {(data.balance?.pnl || 0) >= 0 ? '+' : ''}${data.balance?.pnl.toFixed(2) || '0.00'} ({(data.balance?.pnl_pct || 0).toFixed(1)}%)
  </div>
)}
```

## How It Works Now

### Test Mode (ARB_ALLOW_LIVE_ORDERS=0)
```
┌─────────────────────────────────┐
│ TEST BALANCE                    │
│ $499.99                         │
│ -$0.01 (-0.0%)                  │
└─────────────────────────────────┘
```

### Live Mode (ARB_ALLOW_LIVE_ORDERS=1)
```
┌─────────────────────────────────┐
│ LIVE BALANCE [REAL]             │
│ $490.54                         │
│ Unrealized: +$2.45              │  ← From open positions (real-time)
│ Fees: -$0.082                   │  ← Total fees paid
└─────────────────────────────────┘
```

## Real-Time PNL Updates

### How Unrealized PNL Updates:

1. **Polling Interval**: Dashboard polls every **2 seconds**
2. **Backend Updates**: `/api/dashboard` fetches current market prices
3. **PNL Calculation**: 
   ```python
   for pos in positions:
       current_price = fetch_ticker_sync(pos.symbol, pos.market)
       pos.update_pnl(current_price)  # Recalculates unrealized PNL
   ```
4. **Frontend Display**: Shows updated unrealized PNL in green/red

### Example Real-Time Flow:

```
Time: 9:39:44 AM
BTC Price: $50,000
Position: LONG 0.01 BTC @ $49,500
Unrealized PNL: +$5.00 (green)

↓ (2 seconds later)

Time: 9:39:46 AM
BTC Price: $50,100
Position: LONG 0.01 BTC @ $49,500
Unrealized PNL: +$6.00 (green) ← UPDATED

↓ (2 seconds later)

Time: 9:39:48 AM
BTC Price: $49,800
Position: LONG 0.01 BTC @ $49,500
Unrealized PNL: +$3.00 (green) ← UPDATED
```

## Display Breakdown

### Live Balance Card Shows:

1. **Title**: "LIVE BALANCE [REAL]" badge (cyan)
2. **Main Value**: Net balance (wallet + unrealized PNL)
3. **Unrealized PNL**: 
   - Green if profitable (+$2.45)
   - Red if losing (-$1.20)
   - Only shows if positions are open
4. **Fees Paid**: Orange text showing total fees (-$0.082)

### Statistics Cards Show:

1. **Live Balance**: $490.54 (with unrealized PNL + fees)
2. **Total Trades**: Number of completed trades
3. **Win Rate**: Percentage of winning trades
4. **Realized P&L**: Profit/loss from closed trades
5. **Unrealized P&L**: Current P&L from open positions (updates every 2s)

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ BACKEND: /api/dashboard                                     │
│                                                              │
│ 1. Fetch all open positions                                 │
│ 2. For each position:                                       │
│    - Fetch current market price (Binance API)               │
│    - Calculate unrealized PNL                               │
│    - Update position object                                 │
│                                                              │
│ 3. Check if ARB_ALLOW_LIVE_ORDERS=1                        │
│ 4. If yes:                                                  │
│    - Fetch Binance Futures wallet balance                   │
│    - Calculate: wallet + unrealized PNL - fees              │
│    - Return live balance with 'live: true' flag             │
│ 5. If no:                                                   │
│    - Return test balance ($500 starting balance)            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND: LiveDashboard Component                           │
│                                                              │
│ 1. Polls every 2 seconds (setInterval 2000ms)              │
│ 2. Receives updated data from backend                       │
│ 3. Checks data.balance.live flag                           │
│ 4. If live=true:                                           │
│    - Shows "LIVE BALANCE [REAL]"                           │
│    - Shows wallet balance                                   │
│    - Shows unrealized PNL (green/red)                       │
│    - Shows fees paid (orange)                               │
│ 5. If live=false:                                          │
│    - Shows "TEST BALANCE"                                   │
│    - Shows test balance with PNL percentage                 │
└─────────────────────────────────────────────────────────────┘
```

## Testing

### Verify Live Mode is Working:

1. **Check environment variable:**
   ```bash
   echo $env:ARB_ALLOW_LIVE_ORDERS
   # Should output: 1
   ```

2. **Open Trading page**

3. **Look for "LIVE BALANCE [REAL]" badge:**
   - If you see this → Live mode active ✅
   - If you see "TEST BALANCE" → Test mode active

4. **Open a position and watch unrealized PNL:**
   - Should update every 2 seconds
   - Green if price moves in your favor
   - Red if price moves against you

### Verify Real-Time Updates:

1. Open a LONG position on a volatile symbol (e.g., BTC)
2. Watch the "Unrealized P&L" card
3. Should see the value change every 2 seconds as price moves
4. Compare with Binance app to verify accuracy

## Benefits

✅ **Unified Dashboard**: One view for both test and live trading
✅ **Real-Time Updates**: Unrealized PNL updates every 2 seconds
✅ **Accurate Balance**: Shows actual Binance wallet balance
✅ **Fee Transparency**: See total fees paid on all trades
✅ **Clear Mode Indicator**: "LIVE" badge vs "TEST" label
✅ **Color-Coded PNL**: Green for profit, red for loss
✅ **No Configuration Needed**: Automatically detects live mode

## Notes

- The dashboard automatically switches between test and live mode based on `ARB_ALLOW_LIVE_ORDERS`
- Unrealized PNL is calculated in real-time using current market prices from Binance
- Live balance includes: wallet balance + unrealized PNL
- Fees are tracked separately and displayed for transparency
- Position updates happen every 2 seconds via polling
- All monetary values are in USDT
