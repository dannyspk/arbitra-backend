# Strategy Persistence - Deployment Guide

## What Was Fixed

Strategies now **persist across Railway restarts**. When Railway restarts your container (due to deployment, crash, or maintenance), all active strategies will automatically resume.

## How It Works

### 1. SQLite Database
- Strategies are saved to `/app/data/strategies.db`
- Database persists on Railway's volume mount
- Survives container restarts

### 2. Auto-Restore on Startup
- On app startup, checks database for active strategies
- Automatically restarts each strategy
- Logs restoration status

### 3. Lifecycle Management
- **On Start**: Strategy saved to database
- **On Stop**: Strategy removed from database
- **On Restart**: All active strategies restored

## Deployment Steps

### 1. Commit and Push Changes
```bash
git add .
git commit -m "Add strategy persistence for Railway"
git push origin main
```

### 2. Railway Will Auto-Deploy
Railway will detect the changes and redeploy automatically.

### 3. Volume Configuration

Railway should automatically create the volume based on `railway.toml`. If you need to configure manually:

1. Go to Railway Dashboard → Your Service
2. Click "Settings" tab
3. Scroll to "Volumes"
4. Add volume:
   - **Mount Path**: `/app/data`
   - **Name**: `strategy_data`

### 4. Verify Persistence

After deployment:

1. **Start a strategy** via the dashboard
2. **Check Railway logs** for:
   ```
   Saved strategy: BTCUSDT (scalp)
   ```
3. **Trigger a restart** (redeploy or manual restart)
4. **Check logs again** for:
   ```
   Restoring 1 strategies from database...
   ✓ Restored strategy: BTCUSDT (scalp)
   ```

## Monitoring

### Check Active Strategies
```bash
GET /api/live-strategy/status
```

### Check Logs
```bash
railway logs
```

Look for:
- `Saved strategy: ...` - Strategy persisted
- `Restored strategy: ...` - Strategy resumed after restart
- `Removed strategy: ...` - Strategy stopped and removed

## Database Location

### Railway (Production)
- Path: `/app/data/strategies.db`
- Persisted on volume mount

### Local Development
- Path: `data/strategies.db` (in project root)
- Created automatically if doesn't exist

## Database Schema

### active_strategies
```sql
- id: INTEGER PRIMARY KEY
- symbol: TEXT UNIQUE (e.g., 'BTCUSDT')
- strategy_type: TEXT (e.g., 'scalp', 'range')
- exchange: TEXT (e.g., 'binance')
- config: JSON (strategy parameters)
- started_at: TEXT (ISO timestamp)
- last_active: TEXT (ISO timestamp)
- status: TEXT ('running', 'stopped')
```

### strategy_history
```sql
- id: INTEGER PRIMARY KEY
- symbol: TEXT
- strategy_type: TEXT
- exchange: TEXT
- started_at: TEXT
- stopped_at: TEXT
- reason: TEXT (why it stopped)
- pnl: REAL (profit/loss)
- trades_count: INTEGER
```

## Troubleshooting

### Strategies Not Restoring?

**1. Check Railway Logs**
```bash
railway logs | grep -i "strategy\|restore"
```

**2. Check Volume Mount**
```bash
railway run ls -la /app/data
```

Should show `strategies.db` file.

**3. Manual Database Check**
```bash
# SSH into Railway container
railway run bash

# Check database
cd /app/data
sqlite3 strategies.db "SELECT * FROM active_strategies;"
```

### Database Getting Too Large?

The history table can grow over time. Add periodic cleanup:
```python
# Clean history older than 30 days
DELETE FROM strategy_history 
WHERE stopped_at < datetime('now', '-30 days');
```

## Benefits

✅ **Survive Restarts** - Strategies continue after Railway restarts  
✅ **Zero Downtime** - Auto-resume on deployment  
✅ **Audit Trail** - Full history of all strategies  
✅ **No Manual Work** - Automatic restoration  

## Next Steps

1. Deploy to Railway
2. Start a test strategy
3. Wait for auto-restart (or manually trigger)
4. Verify strategy resumes automatically

The persistence system is now active and will ensure your strategies survive any Railway restarts!
