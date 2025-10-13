# WebSocket Connection Loop Issue

## Problem
The WebSocket connection keeps closing and reopening in a rapid loop:
```
[WS] WebSocket closed, stopping watcher
[WS] WebSocket closed while sending P&L for MYX/USDT:USDT
```

This prevents balance data from being sent to the frontend.

## Root Cause Analysis

### Symptoms
1. WebSocket connects successfully
2. Position data is imported and sent once
3. Ticker watcher starts
4. Connection immediately closes
5. Process repeats in a loop

### Possible Causes
1. **Multiple component instances** - LiveDashboard might be mounted multiple times
2. **Page navigation** - User might be navigating between tabs
3. **React Strict Mode** - Double mounting in development
4. **WebSocket timeout** - Connection timing out before data is sent
5. **Frontend reconnection logic** - Auto-reconnect might be too aggressive

## Immediate Fix Needed

### Backend Changes
- [x] Add better logging to track connection state
- [ ] Add cooldown period before stopping watchers
- [ ] Continue watching even if one send fails (don't stop all watchers)

### Frontend Changes
- [ ] Check if multiple LiveDashboard instances are mounted
- [ ] Add connection debouncing
- [ ] Log all WebSocket state changes
- [ ] Prevent auto-reconnect loop

## Current Workaround

The LiveManualTradingPanel IS receiving balance data correctly, which means:
- WebSocket CAN connect
- Balance data CAN be fetched
- The issue is specific to the LiveDashboard component or its lifecycle

## Next Steps

1. Check browser console for WebSocket connection/disconnection messages
2. Count how many times useLiveDashboardWebSocket() is being called
3. Check if LiveDashboard is being unmounted/remounted
4. Add a minimum connection duration before allowing reconnection
