# WebSocket Dashboard - Nothing Being Shown or Sent

## Root Cause
The WebSocket at `/ws/live-dashboard` requires `ARB_ALLOW_LIVE_ORDERS=1` to be set in the environment.

Your `.env` file **already has** `ARB_ALLOW_LIVE_ORDERS=1`, but the backend server hasn't loaded it yet because it was started before the env var was set.

## What's Happening

1. **Frontend** (page.tsx) → Uses `<LiveDashboard isLiveMode={!isTestMode} />`
2. **LiveDashboard component** → Calls `useLiveDashboardWebSocket()` hook
3. **WebSocket Hook** → Tries to connect to `ws://127.0.0.1:8000/ws/live-dashboard`
4. **Backend** (web.py line 6690) → **REJECTS** connection if `ARB_ALLOW_LIVE_ORDERS != 1`
5. **Result** → WebSocket closes immediately, no position data sent

## Quick Fix

### Option 1: Use the Helper Script (Recommended)
```powershell
.\restart_backend_with_live_ws.ps1
```

This script will:
- Load all variables from `.env`
- Set `ARB_ALLOW_LIVE_ORDERS=1`
- Restart the backend server
- Enable WebSocket connections

### Option 2: Manual Restart
```powershell
# Set the environment variable
$env:ARB_ALLOW_LIVE_ORDERS = "1"

# Restart backend
python -m uvicorn src.arbitrage.web:app --reload
```

## Verification

After restarting, open browser console (F12) and check for:

```
[WS] Connecting to: ws://127.0.0.1:8000/ws/live-dashboard
[WS] ✅ Connected to live dashboard WebSocket
[WS] Connected: Connected to Binance WebSocket
```

You should also see in the dashboard:
- ⚡ **"WebSocket Connected - Real-time updates active"** green banner
- Balance showing your live Binance balance
- Positions showing any open Binance Futures positions
- Real-time P&L updates

## What the WebSocket Shows

The `/ws/live-dashboard` WebSocket streams:
1. **Balance** - Live USDT balance from Binance
2. **Positions** - All open Binance Futures positions
3. **Orders** - Active orders
4. **P&L Updates** - Real-time profit/loss calculations

## Test vs Live Mode

The `isLiveMode` prop controls what data you see:
- **Test Mode** (purple badge) → Shows paper trading positions from local storage
- **Live Mode** (gray badge) → Shows actual Binance positions via WebSocket

## Still Not Working?

If WebSocket connects but shows no positions:
1. ✅ Check you actually have **open positions on Binance Futures**
2. ✅ Verify Binance API keys are set: `BINANCE_API_KEY`, `BINANCE_API_SECRET`
3. ✅ Make sure you're in **Live Mode** (toggle in top-right of Order Placement panel)
4. ✅ Check Python console for errors like "authentication failed"

## Backend Code Reference

The rejection happens here (`src/arbitrage/web.py` line 6690):
```python
live_enabled = os.environ.get('ARB_ALLOW_LIVE_ORDERS', '0').strip() == '1'

if not live_enabled:
    await websocket.send_json({
        'type': 'error',
        'message': 'Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1'
    })
    await websocket.close()
    return
```

## Environment Variables Needed

```bash
# Required for WebSocket to work
ARB_ALLOW_LIVE_ORDERS=1

# Required to fetch Binance positions
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
```

## Files Involved

- **Frontend WebSocket Hook**: `web/frontend/hooks/useLiveDashboardWebSocket.ts`
- **Frontend Component**: `web/frontend/components/LiveDashboard.tsx`
- **Backend WebSocket**: `src/arbitrage/web.py` (line 6669 - `@app.websocket("/ws/live-dashboard")`)
- **Environment Config**: `.env` file in root directory

---

**Summary**: Restart your backend server to load `ARB_ALLOW_LIVE_ORDERS=1` from the `.env` file, and the WebSocket will start streaming live Binance positions to your dashboard.
