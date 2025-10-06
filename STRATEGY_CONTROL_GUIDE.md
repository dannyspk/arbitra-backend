# Live Strategy Control Integration - Quick Start Guide

## ✅ What Was Added

### Frontend Strategy Control Panel

Added to `web/frontend/app/trading/page.tsx`:

1. **Strategy Type Selector**
   - 🐻 Bear (Short Bias) - Red button
   - 🐂 Bull (Long Bias) - Green button
   - Disabled when strategy is running

2. **Symbol Display**
   - Shows currently selected symbol from dropdown
   - Strategy will trade this symbol

3. **Start/Stop Buttons**
   - ▶️ Start Strategy (Green) - Starts live strategy
   - ⏹️ Stop Strategy (Red) - Stops running strategy
   - Auto-disables/enables based on state

4. **Status Messages**
   - Error alerts (red background)
   - Success confirmations (green background)
   - Strategy info (bear/bull parameters)

5. **Auto Status Check**
   - Polls strategy status every 5 seconds
   - Updates UI if strategy stops/crashes
   - Syncs symbol and mode from backend

## 🎮 How to Use

### Step 1: Select Symbol
In the Order Entry section, select a symbol from the dropdown (e.g., BTCUSDT, ALPINEUSDT)

### Step 2: Choose Strategy Type
Click either:
- **🐻 Bear** for short-bias strategy (good for downtrends)
- **🐂 Bull** for long-bias strategy (good for uptrends)

### Step 3: Start Strategy
Click **▶️ Start Strategy** button

The strategy will:
- Start monitoring 15-minute candles
- Generate signals based on price movements
- Execute trades (paper mode by default)
- Update dashboard in real-time

### Step 4: Monitor Dashboard
Watch the Live Strategy Dashboard below for:
- Strategy status (● LIVE / ○ STOPPED)
- Open positions with real-time P&L
- Recent signals (pending/executed/failed)
- Completed trades with profit/loss

### Step 5: Stop Strategy
Click **⏹️ Stop Strategy** when done

## 🔧 API Endpoints Used

```typescript
// Start strategy
POST /api/live-strategy/start
Body: { symbol: "BTCUSDT", mode: "bear" | "bull" }
Response: { started: true, message: "..." }

// Stop strategy
POST /api/live-strategy/stop
Response: { stopped: true, message: "..." }

// Check status
GET /api/live-strategy/status
Response: { running: true, symbol: "BTCUSDT", mode: "bear" }
```

## 📊 Example Workflow

### Bear Strategy Example
```
1. Select BTCUSDT from dropdown
2. Click "🐻 Bear (Short Bias)"
3. Click "▶️ Start Strategy"
4. Status shows: "✅ Strategy running on BTCUSDT in BEAR mode"
5. Dashboard updates every 2 seconds
6. Price drops 5% → Signal: "open_long" (oversold bounce)
7. Order executes → Position opens
8. Price bounces 2% → Position closes with profit
9. Trade appears in dashboard
```

### Bull Strategy Example
```
1. Select ETHUSDT from dropdown
2. Click "🐂 Bull (Long Bias)"
3. Click "▶️ Start Strategy"
4. Status shows: "✅ Strategy running on ETHUSDT in BULL mode"
5. Price drops 5% in 15m → Signal: "open_long" (buy the dip)
6. Order executes → Long position opens
7. Price recovers 2% → Take profit hit
8. Trade recorded with profit
```

## 🎨 UI Design

### Strategy Control Panel Layout
```
┌───────────────────────────────────────────┐
│ Live Strategy Control                      │
├───────────────────────────────────────────┤
│ Strategy Type                              │
│ [🐻 Bear (Short Bias)] [🐂 Bull (Long..)] │
│                                            │
│ Selected Symbol                            │
│ ┌─────────────────────────────────────┐   │
│ │ BTCUSDT                             │   │
│ └─────────────────────────────────────┘   │
│                                            │
│ ┌─────────────────────────────────────┐   │
│ │      ▶️ Start Strategy              │   │
│ └─────────────────────────────────────┘   │
│                                            │
│ ✅ Strategy running on BTCUSDT in BEAR    │
│                                            │
│ Bear Strategy: Short on quick pumps...    │
│ Bull Strategy: Long on quick dips...      │
│ Default Mode: Paper trading (set ARB...   │
└───────────────────────────────────────────┘
```

## 🚨 Safety Features

### Button States
- **Start button disabled when:**
  - No symbol selected
  - Strategy already running
  - Request in progress (shows "⏳ Starting...")

- **Stop button disabled when:**
  - Request in progress (shows "⏳ Stopping...")

### Auto Status Sync
- Checks backend every 5 seconds
- Updates UI if strategy crashes
- Prevents duplicate starts

### Error Handling
- Shows error messages in red alert box
- Doesn't change state on failed requests
- Retries status check automatically

## 🧪 Testing Commands

### Test Strategy Control via PowerShell

```powershell
# Start bear strategy on BTCUSDT
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/live-strategy/start' `
  -ContentType 'application/json' `
  -Body '{"symbol":"BTCUSDT","mode":"bear"}' | ConvertTo-Json

# Check status
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/live-strategy/status' | ConvertTo-Json

# Stop strategy
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/live-strategy/stop' | ConvertTo-Json

# View dashboard
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/dashboard' | ConvertTo-Json -Depth 6
```

## 📝 Strategy Parameters

### Bear Strategy (Default)
- **p15_thresh**: 5.0% (15-minute threshold)
- **p30_thresh**: 10.0% (30-minute threshold)
- **p60_thresh**: 12.0% (60-minute threshold)
- **sl_pct**: 1.0% (stop loss)
- **tp_pct**: 2.0% (take profit)
- **risk_pct**: 20% (position sizing)

**Signals:**
- LONG: Price down ≥5%, ≥10%, ≥12% (oversold bounce)
- SHORT: Price up ≥5% in 15m (quick pump fade)

### Bull Strategy (Default)
- **p15_thresh**: 7.0%
- **p30_thresh**: 12.0%
- **p60_thresh**: 15.0%
- **sl_pct**: 1.0%
- **tp_pct**: 2.0%
- **risk_pct**: 10% (position sizing)

**Signals:**
- SHORT: Price up ≥7%, ≥12%, ≥15% (overbought)
- LONG: Price down ≥5% in 15m (quick dip buy)

## 🔐 Environment Setup

### Required Environment Variables
```bash
# Binance Futures API credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_here

# Execution mode (paper = simulation, live = real orders)
ARB_LIVE_DEFAULT_EXEC_MODE=paper

# Allow real orders (for test-order endpoint)
ARB_ALLOW_LIVE_ORDERS=0
```

### Enable Live Trading
```bash
# Switch to live mode (DANGER: Real money!)
ARB_LIVE_DEFAULT_EXEC_MODE=live
```

## 🎯 Quick Start Checklist

- [ ] Backend server running (`python -m uvicorn src.arbitrage.web:app --reload`)
- [ ] Frontend running (`cd web/frontend && npm run dev`)
- [ ] Navigate to `http://localhost:3000/trading`
- [ ] Binance API keys configured (see above)
- [ ] Select a symbol from dropdown
- [ ] Choose Bear or Bull strategy
- [ ] Click "▶️ Start Strategy"
- [ ] Watch dashboard for live updates!

## 📈 What Happens Next

1. **Strategy Loop Starts** (every 15 seconds):
   - Fetches last 5 candles (15-minute intervals)
   - Calculates price changes (15m, 30m, 60m)
   - Checks signal conditions

2. **Signal Generated**:
   - Records signal in dashboard (pending)
   - Calculates position size (20% of USDT balance for bear, 10% for bull)
   - Sends order to CCXT

3. **Order Executes**:
   - Signal status → executed
   - Position opens in dashboard
   - Real-time P&L tracking starts

4. **Position Closes**:
   - Take profit (2%) or stop loss (1%) hit
   - Trade recorded with final P&L
   - Statistics updated (win rate, total P&L)

## 🆘 Troubleshooting

### "No symbol selected" error
→ Select a symbol from the Order Entry dropdown first

### Strategy won't start
→ Check backend logs for API key errors
→ Verify Binance API has Futures enabled
→ Check if symbol exists on Binance Futures

### Dashboard shows no data
→ Wait 15 seconds for first candle fetch
→ Check browser console for fetch errors
→ Verify backend is running on port 8000

### Positions not appearing
→ Check if order executed (Recent Signals status)
→ Verify CCXT order placement didn't fail
→ Check backend terminal for execution errors

## 🎉 You're Ready!

Your live strategy control panel is fully integrated! Navigate to the Trading page, select a symbol, pick a strategy type, and click Start Strategy to begin live trading monitoring.

The dashboard will update every 2 seconds with positions, signals, and trades!
