# DeFi Vault APY Monitoring & Alerts

## Overview
The system now includes real-time APY monitoring and alerting for DeFi vaults, allowing users to track yield changes and get notified when opportunities arise or positions need attention.

## Features

### 1. **APY Historical Tracking**
- Automatically tracks APY changes every 5 minutes
- Stores 7 days of historical data per vault
- Includes base APY, reward APY, TVL, and outlier flags

### 2. **Smart Alerts**
Four types of alerts to catch time-sensitive opportunities:

#### Alert Types:
- **`apy_drop`**: Triggered when APY drops by X% (e.g., -20%)
  - Use case: Exit signal or opportunity to find better yields
  
- **`apy_spike`**: Triggered when APY increases by X% (e.g., +50%)
  - Use case: Entry signal for leveraged looping opportunities
  
- **`apy_below`**: Triggered when APY falls below absolute threshold
  - Use case: "Exit if APY < 10%"
  
- **`apy_above`**: Triggered when APY rises above absolute threshold
  - Use case: "Alert me when APY > 20%"

### 3. **Position Tracking**
- Track your wallet positions in specific vaults
- Monitor entry APY vs. current APY
- See real-time P&L on yield changes

### 4. **Webhook Notifications**
- Instant notifications to Discord, Slack, Telegram, etc.
- Custom webhook URLs per alert
- Email support (coming soon)

---

## API Endpoints

### Get Vault APY History
```http
GET /api/defi-vaults/history/{pool_id}?hours=24
```

**Response:**
```json
{
  "pool_id": "morpho-blue-re-7-wsteth-dai-0xec13d3....",
  "history": [
    {
      "timestamp": 1728234567.89,
      "timestamp_iso": "2025-10-06T12:00:00",
      "apy": 15.2,
      "apy_base": 15.2,
      "apy_reward": 0,
      "tvl_usd": 289916885,
      "outlier": false
    }
  ],
  "current_apy": 15.2,
  "apy_change": -1.5,
  "data_points": 288
}
```

### Create Alert
```http
POST /api/defi-vaults/alerts
Content-Type: application/json

{
  "pool_id": "morpho-blue-re-7-wsteth-dai-0xec13d3....",
  "alert_type": "apy_drop",
  "threshold": 20.0,
  "notification_method": "webhook",
  "webhook_url": "https://discord.com/api/webhooks/..."
}
```

**Response:**
```json
{
  "success": true,
  "alert_id": "a1b2c3d4e5f6g7h8",
  "message": "Alert created for morpho-blue-...",
  "alert": {
    "alert_id": "a1b2c3d4e5f6g7h8",
    "pool_id": "morpho-blue-...",
    "alert_type": "apy_drop",
    "threshold": 20.0,
    "active": true
  }
}
```

### Get All Alerts
```http
GET /api/defi-vaults/alerts?active_only=true
```

### Delete Alert
```http
DELETE /api/defi-vaults/alerts/{alert_id}
```

### Track Position
```http
POST /api/defi-vaults/positions
Content-Type: application/json

{
  "user_id": "0xYourWalletAddress",
  "pool_id": "morpho-blue-re-7-wsteth-dai-0xec13d3....",
  "amount": 10000,
  "entry_apy": 15.2,
  "tx_hash": "0x..."
}
```

### Get User Positions
```http
GET /api/defi-vaults/positions/{user_id}
```

**Response:**
```json
{
  "user_id": "0xYourWallet...",
  "positions": [
    {
      "pool_id": "morpho-blue-...",
      "amount": 10000,
      "entry_apy": 15.2,
      "current_apy": 13.8,
      "apy_delta": -1.4,
      "apy_delta_pct": -9.2,
      "entry_timestamp": 1728234567.89
    }
  ],
  "total_positions": 1
}
```

---

## Usage Examples

### Example 1: Alert on APY Drop
Set up an alert to notify you when a high-yield vault's APY drops significantly:

```bash
curl -X POST http://localhost:8000/api/defi-vaults/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "pool_id": "stream-finance-xusd",
    "alert_type": "apy_drop",
    "threshold": 15,
    "notification_method": "webhook",
    "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK"
  }'
```

**When triggered:**
```json
{
  "alert_id": "xyz123",
  "pool_id": "stream-finance-xusd",
  "vault_name": "Stream Finance USDC",
  "protocol": "Stream Finance",
  "chain": "Ethereum",
  "current_apy": 10.5,
  "message": "APY dropped 30.5% (from 15.2% to 10.5%)",
  "timestamp": "2025-10-06T15:23:45Z",
  "defillama_url": "https://defillama.com/yields/pool/..."
}
```

### Example 2: Alert on High APY Opportunities
Get notified when any vault exceeds 20% APY:

```bash
curl -X POST http://localhost:8000/api/defi-vaults/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "pool_id": "morpho-blue-re-7-wsteth-dai-0xec13d3",
    "alert_type": "apy_above",
    "threshold": 20,
    "notification_method": "webhook",
    "webhook_url": "https://hooks.slack.com/services/YOUR_WEBHOOK"
  }'
```

### Example 3: Track Your Position
Monitor your active position:

```bash
curl -X POST http://localhost:8000/api/defi-vaults/positions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "0xYourWalletAddress",
    "pool_id": "stream-finance-xusd",
    "amount": 50000,
    "entry_apy": 15.2
  }'
```

Then check it periodically:
```bash
curl http://localhost:8000/api/defi-vaults/positions/0xYourWalletAddress
```

### Example 4: View APY History
See how a vault's APY has changed over the last 24 hours:

```bash
curl http://localhost:8000/api/defi-vaults/history/stream-finance-xusd?hours=24
```

---

## Discord Webhook Setup

1. Go to your Discord server → Server Settings → Integrations → Webhooks
2. Create a new webhook
3. Copy the webhook URL
4. Use it in your alert configuration

**Example Discord notification:**
> 🚨 **DeFi Vault Alert**
> 
> **Vault:** Stream Finance USDC (Ethereum)  
> **Current APY:** 10.5%  
> **Message:** APY dropped 30.5% (from 15.2% to 10.5%)
> 
> [View on DeFiLlama](https://defillama.com/yields/pool/...)

---

## Monitoring Strategy

### For High-Yield Hunters
1. Set `apy_above` alerts at your target threshold (e.g., 20%)
2. Get notified immediately when opportunities arise
3. Move quickly before APY normalizes

### For Active Position Management
1. Track your positions with entry APY
2. Set `apy_drop` alerts at -15% or -20%
3. Exit when yields decline significantly

### For Risk Management
1. Monitor `outlier` flags in vault data
2. Set `apy_spike` alerts to catch unsustainable yields
3. Check `apy_base_inception` for long-term sustainability

---

## Data Accuracy

- **APY updates:** Every 5 minutes
- **Alert cooldown:** 15 minutes between duplicate alerts
- **Historical data:** 7 days rolling window
- **Data source:** DeFiLlama Yields API (live data)

⚠️ **Note:** Platform fees, performance fees, and withdrawal periods are NOT available from DeFiLlama API and are shown as `null`. Check protocol documentation for these details.

---

## Future Enhancements

- [ ] WebSocket streaming for real-time APY updates
- [ ] Email notifications
- [ ] Telegram bot integration
- [ ] On-chain position verification
- [ ] Gas cost estimator for position changes
- [ ] Multi-vault comparison alerts ("Alert if Vault A APY < Vault B APY")
- [ ] APY prediction using ML models
- [ ] Smart rebalancing recommendations
