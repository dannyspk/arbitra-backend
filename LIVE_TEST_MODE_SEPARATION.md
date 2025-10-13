# Live Mode vs Test Mode Separation

## Problem
The Live Dashboard was showing both test and live positions together, and live balance was appearing even in Test Mode.

## Solution
Complete separation of test and live trading data through:

### 1. **Position Tracking** (`live_dashboard.py`)
- Added `is_live: bool = False` field to `Position` class
- Updated `get_total_unrealized_pnl()` to filter by live/test
- Updated `calculate_net_balance()` to only include relevant positions

**Key Changes:**
```python
class Position:
    is_live: bool = False  # NEW: Differentiates live vs test positions

def get_total_unrealized_pnl(self, live_only: bool = False) -> float:
    # Only sum PNL from matching position type

def calculate_net_balance(self, wallet_balance: float, live_only: bool = True):
    # Only include PNL from live positions when calculating live balance
```

### 2. **Backend API** (`web.py`)
- When creating positions, set `is_live=allow_live`
- Dashboard endpoint filters positions based on `mode` parameter
- Balance calculation only uses relevant positions

**API Changes:**
```python
# Creating position
position = Position(
    ...
    is_live=allow_live  # NEW: Mark as live or test
)

# Dashboard endpoint
@app.get('/api/dashboard')
async def api_dashboard(mode: str = 'test'):
    # Filter positions by mode
    if mode == 'live':
        positions = [p for p in positions if p.is_live]
    else:
        positions = [p for p in positions if not p.is_live]
    
    # Only fetch Binance balance in live mode
    if mode == 'live' and live_enabled:
        net_info = dashboard.calculate_net_balance(wallet_balance, live_only=True)
```

### 3. **Frontend** (`LiveDashboard.tsx`, `trading/page.tsx`)
- Dashboard sends `mode=live` or `mode=test` query parameter
- Close position and adjust TP/SL use `isLiveMode` prop
- Dashboard title changes based on mode

**Frontend Changes:**
```typescript
// Pass mode to backend
const url = `${backend}/api/dashboard?mode=${isLiveMode ? 'live' : 'test'}`

// Close/adjust operations respect mode
allow_live: isLiveMode  // Only true in Live Mode

// Dynamic title
{isTestMode ? 'Test Trading Dashboard' : 'Live Strategy Dashboard'}
```

## Behavior

### Test Mode (Default)
- ✅ Shows test balance ($500 starting)
- ✅ Shows ONLY test positions (paper trading)
- ✅ Close/Adjust only affects test positions
- ✅ No real money involved
- ✅ PNL updates in real-time for test positions

### Live Mode (Toggle On)
- ✅ Shows live Binance Futures balance
- ✅ Shows ONLY live positions (real trades)
- ✅ Close/Adjust sends orders to Binance
- ✅ Real money and fees
- ✅ PNL updates in real-time for live positions
- ✅ TP/SL orders placed on Binance

## Data Isolation

| Feature | Test Mode | Live Mode |
|---------|-----------|-----------|
| **Positions** | Test positions only | Live positions only |
| **Balance** | $500 virtual | Binance Futures wallet |
| **PNL Calculation** | From test positions | From live positions |
| **Orders** | Simulated locally | Sent to Binance |
| **TP/SL** | Simulated | Actual orders on Binance |
| **Fees** | Not tracked | Tracked (0.04%) |

## Testing Steps

1. **Start in Test Mode:**
   - Open a test position
   - Verify it appears in Test Trading Dashboard
   - Verify balance shows $500

2. **Switch to Live Mode:**
   - Toggle to Live Mode
   - Verify test position disappears
   - Verify live balance shows Binance wallet
   - Open a live position (small amount!)
   - Verify it appears in Live Strategy Dashboard

3. **Switch Back to Test:**
   - Toggle back to Test Mode
   - Verify live position disappears
   - Verify test position reappears
   - Verify balance back to $500 (+ test PNL)

4. **Verify Separation:**
   - Test positions don't affect live balance
   - Live positions don't affect test balance
   - Each mode has independent position tracking

## Debug Logging

When backend is running, you'll see:
```
[DEBUG] Total positions: 2, mode=live
[DEBUG] Filtered to 1 live positions
[DEBUG] Updated BTCUSDT: price=$97500.00, PNL=$5.25
[DEBUG] Live balance: wallet=$50.00, unrealized=$5.25, realized=$0.00, fees=$0.0200
```

Or in test mode:
```
[DEBUG] Total positions: 2, mode=test
[DEBUG] Filtered to 1 test positions
[DEBUG] Updated ETHUSDT: price=$3500.00, PNL=$2.50
```

## Safety Features

- ✅ Test positions can never send orders to Binance
- ✅ Live positions require `ARB_ALLOW_LIVE_ORDERS=1`
- ✅ Clear visual distinction (purple for test, cyan for live)
- ✅ Confirmation modal before live orders
- ✅ Mode-specific dashboard titles

## Files Modified

1. `src/arbitrage/live_dashboard.py` - Position tracking with `is_live` flag
2. `src/arbitrage/web.py` - Filtering and balance calculation by mode
3. `web/frontend/components/LiveDashboard.tsx` - Mode-aware API calls
4. `web/frontend/app/trading/page.tsx` - Pass `isLiveMode` prop to dashboard

## Next Steps

After restarting backend:
1. Test both modes thoroughly
2. Verify positions don't cross-contaminate
3. Confirm TP/SL orders appear on Binance (live mode only)
4. Check real-time PNL updates work in both modes
