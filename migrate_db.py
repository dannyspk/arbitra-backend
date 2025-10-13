"""
Migrate database to add exit_price column to strategy_trades table
"""
import sqlite3
import os

DB_PATH = 'data/strategies.db'

def migrate_database():
    print(f"Migrating database at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if exit_price column already exists
    cursor.execute("PRAGMA table_info(strategy_trades)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'exit_price' in columns:
        print("✅ exit_price column already exists")
    else:
        print("Adding exit_price column...")
        cursor.execute('''
            ALTER TABLE strategy_trades
            ADD COLUMN exit_price REAL
        ''')
        conn.commit()
        print("✅ exit_price column added successfully")
    
    # Show current schema
    cursor.execute("PRAGMA table_info(strategy_trades)")
    print("\nCurrent schema:")
    for row in cursor.fetchall():
        print(f"  {row[1]} ({row[2]})")
    
    conn.close()
    print("\n✅ Migration complete!")

if __name__ == '__main__':
    migrate_database()
