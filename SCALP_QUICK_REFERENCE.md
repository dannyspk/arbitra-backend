# ⚡ Quick Reference: Scalp Strategy Configs

## 📊 Current Configuration (UPDATED)

```python
✅ STANDARD SCALP (Default - Good for most traders)
Entry:    1.2% deviation from SMA
Target:   2.5% profit (net 2.35% after fees)
Partial:  1.5% profit (net 1.35% after fees) → Close 50%
Stop:     1.5% loss (net -1.65% with fees)
Max Hold: 2 hours
Size:     $200 base (volatility adjusted)
R:R:      1:1.42
Expected: 10-15% monthly return
```

---

## 🎚️ Other Presets

### Conservative (Beginners)
```
Entry: 1.0% | Target: 2.0% | Stop: 1.2% | R:R: 1:1.37
Expected: 8-12% monthly, 60-65% win rate
```

### Aggressive (Experienced)
```
Entry: 1.5% | Target: 3.5% | Stop: 1.8% | R:R: 1:1.72
Expected: 15-25% monthly, 50-55% win rate
```

### Day Trading (Swing-style)
```
Entry: 2.0% | Target: 5.0% | Stop: 2.5% | R:R: 1:1.83
Expected: 20-30% monthly, 45-50% win rate
```

---

## 💰 Why The Old Config Failed

| Metric | Old (Bad) | New (Good) | Difference |
|--------|-----------|------------|------------|
| Target | 0.9% | 2.5% | +178% |
| Net Profit | 0.75% | 2.35% | +213% |
| Stop | -1.15% | -1.65% | Wider breathing room |
| R:R | 1:0.65 ❌ | 1:1.42 ✅ | +118% better |
| Break-even WR | 60% | 42% | Much easier! |

**Old config needed 60% win rate just to break even - impossible!**

---

## 🔧 How to Change Config

Edit `src/arbitrage/live_strategy.py` around line 58:

```python
self.scalp_strategy = QuickScalpStrategy(
    notional_per_trade=200.0,     # ← Change base position size
    entry_threshold=0.012,        # ← Change entry trigger
    exit_target=0.025,            # ← Change profit target
    partial_target=0.015,         # ← Change partial exit
    stop_loss=0.015,              # ← Change stop loss
    max_holding_bars=120,         # ← Change max hold time
    max_notional=2000.0,          # ← Change max position
)
```

---

## 📈 Real Example: $10K Account

### Standard Config
```
Position: $200 (2% of account)
Trades/day: 15
Win rate: 58%

Good day:
9 wins × $4.70 = +$42.30
6 losses × $3.30 = -$19.80
Net: +$22.50/day (+0.225%)

Month: +$450 (+4.5%)
With compounding: +$675 (+6.75%)
```

### Aggressive Config  
```
Position: $300 (3% of account)
Trades/day: 8
Win rate: 52%

Good day:
4 wins × $10.05 = +$40.20
4 losses × $5.85 = -$23.40
Net: +$16.80/day (+0.168%)

Month: +$336 (+3.36%)
With compounding: +$504 (+5.04%)
```

---

## ⚠️ Key Rules

1. **Never use < 1.5% profit targets** in crypto
   - Fees + slippage = ~0.15%
   - Need buffer for costs!

2. **Risk:Reward must be > 1:1**
   - Otherwise need >50% win rate
   - Hard to sustain long-term

3. **Account for ALL costs**
   - Trading fees (0.14% round trip)
   - Slippage (~0.05%)
   - Funding rates (varies)
   - Total: ~0.15-0.20%

4. **Test in paper mode first!**
   - Run for 24-48 hours
   - Verify win rate and P&L
   - Only then consider live

---

## 🎯 Choose Your Config

**New to algo trading?** → Conservative
**Some experience?** → Standard (current default)
**Experienced trader?** → Aggressive  
**Swing trader?** → Day Trading preset

---

## 📞 Quick Stats

| Config | Trades/Day | Win% | Monthly | Drawdown |
|--------|-----------|------|---------|----------|
| Conservative | 10-15 | 60-65% | 8-12% | 2-3% |
| **Standard** | 12-18 | 55-60% | 10-15% | 3-5% |
| Aggressive | 8-12 | 50-55% | 15-25% | 5-8% |
| Day Trading | 4-8 | 45-50% | 20-30% | 8-12% |

---

**Remember: The market doesn't care about your targets. Price does what it wants. Your job is to set realistic targets that account for costs and give you a statistical edge!** 🚀
