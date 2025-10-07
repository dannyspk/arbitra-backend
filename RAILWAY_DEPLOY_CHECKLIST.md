# 🚀 Railway Deployment Readiness Checklist

**Date:** October 7, 2025  
**Purpose:** Deploy backend to Railway for 24/7 paper trading monitoring

---

## ✅ Pre-Deployment Checklist

### 1. Essential Files ✅
- [x] `Procfile` - Tells Railway how to start the app
- [x] `railway.toml` - Railway configuration
- [x] `runtime.txt` - Python version (3.12)
- [x] `requirements.txt` - Dependencies with uvicorn & fastapi
- [x] `src/arbitrage/web.py` - Main FastAPI app with `/health` endpoint

### 2. Code Status ⚠️
- [x] Live strategy implementation (Bear/Bull/Scalp/Range modes)
- [x] Multiple strategy support
- [x] Dashboard API endpoints
- [ ] **.env file NOT committed** (important for security!)
- [ ] Uncommitted changes need to be committed

### 3. Environment Variables to Set on Railway 🔐

**Required:**
```bash
ARB_ALLOW_LIVE_EXECUTION=0          # Paper trading mode (SAFE!)
ARB_ALLOW_ORIGINS=*                  # Allow CORS for your frontend
PORT=8000                             # Railway will set this automatically
```

**Optional (for API features):**
```bash
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
LUNARCRUSH_API_KEY=your_key_here
ARB_MAX_POSITION_SIZE=10
ARB_MAX_DAILY_TRADES=5
ARB_MAX_LOSS_PERCENT=1
```

**⚠️ CRITICAL:** Never commit your `.env` file! Set these in Railway dashboard.

### 4. Git Status
**Current uncommitted changes:**
- `src/arbitrage/live_strategy.py` (adaptive Bear strategy)
- `src/arbitrage/web.py` (API endpoints)
- Multiple documentation files

**Action needed:** Commit and push before deploying

---

## 📋 Deployment Steps

### Step 1: Secure Your API Keys
```powershell
# Make sure .env is in .gitignore
Get-Content .gitignore | Select-String ".env"

# If not found, add it:
Add-Content .gitignore "`n.env"
```

### Step 2: Commit Your Changes
```powershell
cd C:\arbitrage

# Stage important files (EXCLUDING .env!)
git add src/arbitrage/live_strategy.py
git add src/arbitrage/web.py
git add ADAPTIVE_BEAR_STRATEGY.md
git add MULTIPLE_STRATEGIES_GUIDE.md
git add NO_SIGNALS_YET_EXPLAINED.md
git add SIGNAL_FLOW_EXPLANATION.md
git add requirements.txt
git add Procfile
git add railway.toml
git add runtime.txt

# Commit
git commit -m "Add live strategy framework for Railway deployment"

# Push to GitHub
git push origin main
```

### Step 3: Deploy to Railway

1. **Go to Railway:**
   - Visit https://railway.app
   - Login with GitHub

2. **Create New Project:**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose `dannyspk/arbitra-backend`
   - Railway auto-detects Python

3. **Configure Environment Variables:**
   - Click on deployed service
   - Go to "Variables" tab
   - Add the required variables (see section 3 above)
   - **Most important:** `ARB_ALLOW_LIVE_EXECUTION=0` (paper trading!)

4. **Wait for Deployment:**
   - Railway builds (2-5 minutes)
   - Gets a URL like: `https://arbitra-backend-production.up.railway.app`

5. **Test Deployment:**
   ```powershell
   # Test health endpoint
   Invoke-RestMethod "https://YOUR-RAILWAY-URL.up.railway.app/health"
   
   # Should return: {"status":"healthy"}
   ```

6. **Start Strategies:**
   ```powershell
   # Start BTCUSDT scalp
   Invoke-RestMethod -Method POST -Uri "https://YOUR-RAILWAY-URL.up.railway.app/api/live-strategy/start" `
     -ContentType "application/json" `
     -Body '{"symbol":"BTCUSDT","mode":"scalp","interval":"1m"}'
   
   # Start AIAUSDT bear
   Invoke-RestMethod -Method POST -Uri "https://YOUR-RAILWAY-URL.up.railway.app/api/live-strategy/start" `
     -ContentType "application/json" `
     -Body '{"symbol":"AIAUSDT","mode":"bear","interval":"15m"}'
   
   # Start COAIUSDT bear
   Invoke-RestMethod -Method POST -Uri "https://YOUR-RAILWAY-URL.up.railway.app/api/live-strategy/start" `
     -ContentType "application/json" `
     -Body '{"symbol":"COAIUSDT","mode":"bear","interval":"15m"}'
   ```

7. **Monitor Dashboard:**
   ```powershell
   # Check status
   Invoke-RestMethod "https://YOUR-RAILWAY-URL.up.railway.app/api/dashboard"
   ```

---

## 🎯 Post-Deployment Monitoring

### Check Logs on Railway:
- Click on your service
- Go to "Deployments" tab
- Click on latest deployment
- View logs in real-time

### Monitor Signals:
```powershell
# Create monitoring script for Railway
$railwayUrl = "https://YOUR-RAILWAY-URL.up.railway.app"

while ($true) {
    $dash = Invoke-RestMethod "$railwayUrl/api/dashboard"
    Clear-Host
    Write-Host "=== Railway Strategy Monitor ===" -ForegroundColor Cyan
    Write-Host "Signals: $($dash.signals.Count)" -ForegroundColor Green
    Write-Host "Positions: $($dash.positions.Count)" -ForegroundColor Yellow
    Write-Host "Trades: $($dash.trades.Count)" -ForegroundColor White
    
    if ($dash.signals.Count -gt 0) {
        Write-Host "`nRecent Signal:" -ForegroundColor Cyan
        $latest = $dash.signals[0]
        Write-Host "  $($latest.symbol) - $($latest.action) @ `$$($latest.price)" -ForegroundColor White
    }
    
    Start-Sleep -Seconds 30
}
```

---

## ⚠️ Important Notes

### 🔒 Security
- **Never commit `.env` file** - Use Railway environment variables
- **Keep API keys secure** - Set them in Railway dashboard only
- **Paper trading enabled** - `ARB_ALLOW_LIVE_EXECUTION=0` prevents real trades

### 💰 Railway Costs
- **Free tier:** $5 credit/month
- **Estimated usage:** ~$3-5/month for this backend
- **Upgrade if needed:** Developer plan $5/month

### 🔄 Continuous Operation
- Railway keeps app running 24/7
- Auto-restarts on crashes (configured in railway.toml)
- Strategies persist across restarts

### 📊 Data Collection
- Signals stored in memory (resets on restart)
- For persistent storage, consider adding database later
- Current setup perfect for 24-48 hour testing

---

## 🚨 Troubleshooting

### Build Fails
```powershell
# Check Python version matches runtime.txt
cat runtime.txt  # Should be: 3.12

# Check requirements.txt has all dependencies
cat requirements.txt | grep -E "fastapi|uvicorn|ccxt"
```

### Health Check Fails
- Verify `/health` endpoint exists in `src/arbitrage/web.py`
- Check Railway logs for errors
- Ensure port binding to `$PORT` variable

### No Signals Generating
- Check if strategies started successfully
- Verify CCXT can access Binance API (no keys needed for public data)
- Monitor Railway logs for errors

---

## ✅ Ready to Deploy?

**All checks passed:**
- [x] Files ready (Procfile, railway.toml, requirements.txt)
- [x] Code includes live strategy framework
- [x] Health endpoint exists
- [x] `.env` will be excluded from git
- [ ] Commit pending changes
- [ ] Push to GitHub
- [ ] Deploy to Railway

**Next command:**
```powershell
# Run this to start deployment process
git status   # Review changes
git add .    # Stage files (excluding .env)
git commit -m "Ready for Railway deployment with live strategies"
git push origin main
```

Then go to https://railway.app and deploy! 🚀
