"""
Real-time monitor for strategy signals and trades
"""
import sqlite3
import time
from datetime import datetime

DB_PATH = 'data/strategies.db'

def monitor_signals():
    """Monitor signals in real-time"""
    print("\n" + "="*80)
    print("📡 LIVE SIGNAL & TRADE MONITOR")
    print("="*80)
    print("Watching database for new signals and trades...")
    print("Press Ctrl+C to stop\n")
    
    last_signal_count = 0
    last_trade_count = 0
    
    try:
        while True:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Check for new signals
            cursor.execute('SELECT COUNT(*) FROM strategy_signals')
            current_signal_count = cursor.fetchone()[0]
            
            if current_signal_count > last_signal_count:
                # New signals detected!
                new_count = current_signal_count - last_signal_count
                print(f"\n🆕 {new_count} NEW SIGNAL(S) DETECTED!")
                
                # Get the latest signals
                cursor.execute('''
                    SELECT symbol, signal_type, price, reason, timestamp
                    FROM strategy_signals
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (new_count,))
                
                for row in cursor.fetchall():
                    symbol, sig_type, price, reason, ts = row
                    print(f"  ├─ {symbol}: {sig_type} @ ${price:,.2f}")
                    print(f"  │  Reason: {reason}")
                    print(f"  └─ Time: {ts}")
                
                last_signal_count = current_signal_count
            
            # Check for new trades
            cursor.execute('SELECT COUNT(*) FROM strategy_trades')
            current_trade_count = cursor.fetchone()[0]
            
            if current_trade_count > last_trade_count:
                # New trades detected!
                new_count = current_trade_count - last_trade_count
                print(f"\n💰 {new_count} NEW TRADE(S) EXECUTED!")
                
                # Get the latest trades
                cursor.execute('''
                    SELECT symbol, side, quantity, price, status, timestamp
                    FROM strategy_trades
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (new_count,))
                
                for row in cursor.fetchall():
                    symbol, side, qty, price, status, ts = row
                    total = qty * price
                    print(f"  ├─ {symbol}: {side} {qty:.6f} @ ${price:,.2f} = ${total:,.2f}")
                    print(f"  │  Status: {status}")
                    print(f"  └─ Time: {ts}")
                
                last_trade_count = current_trade_count
            
            conn.close()
            
            # Show status every 10 seconds
            now = datetime.now().strftime('%H:%M:%S')
            print(f"\r[{now}] Signals: {current_signal_count} | Trades: {current_trade_count}", end='', flush=True)
            
            time.sleep(2)  # Check every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\n✅ Monitor stopped")
        
        # Final summary
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM strategy_signals')
        total_signals = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM strategy_trades')
        total_trades = cursor.fetchone()[0]
        
        print(f"\nFinal Stats:")
        print(f"  Total Signals: {total_signals}")
        print(f"  Total Trades: {total_trades}")
        
        conn.close()

if __name__ == "__main__":
    monitor_signals()
