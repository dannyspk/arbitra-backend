"""
Monitor backend logs for trade closures in real-time
"""
import time
import subprocess
import sys

print("\n" + "="*80)
print("🔍 MONITORING FOR TRADE CLOSURES")
print("="*80)
print("\nWatching for:")
print("  • [TRADE SAVED] - Trade persisted to database")
print("  • [BALANCE] Position closed - Position closure event")
print("\nPress Ctrl+C to stop\n")

try:
    # Use PowerShell to tail the backend process output
    # Since we can't easily tail a running process, let's check database periodically
    import sqlite3
    
    last_trade_count = 0
    conn = sqlite3.connect('data/strategies.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM strategy_trades')
    last_trade_count = cursor.fetchone()[0]
    conn.close()
    
    print(f"Starting monitor... Current trades in DB: {last_trade_count}\n")
    
    while True:
        conn = sqlite3.connect('data/strategies.db')
        cursor = conn.cursor()
        
        # Check for new trades
        cursor.execute('SELECT COUNT(*) FROM strategy_trades')
        current_count = cursor.fetchone()[0]
        
        if current_count > last_trade_count:
            new_trades = current_count - last_trade_count
            print(f"\n🎉 NEW TRADE(S) DETECTED! ({new_trades} new)")
            
            # Get the latest trade
            cursor.execute('''
                SELECT symbol, side, quantity, price, pnl, status, timestamp
                FROM strategy_trades
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (new_trades,))
            
            for row in cursor.fetchall():
                symbol, side, qty, price, pnl, status, ts = row
                pnl_sign = "+" if pnl >= 0 else ""
                print(f"\n  Symbol: {symbol}")
                print(f"  Side: {side.upper()}")
                print(f"  Exit Price: ${price:.2f}")
                print(f"  Quantity: {qty:.4f}")
                print(f"  P&L: {pnl_sign}${pnl:.2f}")
                print(f"  Status: {status}")
                print(f"  Time: {ts}")
            
            last_trade_count = current_count
        
        conn.close()
        
        # Show heartbeat
        now = time.strftime('%H:%M:%S')
        print(f"\r[{now}] Trades in DB: {current_count} | Waiting for position to close...", end='', flush=True)
        
        time.sleep(2)  # Check every 2 seconds
        
except KeyboardInterrupt:
    print("\n\n✅ Monitoring stopped\n")
except Exception as e:
    print(f"\n\n❌ Error: {e}\n")
