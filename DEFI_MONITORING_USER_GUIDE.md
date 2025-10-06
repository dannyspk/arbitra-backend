# DeFi Vault Monitoring - User Guide

## 🎯 Overview

The DeFi Vaults page now includes comprehensive monitoring tools to help you track yield opportunities and manage your positions effectively.

## 📊 Features

### 1. **Available Vaults Tab**
Browse high-yield DeFi vaults with real-time APY data from DeFiLlama.

**What you see:**
- Current APY (with base + rewards breakdown)
- Total Value Locked (TVL)
- Risk level (Low/Medium/High)
- Protocol and chain information
- Leverage indicators for looping strategies

**New Actions:**
- 📈 **APY History** - View historical APY trends
- 🔔 **Set Alert** - Create custom APY alerts
- 🔗 **View Vault** - Go to protocol interface
- 📊 **Analytics** - See DeFiLlama data

---

### 2. **APY History Chart** 📈

Click the "APY History" button on any vault to see:

**Visualization:**
- Line chart showing APY over time (6h, 12h, 24h, 48h, 7d)
- Separate lines for total APY and base APY
- Red dots mark outlier data points (potentially unsustainable yields)

**Stats Displayed:**
- Current APY
- APY change over selected period
- Number of data points collected
- Recent data point history

**Use Cases:**
- Spot APY trends (rising/falling)
- Identify stable vs volatile yields
- Time your entry/exit based on historical patterns
- Validate sustainability of high yields

---

### 3. **Alert Manager** 🔔

Set up intelligent alerts to catch time-sensitive opportunities.

**Alert Types:**

#### 📉 APY Drop
- **Trigger:** When APY drops by X% or more
- **Example:** Alert if APY drops by 20%
- **Use case:** Exit signal - yield is deteriorating

#### 📈 APY Spike  
- **Trigger:** When APY increases by X% or more
- **Example:** Alert if APY spikes by 50%
- **Use case:** Entry opportunity - new leverage/looping activated

#### ⬇️ Below Threshold
- **Trigger:** When APY falls below an absolute value
- **Example:** Alert if APY < 10%
- **Use case:** Minimum yield requirement not met

#### ⬆️ Above Threshold
- **Trigger:** When APY rises above an absolute value
- **Example:** Alert if APY > 20%
- **Use case:** Target yield opportunity reached

**Setup:**
1. Click "Set Alert" on any vault
2. Choose alert type
3. Set threshold percentage
4. Enter webhook URL (Discord, Slack, Telegram, etc.)
5. Click "Create Alert"

**Webhook Setup:**
- **Discord:** Server Settings → Integrations → Webhooks → New Webhook
- **Test webhook:** Use https://webhook.site for testing
- **Slack:** Create an incoming webhook app
- **Telegram:** Use bot API with webhook

**Alert Example Notification:**
```json
{
  "vault_name": "Stream Finance USDC",
  "protocol": "Stream Finance",
  "chain": "Ethereum",
  "current_apy": 10.5,
  "message": "APY dropped 30.5% (from 15.2% to 10.5%)",
  "defillama_url": "https://defillama.com/yields/pool/..."
}
```

---

### 4. **Position Tracker** 📊

Track your active positions and monitor yield performance.

**Features:**
- Connect wallet address to track positions
- Add positions with entry APY
- See real-time APY comparison
- Calculate yield impact of APY changes

**To Track a Position:**
1. Go to "My Positions" tab
2. Click "Connect Your Wallet"
3. Enter your wallet address (e.g., `0xYour...Address`)
4. Click "+ Track Position"
5. Select vault, enter amount and entry APY
6. Click "Track Position"

**What You See:**
- **Total Value:** Sum of all position amounts
- **Active Positions:** Number of tracked positions
- **Avg APY Change:** Average APY delta across all positions

**Position Details:**
- Entry APY vs Current APY
- APY Change (percentage)
- Yield Impact (annual $ difference)
- Time since entry
- Protocol and chain info

**Example:**
```
Position: Stream Finance USDC
Amount: $50,000
Entry APY: 15.2%
Current APY: 13.8%
APY Change: -9.2%
Yield Impact: -$700/year
```

**Use Cases:**
- Monitor multiple positions across protocols
- Identify underperforming positions
- Calculate opportunity cost of staying vs exiting
- Track when to rebalance

---

## 🚀 Quick Start Guide

### For Yield Hunters

**Goal:** Find and capture high-yield opportunities

1. Browse "Available Vaults" tab
2. Sort by highest APY
3. Click "APY History" to check stability
4. Set "APY Above 20%" alert for future opportunities
5. Enter position when alert fires

### For Active Position Managers

**Goal:** Optimize existing positions

1. Add all positions to "My Positions" tab
2. Set "APY Drop 15%" alerts on each vault
3. Check positions daily for yield degradation
4. Exit when alerts fire or yield impact is negative
5. Rebalance to higher-yield vaults

### For Conservative Investors

**Goal:** Maintain stable yields with minimal risk

1. Filter for "Low Risk" vaults
2. Check APY history for stability (< 20% volatility)
3. Avoid vaults marked as "Outlier"
4. Set "APY Below 10%" alerts
5. Monitor 30-day average APY vs current

---

## 📱 Mobile Access

All features work on mobile browsers:
- Responsive design
- Touch-optimized charts
- Swipeable tabs
- Mobile-friendly forms

---

##⚙️ Automation Tips

### Discord Bot Integration
Create a dedicated channel for vault alerts:
1. Create #defi-alerts channel
2. Set up webhook for that channel
3. Configure alerts for all tracked vaults
4. Get real-time notifications on your phone

### Multi-Vault Strategy
Track opportunities across protocols:
```
- Set "APY Above 20%" on 10+ vaults
- Get notified when any spike
- Quick decision-making with mobile alerts
- Move capital to highest yield instantly
```

### Risk Management
Set defensive alerts:
```
- APY Drop 20% = Exit signal
- APY Below 8% = Minimum acceptable
- Check for "Outlier" flag = Unsustainable yield
```

---

## 🔄 Update Frequency

- **APY Data:** Updates every 5 minutes (background monitor)
- **Vaults Page:** Auto-refreshes every 60 seconds
- **Alerts:** Checked on each update (5min intervals)
- **Alert Cooldown:** 15 minutes between duplicate notifications

---

## 📊 Data Sources

- **APY Data:** DeFiLlama Yields API (live data from protocol smart contracts)
- **Historical Data:** 7-day rolling window stored locally
- **Fees/Withdrawal Info:** Not available from API (check protocol docs)

---

## 🛠️ Troubleshooting

**Q: Alert not triggering?**
- Check threshold settings
- Verify webhook URL is correct
- Test webhook at webhook.site first
- Check server logs for errors

**Q: No historical data showing?**
- System needs 5-10 minutes to collect first data points
- Check back shortly after server starts
- Refresh page to load latest data

**Q: Position not updating?**
- Ensure wallet address is correct
- Position updates every time vault data refreshes (60s)
- Clear browser cache if stale

**Q: Can't see my vault?**
- Only shows vaults meeting criteria:
  - $10M+ TVL
  - 10%+ base APY
  - Stablecoin only
  - No impermanent loss risk

---

## 🎓 Best Practices

1. **Start Small:** Track 1-2 positions first
2. **Test Alerts:** Use webhook.site before Discord
3. **Check History:** Don't chase spikes without context
4. **Diversify:** Don't put everything in highest APY
5. **Monitor Outliers:** High APY = High risk often
6. **Set Realistic Thresholds:** Too sensitive = alert fatigue
7. **Update Positions:** Re-track when you rebalance

---

## 🚧 Coming Soon

- [ ] Email notifications
- [ ] Telegram bot integration
- [ ] On-chain position verification
- [ ] Gas cost estimator
- [ ] Multi-vault comparison alerts
- [ ] APY prediction using ML
- [ ] Smart rebalancing recommendations
- [ ] Portfolio analytics dashboard

---

## 📞 Need Help?

- Check server logs for errors
- Verify DeFiLlama API access
- Test webhooks independently
- Review alert configuration

**Happy yield farming! 🌾💰**
