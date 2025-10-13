"""Check open positions that will become trades when closed"""
from src.arbitrage.live_dashboard import get_dashboard
import time

dashboard = get_dashboard()
positions = dashboard.get_all_positions()

print("\n" + "="*80)
print("OPEN POSITIONS (Will become trades when closed)")
print("="*80)

if not positions:
    print("\n❌ No open positions found")
    print("\n💡 This means:")
    print("   - Signals were generated but didn't open positions, OR")
    print("   - Positions were opened and already closed (check if trades exist)")
else:
    print(f"\n✅ Found {len(positions)} open position(s):\n")
    
    for i, pos in enumerate(positions, 1):
        print(f"{i}. {pos.symbol}")
        print(f"   Side: {pos.side.upper()}")
        print(f"   Entry Price: ${pos.entry_price:.4f}")
        print(f"   Size: {pos.size}")
        print(f"   Unrealized P&L: ${pos.unrealized_pnl:.2f} ({pos.unrealized_pnl_pct:.2f}%)")
        
        # Calculate time held
        entry_time_sec = pos.entry_time / 1000  # Convert ms to seconds
        time_held_min = (time.time() - entry_time_sec) / 60
        print(f"   Time Held: {time_held_min:.1f} minutes")
        print(f"   Will close at: 10 minutes OR 0.5% profit OR stop loss")
        print()

print("="*80)
print("\n📊 Check trades table:")
print("   python check_database.py")
print("\n💾 Trades are saved when positions close!")
print("="*80 + "\n")
