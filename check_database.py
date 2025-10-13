"""
Check what's stored in the strategies database
"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = 'data/strategies.db'

if not os.path.exists(DB_PATH):
    print(f"❌ Database not found at: {DB_PATH}")
    exit(1)

print(f"✅ Database found at: {DB_PATH}")
print(f"File size: {os.path.getsize(DB_PATH)} bytes")
print("\n" + "="*80)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check active strategies
print("\n📊 ACTIVE STRATEGIES:")
print("="*80)
cursor.execute("SELECT symbol, strategy_type, exchange, config, started_at, status FROM active_strategies")
rows = cursor.fetchall()

if rows:
    for row in rows:
        symbol, strategy_type, exchange, config, started_at, status = row
        config_data = json.loads(config)
        print(f"\nSymbol: {symbol}")
        print(f"  Type: {strategy_type}")
        print(f"  Exchange: {exchange}")
        print(f"  Config: {config_data}")
        print(f"  Started: {started_at}")
        print(f"  Status: {status}")
else:
    print("No active strategies found")

print(f"\nTotal active strategies: {len(rows)}")

# Check signals
print("\n" + "="*80)
print("📡 SIGNALS (if any):")
print("="*80)
cursor.execute("SELECT COUNT(*) FROM strategy_signals")
signal_count = cursor.fetchone()[0]
print(f"Total signals: {signal_count}")

# Check trades
print("\n" + "="*80)
print("💰 TRADES (if any):")
print("="*80)
cursor.execute("SELECT COUNT(*) FROM strategy_trades")
trade_count = cursor.fetchone()[0]
print(f"Total trades: {trade_count}")

# Check history
print("\n" + "="*80)
print("📜 STRATEGY HISTORY:")
print("="*80)
cursor.execute("SELECT symbol, strategy_type, started_at, stopped_at, reason FROM strategy_history ORDER BY stopped_at DESC LIMIT 5")
history_rows = cursor.fetchall()

if history_rows:
    for row in history_rows:
        symbol, strategy_type, started_at, stopped_at, reason = row
        print(f"\n{symbol} ({strategy_type})")
        print(f"  Started: {started_at}")
        print(f"  Stopped: {stopped_at}")
        print(f"  Reason: {reason}")
else:
    print("No strategy history")

conn.close()

print("\n" + "="*80)
print("\n✅ If you see your strategy above, it WILL be restored on server restart!")
print("\n🔄 To test: Restart the Python backend and check the logs for:")
print('    [STARTUP] Restoring X strategies from database...')
print('    [STARTUP] ✓ Restored strategy: YOURSYMBOL')
print("="*80)
