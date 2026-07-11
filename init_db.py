import sqlite3

def initialize_database():
    # Connect to the target local database file
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    print("Initializing SQLite relational engine schemas...")

    # 1. Clear out historic experimental layouts if they exist
    cursor.execute("DROP TABLE IF EXISTS history")
    cursor.execute("DROP TABLE IF EXISTS transactions")
    cursor.execute("DROP TABLE IF EXISTS holdings")
    cursor.execute("DROP TABLE IF EXISTS users")

    # 2. Build the Core Users Table
    # Tracks liquid cash positions and account credentials
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            cash NUMERIC NOT NULL DEFAULT 10000.00,
            last_logout_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 3. Build the Active Holdings Table
    # Tracks current asset exposure, positions, and cost bases
    cursor.execute("""
        CREATE TABLE holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            shares INTEGER NOT NULL,
            average_price NUMERIC NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(user_id, ticker)
        )
    """)

    # 4. Build the Targeted Watchlist Table
    # Tracks up to six user-selected symbols for the terminal star action
    cursor.execute("""
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(user_id, ticker)
        )
    """)

    # 5. Build the Automatic Trading Rules Table
    # Stores price-triggered orders that the profile page manages
    cursor.execute("""
        CREATE TABLE auto_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            shares INTEGER NOT NULL,
            target_price REAL NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            paused_reason TEXT,
            last_executed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 6. Build the Transaction Ledger Table
    # Stores the real trade history rendered by the dashboard ledger
    cursor.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            type TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price NUMERIC NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 7. Inject a Default Baseline Seed User for Development Profile Routing
    # This matches the user_id = 1 context used across your search and trade views
    cursor.execute("""
        INSERT INTO users (username, hash, cash) 
        VALUES ('cs50_student', 'mock_secure_hash_value', 10000.00)
    """)

    conn.commit()
    conn.close()
    print("Database infrastructure successfully constructed with seed records.")

if __name__ == "__main__":
    initialize_database()