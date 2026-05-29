import os
import sqlite3
from flask import Flask, render_template, url_for, jsonify
import yfinance as yf

app = Flask(__name__)

def get_db_connection():
    """Establishes an active reference connection to the SQLite database."""
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row  # Enables column fetching by name like a dictionary
    return conn

@app.route("/api/watchlist")
def api_watchlist():
    """Returns real-time watchlist prices as JSON for background updates."""
    conn = get_db_connection()
    watchlist_rows = conn.execute("SELECT ticker FROM watchlist WHERE user_id = 1").fetchall()
    conn.close()

    if not watchlist_rows:
        return jsonify([])

    tickers_list = [row['ticker'] for row in watchlist_rows]
    updated_stocks = []

    try:
        api_data = yf.Tickers(" ".join(tickers_list))
        for ticker in tickers_list:
            info = api_data.tickers[ticker].info
            current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose') or 0.0
            open_price = info.get('regularMarketOpen') or current_price or 1.0
            change_percent = ((current_price - open_price) / open_price) * 100

            updated_stocks.append({
                "ticker": ticker,
                "price": f"${current_price:,.2f}",
                "change": f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                "is_positive": change_percent >= 0
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(updated_stocks)

@app.context_processor
def override_url_for():
    """Automated cache-buster for static assets."""
    def url_with_timestamp(endpoint, **values):
        if endpoint == 'static':
            filename = values.get('filename', None)
            if filename:
                file_path = os.path.join(app.root_path, endpoint, filename)
                try:
                    values['q'] = int(os.stat(file_path).st_mtime)
                except OSError:
                    pass
        return url_for(endpoint, **values)
    return dict(url_for=url_with_timestamp)

@app.route("/")
def index():
    # 1. Fetch user states and logs directly from SQLite database
    conn = get_db_connection()
    
    # Grab details for the default user (id = 1)
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    
    # Calculate Core Metric Numbers for Layer 1
    holdings_count = conn.execute("SELECT COUNT(id) FROM holdings WHERE user_id = 1").fetchone()[0]
    recent_txs_rows = conn.execute(
        "SELECT timestamp, ticker, type, shares, price, (shares * price) as total FROM transactions WHERE user_id = 1 ORDER BY timestamp DESC LIMIT 5"
    ).fetchall()
    
    # Calculate auto-trades executed since the logged logout timestamp
    auto_trades_count = conn.execute(
        "SELECT COUNT(id) FROM transactions WHERE user_id = 1 AND type LIKE '%Auto%' AND timestamp > ?",
        (user['last_logout_at'],)
    ).fetchone()[0]

    # Assemble metrics object dynamically
    metrics = {
        "current_asset": user['cash'],
        "asset_change_percent": 1.18,  # Hardcoded placeholder for layout continuity
        "auto_trades_since_logout": auto_trades_count,
        "current_holdings_count": holdings_count
    }

    # 2. Layer 2: Dynamic Watchlist Processing via Live External API
    watchlist_rows = conn.execute("SELECT ticker FROM watchlist WHERE user_id = 1").fetchall()
    conn.close()

    targeted_stocks = []
    if watchlist_rows:
        # Extract plain string tickers from db rows
        tickers_list = [row['ticker'] for row in watchlist_rows]
        
        try:
            # Query the live network API for all tickers in parallel
            api_data = yf.Tickers(" ".join(tickers_list))
            
            for ticker in tickers_list:
                info = api_data.tickers[ticker].info
                # Safely extract latest price or default to zero if market is closed/null
                current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose') or 0.0
                open_price = info.get('regularMarketOpen') or current_price or 1.0
                
                # Compute live percentage change mathematical formula
                change_percent = ((current_price - open_price) / open_price) * 100
                
                targeted_stocks.append({
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "change": round(change_percent, 2)
                })
        except Exception as e:
            print(f"API Fetch Error: {e}. Falling back to visual layout defaults.")
            # Absolute fallback array to prevent structural app crash if system offline
            targeted_stocks = [{"ticker": t, "price": 0.00, "change": 0.00} for t in tickers_list]

    # Layer 2 Side Column: Standard static news array configuration
    market_news = [
        {"title": "Tech Stocks Rally on Favorable Inflation Reports", "source": "MarketWatch"},
        {"title": "Federal Reserve Hints at Steady Interest Rates This Quarter", "source": "Bloomberg"},
        {"title": "Automated Trading Algorithms See Record Volume Highs", "source": "Reuters"},
        {"title": "Chipmakers Surge Led by Increased Enterprise Hardware Demand", "source": "CNBC"},
        {"title": "Global Logistics Stabilize, Boosting E-Commerce Forecasts", "source": "Financial Times"}
    ]

    return render_template(
        "index.html", 
        metrics=metrics, 
        targeted_stocks=targeted_stocks, 
        market_news=market_news, 
        recent_transactions=recent_txs_rows
    )

@app.route("/search")
def search_page():
    """Renders the dedicated standalone stock search and analysis workspace."""
    return render_template("search.html")

if __name__ == "__main__":
    app.run(debug=True)