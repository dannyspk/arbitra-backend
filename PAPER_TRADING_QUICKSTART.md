# Paper Trading - Quick Start Summary

## ✅ What's Working:
- ✅ Binance API keys configured
- ✅ Backend can start (`python -m uvicorn src.arbitrage.web:app --reload`)
- ✅ Frontend Trading page accessible
- ✅ Strategy start endpoint working (received 200 OK)
- ✅ Paper trading mode enabled (ARB_ALLOW_LIVE_EXECUTION=0)

## ⚠️  Current Issue:
The backend keeps shutting down after starting the strategy. This might be due to:
1. An error in the live_strategy.py execution
2. Missing dependencies for the strategy runner
3. The strategy thread crashing

## 🔧 To Fix and Test:

### Step 1: Keep Backend Running
```powershell
# Start backend in foreground to see all errors
cd C:\arbitrage
python -m uvicorn src.arbitrage.web:app --host 0.0.0.0 --port 8000 --reload
```

Keep this terminal open and watch for errors.

### Step 2: In Browser
1. Open: `http://localhost:3001/trading` (or port 3000)
2. Press **Ctrl+Shift+R** to hard refresh
3. If "Stop Strategy" button is showing, click it first
4. Select a symbol: **BTCUSDT**
5. Click strategy mode: **⚡ Scalp**
6. Click: **▶️ Start Strategy**

### Step 3: Watch Backend Terminal
Look for error messages like:
- `ModuleNotFoundError`
- `ImportError` 
- `AttributeError`
- Stack traces

## 📊 What the Strategy Should Do:

When working correctly, the **Scalp Strategy** will:
- Monitor BTCUSDT price in real-time
- Look for 1.2% deviation from SMA (Simple Moving Average)
- Enter virtual positions (no real money)
- Target 2.5% profit or 1.5% stop loss
- Close positions within 2 hours max

You'll see:
- "Open Positions" count increase
- Trades appear in the dashboard
- P&L values update
- All simulated (paper trading)

## 🐛 Troubleshooting:

If strategy won't start:
1. Check backend terminal for Python errors
2. Verify live_strategy.py exists: `ls src/arbitrage/live_strategy.py`
3. Check if CCXT is installed: `pip list | Select-String ccxt`
4. Try running: `python -c "from src.arbitrage.live_strategy import LiveStrategy; print('OK')"`

## 📝 Key Files:
- Backend: `src/arbitrage/web.py` (line 2239: start endpoint)
- Strategy: `src/arbitrage/live_strategy.py` (the actual trading logic)
- Frontend: `web/frontend/app/trading/page.tsx` (UI controls)
- Config: `.env` (API keys and settings)

## 💡 Remember:
- This is **100% paper trading** - no real money
- Your Binance account needs **$0 balance** to test
- Only API connection is used (for live prices)
- Change `ARB_ALLOW_LIVE_EXECUTION=1` only after 24-48 hours of successful paper trading

## 🆘 If Stuck:
The backend keeps crashing, which suggests the live_strategy module might have an issue. Try:
```powershell
python -c "from src.arbitrage.live_strategy import LiveStrategy"
```

This will show the exact import error if there is one.
