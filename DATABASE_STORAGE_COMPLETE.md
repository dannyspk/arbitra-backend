# Strategy Database - Complete Data Storage

## Overview

Yes! The SQLite database (`strategies.db`) now stores **EVERYTHING**:
- ✅ Strategy configurations
- ✅ **Signals generated**
- ✅ **Trades executed**
- ✅ **Performance metrics**
- ✅ **Complete audit trail**

---

## Database Tables

### 1. `active_strategies` - Running Strategies
**What it stores:** Currently active strategy configurations

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Trading pair (e.g., 'BTCUSDT') |
| strategy_type | TEXT | Strategy mode ('scalp', 'range', etc.) |
| exchange | TEXT | Exchange name |
| config | JSON | Full strategy parameters |
| started_at | TEXT | When strategy was started |
| last_active | TEXT | Last heartbeat timestamp |
| status | TEXT | 'running' or 'stopped' |

**Example:**
```json
{
  "symbol": "BTCUSDT",
  "strategy_type": "scalp",
  "exchange": "binance",
  "config": {"mode": "scalp", "interval": "15m"},
  "started_at": "2025-10-11T10:00:00",
  "status": "running"
}
```

---

### 2. `strategy_signals` 🆕 - All Signals Generated
**What it stores:** Every BUY/SELL signal the strategy generates

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Trading pair |
| strategy_type | TEXT | Strategy that generated it |
| signal_type | TEXT | 'BUY', 'SELL', 'CLOSE' |
| price | REAL | Price at signal time |
| reason | TEXT | Why signal was generated |
| indicators | JSON | Indicator values (RSI, MACD, etc.) |
| timestamp | TEXT | When signal was generated |
| executed | BOOLEAN | Was this signal acted upon? |

**Example:**
```json
{
  "symbol": "BTCUSDT",
  "strategy_type": "scalp",
  "signal_type": "BUY",
  "price": 43250.50,
  "reason": "RSI oversold + MACD crossover",
  "indicators": {
    "rsi": 28.5,
    "macd": -150.2,
    "volume_spike": 2.3
  },
  "timestamp": "2025-10-11T10:15:30",
  "executed": true
}
```

**Usage:**
```python
from src.arbitrage.strategy_persistence import save_signal

# When strategy generates a signal
save_signal(
    symbol="BTCUSDT",
    strategy_type="scalp",
    signal_type="BUY",
    price=43250.50,
    reason="RSI oversold",
    indicators={"rsi": 28.5, "macd": -150.2}
)
```

---

### 3. `strategy_trades` 🆕 - All Trades Executed
**What it stores:** Every actual trade/order placed

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Trading pair |
| strategy_type | TEXT | Strategy that placed trade |
| exchange | TEXT | Exchange where trade executed |
| side | TEXT | 'BUY' or 'SELL' |
| order_type | TEXT | 'MARKET', 'LIMIT', etc. |
| quantity | REAL | Amount traded |
| price | REAL | Execution price |
| order_id | TEXT | Exchange order ID |
| status | TEXT | 'FILLED', 'PARTIAL', 'CANCELLED' |
| fee | REAL | Trading fee paid |
| fee_currency | TEXT | Fee currency |
| pnl | REAL | Realized PnL (for closing trades) |
| timestamp | TEXT | When trade executed |

**Example:**
```json
{
  "symbol": "BTCUSDT",
  "strategy_type": "scalp",
  "exchange": "binance",
  "side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.05,
  "price": 43250.50,
  "order_id": "1234567890",
  "status": "FILLED",
  "fee": 2.16,
  "fee_currency": "USDT",
  "pnl": null,
  "timestamp": "2025-10-11T10:15:35"
}
```

**Usage:**
```python
from src.arbitrage.strategy_persistence import save_trade

# When trade is executed
save_trade(
    symbol="BTCUSDT",
    strategy_type="scalp",
    exchange="binance",
    side="BUY",
    order_type="MARKET",
    quantity=0.05,
    price=43250.50,
    order_id="1234567890",
    fee=2.16,
    fee_currency="USDT"
)
```

---

### 4. `strategy_metrics` 🆕 - Performance Metrics
**What it stores:** Strategy performance data (daily PnL, win rate, etc.)

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Trading pair |
| strategy_type | TEXT | Strategy type |
| metric_type | TEXT | 'daily_pnl', 'win_rate', 'sharpe', etc. |
| metric_value | REAL | Numeric value |
| details | JSON | Additional metric data |
| timestamp | TEXT | When metric was calculated |

**Example:**
```json
{
  "symbol": "BTCUSDT",
  "strategy_type": "scalp",
  "metric_type": "daily_pnl",
  "metric_value": 125.50,
  "details": {
    "total_trades": 15,
    "winning_trades": 10,
    "losing_trades": 5
  },
  "timestamp": "2025-10-11T23:59:59"
}
```

---

### 5. `strategy_history` - Stopped Strategies
**What it stores:** Archive of all past strategies

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Trading pair |
| strategy_type | TEXT | Strategy mode |
| started_at | TEXT | When started |
| stopped_at | TEXT | When stopped |
| reason | TEXT | Why stopped |
| pnl | REAL | Total PnL |
| trades_count | INTEGER | Number of trades |

---

## Query Functions Available

### Get Signals
```python
from src.arbitrage.strategy_persistence import get_strategy_signals

# Get last 100 signals for BTCUSDT
signals = get_strategy_signals(symbol="BTCUSDT", limit=100)

# Get last 50 signals across all strategies
all_signals = get_strategy_signals(limit=50)
```

### Get Trades
```python
from src.arbitrage.strategy_persistence import get_strategy_trades

# Get last 100 trades for BTCUSDT
trades = get_strategy_trades(symbol="BTCUSDT", limit=100)

# Get all recent trades
all_trades = get_strategy_trades(limit=200)
```

### Get Performance Stats
```python
from src.arbitrage.strategy_persistence import get_strategy_performance

# Get comprehensive stats for a strategy
stats = get_strategy_performance("BTCUSDT")

# Returns:
{
  "symbol": "BTCUSDT",
  "total_trades": 45,
  "buy_count": 23,
  "sell_count": 22,
  "winning_trades": 30,
  "losing_trades": 15,
  "win_rate": 66.67,
  "total_pnl": 523.45,
  "avg_pnl": 11.63,
  "max_win": 75.30,
  "max_loss": -25.10,
  "total_fees": 45.20,
  "total_signals": 120,
  "executed_signals": 45,
  "signal_execution_rate": 37.5
}
```

---

## Integration with Live Strategy

Your live strategy code needs to call these functions when:

**1. Signal Generated:**
```python
# In live_strategy.py when signal is generated
save_signal(
    symbol=self.symbol,
    strategy_type=self.mode,
    signal_type="BUY",  # or "SELL"
    price=current_price,
    reason="RSI oversold + MACD bullish",
    indicators={"rsi": rsi_value, "macd": macd_value}
)
```

**2. Trade Executed:**
```python
# In live_strategy.py after order fills
save_trade(
    symbol=self.symbol,
    strategy_type=self.mode,
    exchange="binance",
    side=order['side'],
    order_type=order['type'],
    quantity=order['executedQty'],
    price=order['price'],
    order_id=order['orderId'],
    status=order['status'],
    fee=order['fee'],
    fee_currency="USDT"
)
```

**3. Position Closed (Calculate PnL):**
```python
# Update trade with realized PnL
# This requires tracking entry/exit prices
```

---

## View Your Data

### Using SQLite Command Line:
```bash
# View active strategies
sqlite3 data/strategies.db "SELECT * FROM active_strategies;"

# View recent signals
sqlite3 data/strategies.db "SELECT * FROM strategy_signals ORDER BY timestamp DESC LIMIT 10;"

# View recent trades
sqlite3 data/strategies.db "SELECT * FROM strategy_trades ORDER BY timestamp DESC LIMIT 10;"

# View performance summary
sqlite3 data/strategies.db "
  SELECT 
    symbol,
    COUNT(*) as trades,
    SUM(pnl) as total_pnl,
    AVG(pnl) as avg_pnl
  FROM strategy_trades 
  WHERE pnl IS NOT NULL 
  GROUP BY symbol;
"
```

### Using Python:
```python
from src.arbitrage.strategy_persistence import (
    get_strategy_signals,
    get_strategy_trades,
    get_strategy_performance
)

# Get last 10 signals
signals = get_strategy_signals(symbol="BTCUSDT", limit=10)
for sig in signals:
    print(f"{sig['timestamp']}: {sig['signal_type']} @ ${sig['price']}")

# Get last 10 trades
trades = get_strategy_trades(symbol="BTCUSDT", limit=10)
for trade in trades:
    print(f"{trade['timestamp']}: {trade['side']} {trade['quantity']} @ ${trade['price']}")

# Get performance
perf = get_strategy_performance("BTCUSDT")
print(f"Win Rate: {perf['win_rate']:.2f}%")
print(f"Total PnL: ${perf['total_pnl']:.2f}")
```

---

## Summary

### ✅ What Gets Stored:

| Data Type | Table | Auto-Saved? |
|-----------|-------|-------------|
| Strategy Config | `active_strategies` | ✅ Yes (on start/stop) |
| Signals Generated | `strategy_signals` | ⚠️ Needs integration |
| Trades Executed | `strategy_trades` | ⚠️ Needs integration |
| Performance Metrics | `strategy_metrics` | ⚠️ Needs integration |
| Strategy History | `strategy_history` | ✅ Yes (on stop) |

### 📝 Next Steps:

1. **Already Working:**
   - Strategy configs persist on start/stop
   - Auto-restore on restart
   - Strategy history tracking

2. **Needs Integration:**
   - Call `save_signal()` when signals are generated
   - Call `save_trade()` when trades execute
   - Call `save_metric()` for performance tracking

3. **Benefits:**
   - Complete audit trail of all trading activity
   - Performance analysis and backtesting
   - Regulatory compliance
   - Debug trade execution
   - Optimize strategies based on historical data

The database structure is ready - now your live strategy code just needs to call the save functions! 🚀
