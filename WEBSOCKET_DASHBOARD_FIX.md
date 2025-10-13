# WebSocket Dashboard Not Showing Positions - FIX

## Problem
The WebSocket endpoint `/ws/live-dashboard` is not sending position data because:
- The environment variable `ARB_ALLOW_LIVE_ORDERS` is not being loaded by the backend
- Your `.env` file HAS `ARB_ALLOW_LIVE_ORDERS=1` but the server needs to be restarted

## Solution

### Step 1: Restart Backend Server

1. Stop your current Python backend (press Ctrl+C in the terminal where it's running)

2. Start it again with this command:
   ```powershell
   python -m uvicorn src.arbitrage.web:app --reload --host 0.0.0.0 --port 8000
   ```

   OR if you use a different command, make sure the .env file is loaded.

### Step 2: Verify Environment Variable

After restarting, check the server logs. You should see:
- ✅ `ARB_ALLOW_LIVE_ORDERS=1` loaded from environment

If you still don't see it, run this in PowerShell BEFORE starting the server:
```powershell
$env:ARB_ALLOW_LIVE_ORDERS = "1"
python -m uvicorn src.arbitrage.web:app --reload
```

### Step 3: Check WebSocket Connection

Open your browser console (F12) and look for:
- `[WS] Connecting to: ws://127.0.0.1:8000/ws/live-dashboard`
- `[WS] ✅ Connected to live dashboard WebSocket`
- `[WS] Connected: Connected to Binance WebSocket`

If you see this error instead:
- `Live trading is disabled. Set ARB_ALLOW_LIVE_ORDERS=1`

Then the environment variable is still not loaded. Try the manual export method above.

### Step 4: Verify Binance API Keys

The WebSocket also requires valid Binance API keys to fetch positions:
```
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_here
```

Check that these are in your `.env` file and restart the server.

## Alternative: Check Live Mode Toggle

In the Trading page, make sure:
1. The Test/Live Mode toggle is set to **Live Mode** (not purple "Test Mode")
2. The toggle should show as a gray button in the top-right of the Order Placement panel

## Quick Test

Run this PowerShell command to test if the WebSocket is accessible:
```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 8000
```

Should show `TcpTestSucceeded: True`

## Still Not Working?

If you're still seeing no positions:
1. Check you actually HAVE open positions on Binance Futures
2. The dashboard only shows LIVE positions (not test/paper positions)
3. Check browser console for WebSocket errors
4. Check Python backend logs for connection errors

## Expected Behavior

Once fixed, you should see:
- "WebSocket Connected - Real-time updates active" banner at top of dashboard
- Balance updating in real-time
- Positions showing with live P&L updates
- No need to refresh the page
