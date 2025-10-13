# Strategy Persistence Issue & Solution

## Problem

Strategies started on Railway disappear after a few hours because:

1. **In-Memory Storage**: Strategies are stored in `_live_strategy_instances = {}` dictionary
2. **Container Restarts**: Railway can restart containers for several reasons:
   - New deployments
   - Memory limit exceeded
   - Application crashes
   - Platform maintenance
3. **Lost State**: When container restarts, all in-memory data is lost

## Solution Options

### Option 1: SQLite Database (Recommended for Railway)
- Persist strategy configs to SQLite file
- Mount Railway volume to persist the database file
- Auto-restore strategies on startup

### Option 2: PostgreSQL (Best for Production)
- Use Railway's PostgreSQL addon
- Store strategy configs in database
- More reliable for multi-instance deployments

### Option 3: JSON File Persistence
- Simple file-based persistence
- Save configs to JSON file
- Restore on startup
- Works but less robust than database

## Implementation Plan

I'll implement **Option 1 (SQLite)** as it's the best balance for Railway:

### Files to Create/Modify:
1. `src/arbitrage/strategy_persistence.py` - Persistence layer
2. `src/arbitrage/web.py` - Add auto-restore on startup
3. Update Railway volume configuration

### What Will Be Persisted:
- Strategy symbol
- Strategy type (scalp, range, breakout, etc.)
- Configuration parameters
- Exchange
- API credentials reference
- Start time
- Last active time

### Auto-Recovery:
- On startup, check for persisted strategies
- Restore each strategy with saved config
- Resume monitoring and trading

## Railway Volume Configuration

Add to `railway.toml`:
```toml
[deploy]
startCommand = "uvicorn src.arbitrage.web:app --host 0.0.0.0 --port $PORT"

[[deploy.healthcheck]]
path = "/health"
timeout = 300

[volumes]
data = "/app/data"
```

This ensures the SQLite database persists across restarts.

## Alternative: Health Monitoring

If strategies disappearing is due to **crashes**, we also need:
1. Better error handling in strategy code
2. Health check endpoint for Railway
3. Logging to track why restarts happen

## Next Steps

Would you like me to:
1. ✅ Implement SQLite persistence layer
2. ✅ Add auto-restore on startup
3. ✅ Configure Railway volume mounting
4. ✅ Add health monitoring

Or would you prefer a different approach?
