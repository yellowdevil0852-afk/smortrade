import sqlite3

def init_database():
    # Connect to the database file (it will be created if it doesn't exist)
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Enable foreign key support in SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("Creating database tables...")

    # 1. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            cash REAL NOT NULL DEFAULT 10000.00,
            last_logout_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Holdings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            shares INTEGER NOT NULL,
            average_price REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(user_id, ticker)
        );
    """)

    # 3. Transactions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            type TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price REAL NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)

    # 4. Watchlist Table (For dynamic customization)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            target_price REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(user_id, ticker)
        );
    """)

    print("Seeding sample data for testing...")

    # Seed a default user if not exists
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, username, cash, last_logout_at) 
        VALUES (1, 'default_user', 12450.80, datetime('now', '-2 hours'));
    """)

    # Seed initial stock positions (Layer 1 metrics verification)
    cursor.execute("DELETE FROM holdings WHERE user_id = 1;")
    cursor.execute("INSERT INTO holdings (user_id, ticker, shares, average_price) VALUES (1, 'AAPL', 10, 172.00);")
    cursor.execute("INSERT INTO holdings (user_id, ticker, shares, average_price) VALUES (1, 'NVDA', 2, 850.00);")

    # Seed transactions (Layer 3 verification)
    cursor.execute("DELETE FROM transactions WHERE user_id = 1;")
    cursor.execute("""
        INSERT INTO transactions (user_id, ticker, type, shares, price, timestamp) 
        VALUES (1, 'NVDA', 'BUY (Auto)', 5, 870.00, '2026-05-27 14:22:00');
    """)
    cursor.execute("""
        INSERT INTO transactions (user_id, ticker, type, shares, price, timestamp) 
        VALUES (1, 'TSLA', 'SELL (Limit)', 10, 182.00, '2026-05-27 11:05:00');
    """)
    cursor.execute("""
        INSERT INTO transactions (user_id, ticker, type, shares, price, timestamp) 
        VALUES (1, 'AAPL', 'BUY (Auto)', 8, 174.50, '2026-05-26 16:00:00');
    """)

    # Seed dynamic targeted watchlist items (Layer 2 verification)
    cursor.execute("DELETE FROM watchlist WHERE user_id = 1;")
    cursor.execute("INSERT INTO watchlist (user_id, ticker, target_price) VALUES (1, 'AAPL', 175.40);")
    cursor.execute("INSERT INTO watchlist (user_id, ticker, target_price) VALUES (1, 'TSLA', 180.25);")
    cursor.execute("INSERT INTO watchlist (user_id, ticker, target_price) VALUES (1, 'NVDA', 875.12);")
    cursor.execute("INSERT INTO watchlist (user_id, ticker, target_price) VALUES (1, 'MSFT', 420.55);")
    cursor.execute("INSERT INTO watchlist (user_id, ticker, target_price) VALUES (1, 'AMD', 170.10);")

    # Commit changes and clean up connection
    conn.commit()
    conn.close()
    print("Database initialization complete! 'database.db' is ready for use.")

if __name__ == "__main__":
    init_database()