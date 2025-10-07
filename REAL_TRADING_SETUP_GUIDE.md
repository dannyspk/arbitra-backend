# 🚨 Real Trading Execution Setup Guide

## ⚠️ CRITICAL WARNING
**Real trading involves REAL MONEY and REAL RISK. Test thoroughly in paper mode first!**

---

## Current System Status

✅ **What You Have:**
- Live strategy framework (Bear/Bull/Scalp/Range modes)
- Frontend controls on Trading page
- Backend API endpoints (`/api/live-strategy/start`, `/api/live-strategy/stop`, `/api/live-strategy/status`)
- Strategy executor with paper/dry run modes
- WebSocket live data feeds
- Risk management parameters

❌ **What's Missing for Real Execution:**
- Binance API credentials configured
- Live execution enabled via environment variable
- Safety checks and circuit breakers
- Position monitoring and alerts

---

## Step 1: Configure Binance API Credentials

### 1.1 Create Binance API Key

1. Go to: https://www.binance.com/en/my/settings/api-management
2. Create a new API key with these permissions:
   - ✅ **Enable Reading** (required)
   - ✅ **Enable Spot & Margin Trading** (required for spot strategies)
   - ✅ **Enable Futures** (required for futures strategies)
   - ❌ **Disable Withdrawals** (for safety!)
3. **IMPORTANT:** Whitelist your IP address for extra security
4. Save your API Key and Secret Key securely

### 1.2 Add Credentials to Environment

**Option A: Using .env file (Local Development)**

Create or edit `C:\arbitrage\.env`:

```bash
# Binance API Credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_key_here

# Enable Live Trading (BE CAREFUL!)
ARB_ALLOW_LIVE_EXECUTION=1

# Risk Management
ARB_MAX_POSITION_SIZE=100  # Max position size in USDT
ARB_MAX_DAILY_TRADES=50    # Max trades per day
ARB_MAX_LOSS_PERCENT=2     # Max loss per trade (%)

# Strategy Settings
ARB_STRATEGY_MODE=scalp    # bear, bull, scalp, or range
ARB_AUTO_START=0           # Don't auto-start strategies
```

**Option B: Using Railway Environment Variables (Production)**

1. Go to Railway dashboard: https://railway.app/project/YOUR_PROJECT
2. Select your service → **Variables**
3. Add these variables:
   ```
   BINANCE_API_KEY=your_api_key_here
   BINANCE_API_SECRET=your_secret_key_here
   ARB_ALLOW_LIVE_EXECUTION=1
   ARB_MAX_POSITION_SIZE=100
   ARB_MAX_DAILY_TRADES=50
   ARB_MAX_LOSS_PERCENT=2
   ```

---

## Step 2: Update Backend Code for Live Execution

### 2.1 Check Exchange Configuration

The system needs to detect if API credentials are configured:

```python
# In src/arbitrage/exchanges.py or relevant file

import os
from ccxt import binance

def get_binance_exchange(testnet=False):
    """Get configured Binance exchange"""
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        raise ValueError("Binance API credentials not configured!")
    
    exchange = binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # or 'spot'
        }
    })
    
    if testnet:
        exchange.set_sandbox_mode(True)
    
    return exchange
```

### 2.2 Add Safety Checks to Strategy Executor

Add circuit breakers to prevent runaway losses:

```python
# In your strategy executor

class SafetyManager:
    def __init__(self):
        self.max_position_size = float(os.getenv('ARB_MAX_POSITION_SIZE', 100))
        self.max_daily_trades = int(os.getenv('ARB_MAX_DAILY_TRADES', 50))
        self.max_loss_percent = float(os.getenv('ARB_MAX_LOSS_PERCENT', 2))
        self.daily_trades = 0
        self.daily_loss = 0
        self.last_reset = datetime.now().date()
    
    def can_trade(self, position_size: float) -> tuple[bool, str]:
        """Check if trade is allowed"""
        # Reset daily counters
        if datetime.now().date() > self.last_reset:
            self.daily_trades = 0
            self.daily_loss = 0
            self.last_reset = datetime.now().date()
        
        # Check position size
        if position_size > self.max_position_size:
            return False, f"Position size {position_size} exceeds max {self.max_position_size}"
        
        # Check daily trade limit
        if self.daily_trades >= self.max_daily_trades:
            return False, f"Daily trade limit reached ({self.max_daily_trades})"
        
        # Check daily loss limit
        if self.daily_loss >= self.max_loss_percent:
            return False, f"Daily loss limit reached ({self.max_loss_percent}%)"
        
        return True, "OK"
    
    def record_trade(self, profit_loss: float):
        """Record trade result"""
        self.daily_trades += 1
        if profit_loss < 0:
            self.daily_loss += abs(profit_loss)
```

---

## Step 3: Enable Live Execution Flag

### 3.1 Check Current Status

```python
# Check if live execution is enabled
import os

live_enabled = os.getenv('ARB_ALLOW_LIVE_EXECUTION', '0') == '1'
print(f"Live execution enabled: {live_enabled}")
```

### 3.2 Modify Strategy Execution Logic

```python
async def execute_trade(self, signal, dry_run=True):
    """Execute trade with safety checks"""
    
    # Force dry run if live execution not enabled
    if not os.getenv('ARB_ALLOW_LIVE_EXECUTION') == '1':
        dry_run = True
        logger.warning("Live execution disabled, forcing dry run")
    
    # Safety checks
    can_trade, reason = self.safety_manager.can_trade(signal.position_size)
    if not can_trade:
        logger.error(f"Trade blocked: {reason}")
        return {"error": reason}
    
    if dry_run:
        # Simulate trade
        return self._simulate_trade(signal)
    else:
        # Execute real trade
        return await self._execute_real_trade(signal)
```

---

## Step 4: Test in Paper Trading Mode First

### 4.1 Start with Dry Run

```bash
# Set environment
ARB_ALLOW_LIVE_EXECUTION=0

# Start strategy
python -m uvicorn src.arbitrage.web:app --reload
```

### 4.2 Monitor Performance

1. Go to: http://localhost:3000/trading
2. Select a symbol (e.g., BTCUSDT)
3. Choose strategy mode (Scalp recommended for testing)
4. Click "Start Strategy"
5. Monitor the dashboard for:
   - Entry/exit signals
   - Profit/loss tracking
   - Win rate
   - Max drawdown

### 4.3 Analyze Results

Run paper trading for at least **24-48 hours** and check:
- ✅ Win rate > 60%
- ✅ Average profit > average loss
- ✅ Max drawdown < 5%
- ✅ No system errors or crashes

---

## Step 5: Enable Live Trading (CAREFULLY!)

### 5.1 Start Small

**First Live Trade Settings:**
```bash
ARB_ALLOW_LIVE_EXECUTION=1
ARB_MAX_POSITION_SIZE=10      # Start with $10 USDT
ARB_MAX_DAILY_TRADES=5        # Only 5 trades per day
ARB_MAX_LOSS_PERCENT=1        # Max 1% loss
```

### 5.2 Monitor Constantly

**Watch These Metrics:**
- Position status (open/closed)
- Balance changes
- Order execution success rate
- Slippage vs expected
- API errors or rate limits

### 5.3 Gradually Increase

After 1 week of successful small trades:
```bash
ARB_MAX_POSITION_SIZE=50      # Increase to $50
ARB_MAX_DAILY_TRADES=10       # 10 trades per day
```

---

## Step 6: Risk Management Checklist

### Before Each Trading Session:

- [ ] Check Binance account balance
- [ ] Verify API key permissions
- [ ] Confirm strategy parameters
- [ ] Set stop-loss limits
- [ ] Test with 1 small trade first

### During Trading:

- [ ] Monitor open positions
- [ ] Check for unusual price movements
- [ ] Watch for high volatility
- [ ] Verify order execution
- [ ] Track profit/loss in real-time

### End of Day:

- [ ] Review all trades
- [ ] Calculate win rate
- [ ] Analyze losses
- [ ] Adjust strategy if needed
- [ ] Backup trade logs

---

## Step 7: Emergency Stop Procedures

### Manual Stop

1. **Frontend:** Click "Stop Strategy" button
2. **Backend:** Call `/api/live-strategy/stop`
3. **Force Stop:** Restart the backend server

### Kill Switch

Add to your backend:

```python
@app.post("/api/emergency-stop")
async def emergency_stop():
    """Emergency stop all trading"""
    global strategy_runner
    
    # Stop all strategies
    if strategy_runner:
        await strategy_runner.stop()
    
    # Close all open positions
    await close_all_positions()
    
    # Disable live execution
    os.environ['ARB_ALLOW_LIVE_EXECUTION'] = '0'
    
    return {"stopped": True, "message": "Emergency stop executed"}
```

### Close All Positions

```python
async def close_all_positions():
    """Close all open positions immediately"""
    exchange = get_binance_exchange()
    positions = exchange.fetch_positions()
    
    for pos in positions:
        if pos['contracts'] > 0:
            # Close position
            exchange.create_market_order(
                symbol=pos['symbol'],
                side='sell' if pos['side'] == 'long' else 'buy',
                amount=abs(pos['contracts'])
            )
```

---

## Step 8: Monitoring and Alerts

### Set Up Alerts

**Discord/Telegram Webhook:**
```python
import requests

def send_alert(message: str, level: str = "INFO"):
    """Send alert to Discord/Telegram"""
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    
    if webhook_url:
        requests.post(webhook_url, json={
            "content": f"[{level}] {message}"
        })
```

**Alert on:**
- Position opened
- Position closed
- Loss exceeds threshold
- Daily trade limit reached
- API errors
- Unusual price movements

### Log Everything

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading.log'),
        logging.StreamHandler()
    ]
)
```

---

## Step 9: Legal and Compliance

### Disclaimer

⚠️ **YOU are responsible for:**
- All trades executed by the system
- Any losses incurred
- Tax reporting
- Compliance with local regulations

### Recommended:

- Consult with a financial advisor
- Understand tax implications
- Keep detailed trade records
- Review exchange terms of service

---

## Quick Start Checklist

### Initial Setup (One Time)

- [ ] Create Binance API key
- [ ] Add credentials to .env file
- [ ] Configure risk parameters
- [ ] Test API connection
- [ ] Run paper trading for 48 hours

### Before Going Live

- [ ] Review paper trading results
- [ ] Set position size to $10
- [ ] Limit to 5 trades/day
- [ ] Set up monitoring alerts
- [ ] Prepare emergency stop

### Going Live

- [ ] Set `ARB_ALLOW_LIVE_EXECUTION=1`
- [ ] Start with 1 test trade
- [ ] Monitor for 1 hour
- [ ] Gradually increase if successful
- [ ] Stop immediately if issues arise

---

## Troubleshooting

### "API key not configured"
- Check .env file exists
- Verify BINANCE_API_KEY is set
- Restart backend server

### "Insufficient balance"
- Check Binance account balance
- Reduce ARB_MAX_POSITION_SIZE
- Transfer funds to trading account

### "Order rejected"
- Check symbol format (BTCUSDT not BTC/USDT)
- Verify you have trading permissions
- Check if market is open

### "Rate limit exceeded"
- Reduce trade frequency
- Increase `enableRateLimit` delay
- Check for API spam

---

## Support and Resources

- **Binance API Docs:** https://binance-docs.github.io/apidocs/
- **CCXT Documentation:** https://docs.ccxt.com/
- **Your Backend Logs:** `C:\arbitrage\trading.log`
- **Railway Logs:** https://railway.app (if deployed)

---

## Final Reminder

🚨 **START SMALL. TEST THOROUGHLY. NEVER RISK MORE THAN YOU CAN AFFORD TO LOSE.**

Good luck and trade safely! 🚀
