# Why Signals Are Generated But No Trades Execute

## Current Situation

✅ **Signals are being generated** - 8+ signals in database  
❌ **Trades are not being executed** - No trades in database

## Explanation

### Execution Modes

Your strategy is running in **`paper` mode** (controlled by `ARB_LIVE_DEFAULT_EXEC_MODE` environment variable):

1. **`dry` mode**: Pure simulation, no orders at all
2. **`paper` mode** ⬅️ **YOU ARE HERE**
   - Generates signals ✅
   - Saves signals to database ✅
   - Simulates order placement with MockExchange ✅
   - Does NOT execute real Binance trades ❌
   - Tracks positions in memory only
   
3. **`live` mode**: Would execute real trades on Binance (requires proper setup)

### Why Your Aggressive Scalp Strategy Generates Signals But No Trades

The signals you're seeing (COAIUSDT SELL @ $6.66, etc.) are **trading signals**, not actual trade executions.

**Flow:**
1. LiveStrategy analyzes market data
2. Detects trading opportunity (e.g., "sell signal")
3. Calls `_emit_action()` which saves signal to database ✅
4. Calls `StrategyExecutor.process_live_action(execute=True)`
5. StrategyExecutor places **mock order** (not real Binance order)
6. Mock fills are simulated
7. Position is tracked in memory
8. **Trade is NOT saved to database** ❌ (until now - fixed!)

### What Just Changed

I added trade persistence:
- When a position is closed, `save_trade()` is now called
- Trades will be saved to `strategy_trades` table in database
- You'll see trades in the dashboard once positions close

## How To See Actual Trades

### Option 1: Wait for Position to Close
The aggressive scalp strategy will close positions when:
- Price moves 0.5% profit target (take profit)
- Max 10 minutes holding time expires
- Stop loss is hit

**Then you'll see:**
- Trade saved to database with P&L
- "[TRADE SAVED]" in backend logs
- Trade appears in dashboard

### Option 2: Check Current Open Positions
```python
python -c "from src.arbitrage.live_dashboard import get_dashboard; d = get_dashboard(); print(f'Open positions: {len(d.get_all_positions())}'); [print(f'  - {p.symbol} {p.side} @ ${p.entry_price}') for p in d.get_all_positions()]"
```

### Option 3: Enable Real Trading (Advanced)

⚠️ **WARNING: This will execute real trades with real money!**

1. Set environment variable:
   ```
   ARB_LIVE_DEFAULT_EXEC_MODE=live
   ```

2. Ensure Binance API keys are configured correctly

3. Update StrategyExecutor to use real Binance exchange instead of MockExchange

## Summary

**Current Status:**
- ✅ Signal generation working perfectly
- ✅ Signals persisted to database
- ✅ Trade persistence code added
- ⏳ Waiting for positions to close to see completed trades

**Next Steps:**
1. Monitor backend logs for "[TRADE SAVED]" messages
2. Check database after ~10 minutes (max holding time)
3. View trades in dashboard once they complete

**Check Trades:**
```bash
python check_database.py
```

Or query directly:
```sql
SELECT * FROM strategy_trades ORDER BY timestamp DESC LIMIT 5;
```
