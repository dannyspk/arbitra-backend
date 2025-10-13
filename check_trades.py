import sqlite3

conn = sqlite3.connect('data/strategies.db')
c = conn.cursor()

c.execute('SELECT timestamp, symbol, side, quantity, price, pnl, fee FROM strategy_trades ORDER BY timestamp DESC')
print('\nAll trades in database:')
for row in c.fetchall():
    ts, symbol, side, qty, price, pnl, fee = row
    print(f'{ts} | {symbol} {side} | Qty: {qty:.4f} @ ${price:.4f} | P&L: ${pnl:.2f} | Fee: ${fee:.4f}')

conn.close()
