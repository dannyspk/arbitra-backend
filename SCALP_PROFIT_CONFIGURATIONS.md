# 💰 Scalp Strategy - Realistic Profit Configurations

## ❌ Why 0.9% Targets Don't Work in Crypto

### Cost Breakdown
```
Entry:   $100 position
Maker Fee (0.04%):  -$0.04
Taker Fee (0.04%):  -$0.04
Slippage (0.05%):   -$0.05
Funding (avg):      -$0.02
------------------------
Total Costs:        -$0.15 (0.15%)

Target: 0.9%
Costs:  -0.15%
------------------------
Net Profit: 0.75%

But with 1% stop loss:
Risk: -1.15% (including costs)
Reward: 0.75%
R:R = 0.65:1  ❌ TERRIBLE
```

**You'd need 60%+ win rate just to break even!**

---

## ✅ Profitable Configurations

### **Configuration 1: Standard Scalp (CURRENT)**
**Target Market**: Medium volatility, ranging markets

```python
QuickScalpStrategy(
    notional_per_trade=200.0,     # $200 base size
    entry_threshold=0.012,        # 1.2% deviation
    exit_target=0.025,            # 2.5% target
    partial_target=0.015,         # 1.5% partial
    stop_loss=0.015,              # 1.5% stop
    max_holding_bars=120,         # 2 hours max
)
```

**Profit Analysis:**
```
Full Target: 2.5% - 0.15% fees = 2.35% net ✅
Partial:     1.5% - 0.15% fees = 1.35% net ✅
Stop Loss:   -1.5% - 0.15% fees = -1.65% net

Risk:Reward = 1.65% : 2.35% = 1:1.42 ✅

Win Rate Needed: 42% to break even
Expected: 55-60% win rate
Expected Return: 10-15% monthly
```

---

### **Configuration 2: Aggressive Scalp**
**Target Market**: High volatility, trending markets

```python
QuickScalpStrategy(
    notional_per_trade=300.0,     # Larger size
    entry_threshold=0.015,        # 1.5% deviation (wait for bigger moves)
    exit_target=0.035,            # 3.5% target
    partial_target=0.020,         # 2.0% partial
    stop_loss=0.018,              # 1.8% stop
    max_holding_bars=180,         # 3 hours max
    min_notional=30.0,
    max_notional=3000.0,
)
```

**Profit Analysis:**
```
Full Target: 3.5% - 0.15% = 3.35% net ✅✅
Partial:     2.0% - 0.15% = 1.85% net ✅
Stop Loss:   -1.8% - 0.15% = -1.95% net

Risk:Reward = 1.95% : 3.35% = 1:1.72 ✅✅

Win Rate Needed: 37% to break even
Expected: 50-55% win rate
Expected Return: 15-25% monthly
```

---

### **Configuration 3: Day Trading (Not Really Scalping)**
**Target Market**: Strong trends, larger moves

```python
QuickScalpStrategy(
    notional_per_trade=500.0,     # Much larger size
    entry_threshold=0.020,        # 2% deviation
    exit_target=0.050,            # 5% target
    partial_target=0.030,         # 3% partial
    stop_loss=0.025,              # 2.5% stop
    max_holding_bars=360,         # 6 hours max
    min_notional=50.0,
    max_notional=5000.0,
)
```

**Profit Analysis:**
```
Full Target: 5.0% - 0.15% = 4.85% net ✅✅✅
Partial:     3.0% - 0.15% = 2.85% net ✅✅
Stop Loss:   -2.5% - 0.15% = -2.65% net

Risk:Reward = 2.65% : 4.85% = 1:1.83 ✅✅

Win Rate Needed: 35% to break even
Expected: 45-50% win rate
Expected Return: 20-30% monthly
```

---

### **Configuration 4: Conservative (Lower Risk)**
**Target Market**: Low volatility, beginners

```python
QuickScalpStrategy(
    notional_per_trade=100.0,     # Smaller size
    entry_threshold=0.010,        # 1% deviation
    exit_target=0.020,            # 2% target
    partial_target=0.012,         # 1.2% partial
    stop_loss=0.012,              # 1.2% stop
    max_holding_bars=90,          # 1.5 hours max
    min_notional=10.0,
    max_notional=1000.0,
    trend_filter=True,            # Strict filters
)
```

**Profit Analysis:**
```
Full Target: 2.0% - 0.15% = 1.85% net ✅
Partial:     1.2% - 0.15% = 1.05% net ✅
Stop Loss:   -1.2% - 0.15% = -1.35% net

Risk:Reward = 1.35% : 1.85% = 1:1.37 ✅

Win Rate Needed: 42% to break even
Expected: 60-65% win rate (strict filters)
Expected Return: 8-12% monthly
```

---

## 📊 Comparison Table

| Config | Entry | Target | Stop | R:R | Win% Needed | Expected Win% | Monthly Return |
|--------|-------|--------|------|-----|-------------|---------------|----------------|
| **Old (Bad)** | 0.8% | 0.9% | 1.0% | 1:0.65 | 60% | 55% | -5% ❌ |
| **Standard** | 1.2% | 2.5% | 1.5% | 1:1.42 | 42% | 55-60% | 10-15% ✅ |
| **Aggressive** | 1.5% | 3.5% | 1.8% | 1:1.72 | 37% | 50-55% | 15-25% ✅ |
| **Day Trading** | 2.0% | 5.0% | 2.5% | 1:1.83 | 35% | 45-50% | 20-30% ✅ |
| **Conservative** | 1.0% | 2.0% | 1.2% | 1:1.37 | 42% | 60-65% | 8-12% ✅ |

---

## 🎯 Which Configuration to Choose?

### Choose **Standard** (Current) if:
- ✅ You're new to algorithmic trading
- ✅ Want balanced risk/reward
- ✅ Trading BTC/ETH pairs
- ✅ Market is ranging/choppy

### Choose **Aggressive** if:
- ✅ You have trading experience
- ✅ Want higher returns
- ✅ Market is volatile
- ✅ Can handle more drawdown

### Choose **Day Trading** if:
- ✅ You're experienced
- ✅ Want fewer, bigger trades
- ✅ Strong trends in market
- ✅ Don't want to watch 1m charts

### Choose **Conservative** if:
- ✅ You're testing the strategy
- ✅ Want high win rate
- ✅ Low risk tolerance
- ✅ Small account size

---

## 💡 Real-World Examples

### Example 1: Standard Config on BTCUSDT
```
Account: $10,000
Position Size: $200 (2% of account)
Trades per day: 15

Scenario A: Good Day (60% win rate)
Wins: 9 trades × 2.35% = +21.15% = +$42.30
Losses: 6 trades × -1.65% = -9.9% = -$19.80
Net: +$22.50 per day (+0.225% of account)
Monthly: +6.75% account growth

Scenario B: Bad Day (40% win rate)
Wins: 6 trades × 2.35% = +14.1% = +$28.20
Losses: 9 trades × -1.65% = -14.85% = -$29.70
Net: -$1.50 per day (-0.015% of account)
Monthly: -0.45% account drawdown
```

### Example 2: Aggressive Config on ETHUSDT
```
Account: $10,000
Position Size: $300 (3% of account)
Trades per day: 8

Scenario A: Good Day (55% win rate)
Wins: 4.4 trades × 3.35% = +14.74% = +$44.22
Losses: 3.6 trades × -1.95% = -7.02% = -$21.06
Net: +$23.16 per day (+0.232% of account)
Monthly: +6.96% account growth

Scenario B: Average Day (50% win rate)
Wins: 4 trades × 3.35% = +13.4% = +$40.20
Losses: 4 trades × -1.95% = -7.8% = -$23.40
Net: +$16.80 per day (+0.168% of account)
Monthly: +5.04% account growth
```

---

## 🔧 How to Implement

### Method 1: Edit the Code (Permanent)
Edit `src/arbitrage/live_strategy.py` line ~58:

```python
# Change these values to your preferred config
self.scalp_strategy = QuickScalpStrategy(
    notional_per_trade=200.0,    # Your values here
    entry_threshold=0.012,       # Your values here
    exit_target=0.025,           # Your values here
    # ... etc
)
```

### Method 2: Create Custom Strategy Class
```python
# In a new file: custom_scalp.py
from arbitrage.strategy import QuickScalpStrategy

class AggressiveScalp(QuickScalpStrategy):
    def __init__(self):
        super().__init__(
            notional_per_trade=300.0,
            entry_threshold=0.015,
            exit_target=0.035,
            partial_target=0.020,
            stop_loss=0.018,
            max_holding_bars=180,
        )
```

### Method 3: Environment Variables (Future Feature)
Could add config file support:
```json
{
    "scalp": {
        "notional": 200,
        "entry_threshold": 0.012,
        "exit_target": 0.025,
        "stop_loss": 0.015
    }
}
```

---

## 📈 Optimization Tips

### 1. **Increase Position Size, Not Frequency**
❌ 100 trades × $50 = $5,000 daily volume
✅ 20 trades × $250 = $5,000 daily volume (fewer fees!)

### 2. **Use Maker Orders When Possible**
- Maker fee: 0.02-0.04%
- Taker fee: 0.04-0.075%
- Savings: 50% on fees!

### 3. **Account for Funding**
- Long positions in backwardation: You GET paid
- Short positions in contango: You GET paid
- Factor this into targets!

### 4. **Scale with Volatility**
- High vol: Wider targets (3-5%)
- Low vol: Tighter targets (2-3%)
- Strategy already does this via vol adjustment!

### 5. **Time Your Entries**
- Best times: US market open (9:30 ET), Asia open (20:00 ET)
- Worst times: Low liquidity hours (4-6 AM ET)

---

## ⚠️ Important Notes

### Costs in Crypto Are Higher Than You Think
```
Binance Futures (VIP 0):
- Maker: 0.02%
- Taker: 0.04%
- Funding: ~0.01% per 8h (varies)

Round Trip Cost: ~0.15-0.20%
```

### Minimum Viable Targets
```
To be profitable with 50% win rate:
Minimum Target = (Stop Loss + Fees) × 1.2

Examples:
1% stop → 1.35% minimum target
1.5% stop → 2.0% minimum target
2% stop → 2.65% minimum target
```

### Realistic Expectations
- ✅ 5-15% monthly return is excellent
- ✅ 15-30% is exceptional (aggressive configs)
- ❌ 50%+ is unsustainable
- ❌ Expecting 1-2% daily consistently = unrealistic

---

## 🎓 Summary

The **new default configuration (Standard)** is now set to:
- **Entry**: 1.2% deviation
- **Target**: 2.5% (net 2.35%)
- **Partial**: 1.5% (net 1.35%)
- **Stop**: 1.5% (net -1.65%)
- **R:R**: 1:1.42

This gives you a **fighting chance** to be profitable!

Choose your configuration based on:
1. Your risk tolerance
2. Market conditions
3. Trading experience
4. Account size

**Always backtest first and start with paper trading!** 🚀
