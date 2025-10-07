# 🚀 Quick Start: Multiple Strategies

## ✅ Changes Made

### Backend (`src/arbitrage/web.py`)
✅ Multiple strategy support implemented
✅ Can run different strategies on different symbols simultaneously
✅ Each strategy operates independently

### Frontend (`web/frontend/app/trading/page.tsx`)
✅ UI shows all active strategies
✅ Individual stop buttons per strategy
✅ "Stop All" button
✅ Color-coded by mode

### PowerShell Script
✅ `start_multiple_strategies.ps1` - Interactive manager

---

## 🔄 RESTART REQUIRED

**The backend must be restarted to apply changes:**

```powershell
# Stop current backend (Ctrl+C in Python terminal)
# Then restart:
python -m uvicorn src.arbitrage.web:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🎯 How to Test

### Option 1: Use PowerShell Script (Recommended)
```powershell
.\start_multiple_strategies.ps1
```

Then select:
- **Option 9:** Quick Start (BTCUSDT Scalp + SOLUSDT Bear)
- **Option 6:** View active strategies

### Option 2: Manual API Calls
```powershell
# Start BTCUSDT Scalp
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/live-strategy/start" `
  -Method POST -ContentType "application/json" `
  -Body '{"symbol":"BTCUSDT","mode":"scalp","interval":"1m"}'

# Start SOLUSDT Bear
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/live-strategy/start" `
  -Method POST -ContentType "application/json" `
  -Body '{"symbol":"SOLUSDT","mode":"bear","interval":"1m"}'

# Check status
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/live-strategy/status"
```

### Option 3: Use UI
1. Navigate to http://localhost:3001/trading
2. Select **BTCUSDT** → Mode: **Scalp** → Click **Start**
3. Select **SOLUSDT** → Mode: **Bear** → Click **Start**
4. See both strategies in "Active Strategies" panel

---

## 📊 What You'll See

### In the UI:
```
[Active Strategies (2)]                    [Stop All]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[🟢 BTCUSDT] ⚡ SCALP (1m)                 [Stop]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[🟢 SOLUSDT] 🐻 BEAR (1m)                  [Stop]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### In the Dashboard:
```
Recent Signals
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Time       | Symbol   | Action      | Price
9:02:16 AM | BTCUSDT  | open_long   | $97,234.50
9:03:45 AM | SOLUSDT  | open_short  | $145.67
9:05:22 AM | BTCUSDT  | close_long  | $97,892.23
```

---

## 🎮 Strategy Modes Explained

### 🐻 Bear Mode (Counter-trend in bearish market)
- **Short Entry:** Price pumps +5%
- **Long Entry:** Price dumps -5%, -10%, -12%
- **Best for:** Falling coins with volatility
- **Example:** SOLUSDT during downtrend

### 🐂 Bull Mode (Trend-following in bullish market)
- **Long Entry:** Price dips -5%
- **Short Entry:** Price spikes +7%, +12%, +15%
- **Best for:** Rising coins with momentum
- **Example:** ETHUSDT during uptrend

### ⚡ Scalp Mode (Quick entries on SMA deviation)
- **Entry:** 1.2% deviation from 6-period SMA
- **Exit:** 2.5% profit target (1.5% partial)
- **Stop:** 1.5% loss
- **Max Hold:** 2 hours
- **Best for:** High liquidity pairs (BTC, ETH)

### 📊 Range Mode (Mean reversion in sideways market)
- **Entry:** Near Bollinger Bands, pivot points
- **Exit:** Opposite band or breakout
- **Best for:** Low volatility, ranging markets

---

## ⚠️ Important Notes

### ✅ Supported:
- ✅ BTCUSDT scalp + SOLUSDT bear (different symbols)
- ✅ ETHUSDT bull + ADAUSDT range (different symbols)
- ✅ Unlimited concurrent strategies (limited by resources)

### ❌ NOT Supported:
- ❌ BTCUSDT scalp + BTCUSDT bear (same symbol)
- Will return error: "strategy already running for BTCUSDT"

### Paper Trading:
- All strategies run in **paper mode** by default
- ARB_ALLOW_LIVE_EXECUTION=0 in .env
- No real money required
- Safe to test multiple strategies

---

## 🎯 Next Steps After Restart

1. **Restart backend** (required)
2. Run `.\start_multiple_strategies.ps1`
3. Select **Option 9** (Quick Start)
4. Navigate to Trading page: http://localhost:3001/trading
5. Watch "Active Strategies (2)" panel
6. Monitor "Recent Signals" for entries from both

**Both strategies will:**
- Poll independently every 15 seconds
- Generate signals when conditions met
- Display in shared dashboard
- Track separate positions
- Report combined P&L

---

## 📚 Documentation Files

- **MULTIPLE_STRATEGIES_GUIDE.md** - Complete technical guide
- **start_multiple_strategies.ps1** - Interactive manager
- **check_strategy_status.ps1** - Quick status check

---

🎉 **You can now run multiple strategies simultaneously on different coins!**
