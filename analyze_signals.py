"""Check recent signals and understand why no positions opened"""
import sqlite3

conn = sqlite3.connect('data/strategies.db')
cursor = conn.cursor()

print("\n" + "="*80)
print("LAST 5 SIGNALS FROM DATABASE")
print("="*80)

cursor.execute('''
    SELECT timestamp, symbol, signal_type, price, reason 
    FROM strategy_signals 
    ORDER BY timestamp DESC 
    LIMIT 5
''')

signals = cursor.fetchall()

if not signals:
    print("\n❌ No signals in database")
else:
    for i, row in enumerate(signals, 1):
        timestamp, symbol, sig_type, price, reason = row
        print(f"\n{i}. {symbol} - {sig_type} @ ${price:.2f}")
        print(f"   Time: {timestamp}")
        print(f"   Reason: {reason[:120]}")

print("\n" + "="*80)
print("KEY INSIGHT:")
print("="*80)
print("""
The signals show BUY and SELL, but these are being saved AFTER the action
is mapped. The actual action types being sent to StrategyExecutor are:
  - 'open_long' or 'open_short' (to open positions)
  - 'close_long' or 'close_short' (to close positions)

BUT: Positions only open if:
1. The action has proper 'pos_size' field
2. The StrategyExecutor is in 'paper' mode (not 'dry')
3. The position tracking in dashboard is working

Let me check if positions were actually created but not tracked...
""")

conn.close()

# Check trades table too
conn = sqlite3.connect('data/strategies.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM strategy_trades')
trade_count = cursor.fetchone()[0]

print(f"\nTrades in database: {trade_count}")

if trade_count > 0:
    cursor.execute('SELECT symbol, side, price, pnl, timestamp FROM strategy_trades ORDER BY timestamp DESC LIMIT 3')
    print("\nRecent trades:")
    for row in cursor.fetchall():
        print(f"  - {row[0]} {row[1]} @ ${row[2]:.2f}, P&L: ${row[3]:.2f}")
else:
    print("  ❌ No trades yet (positions haven't closed)")

conn.close()
