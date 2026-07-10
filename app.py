import os
import sqlite3
from flask import Flask, render_template, url_for, jsonify, request, redirect, flash
import yfinance as yf

app = Flask(__name__)
app.secret_key = "smortrade_local_dev_secret_key"

def get_db_connection():
    """Establishes an active reference connection to the SQLite database."""
    conn = sqlite3.connect("database.db", timeout=10)
    conn.row_factory = sqlite3.Row
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
    """Renders the standalone trading workspace with live tracking blocks."""
    conn = get_db_connection()
    
    # 1. Grab user balance information
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    
    # 2. Grab all positions to calculate real-time values
    holdings_rows = conn.execute("SELECT * FROM holdings WHERE user_id = 1").fetchall()
    
    portfolio_holdings = []
    total_portfolio_value = user['cash']

    if holdings_rows:
        # Extract tickers to fetch live prices in bulk
        tickers = [row['ticker'] for row in holdings_rows]
        try:
            api_data = yf.Tickers(" ".join(tickers))
            for row in holdings_rows:
                ticker = row['ticker']
                info = api_data.tickers[ticker].info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose') or 0.0
                
                position_value = row['shares'] * current_price
                total_portfolio_value += position_value
                
                portfolio_holdings.append({
                    "ticker": ticker,
                    "shares": row['shares'],
                    "avg_price": row['average_price'],
                    "current_price": round(current_price, 2),
                    "total_value": round(position_value, 2)
                })
        except Exception as e:
            print(f"Holdings API error: {e}")
            # Fallback values if offline
            for row in holdings_rows:
                portfolio_holdings.append({
                    "ticker": row['ticker'], "shares": row['shares'], 
                    "avg_price": row['average_price'], "current_price": row['average_price'], 
                    "total_value": row['shares'] * row['average_price']
                })

    # Sort holdings by total value descending and slice the top 4 for the charts
    top_4_charts = sorted(portfolio_holdings, key=lambda x: x['total_value'], reverse=True)[:4]

    # 3. Dynamic Hot Stocks Stream for Right Sidebar
    hot_tickers = ["NVDA", "AAPL", "TSLA", "AMD", "MSFT"]
    hot_stocks = []
    try:
        hot_api = yf.Tickers(" ".join(hot_tickers))
        for ticker in hot_tickers:
            info = hot_api.tickers[ticker].info
            price = info.get('regularMarketPrice') or info.get('currentPrice') or 0.0
            open_p = info.get('regularMarketOpen') or price or 1.0
            change = ((price - open_p) / open_p) * 100
            hot_stocks.append({
                "ticker": ticker,
                "price": round(price, 2),
                "change": round(change, 2)
            })
    except Exception:
        hot_stocks = [{"ticker": t, "price": 0.0, "change": 0.0} for t in hot_tickers]

    conn.close()

    return render_template(
        "search.html",
        cash=round(user['cash'], 2),
        total_value=round(total_portfolio_value, 2),
        holdings=portfolio_holdings,
        top_charts=top_4_charts,
        hot_stocks=hot_stocks
    )

@app.route('/stock/<ticker>/data')
def stock_dashboard(ticker):
    # Pass ticker to template; data will be fetched client-side via JavaScript
    return render_template('stock_detail.html', ticker=ticker.upper())

@app.route('/api/stock/<ticker>/data')
def get_stock_data(ticker):
    period = request.args.get('period', '1d')
    
    # Map periods to valid yfinance intervals
    interval_map = {
        '1d': '1m',   # 1-minute data for today
        '5d': '5m',   # 5-minute data for the week
        '1mo': '30m', # 30-minute data for the month
        '1y': '1d'    # Daily data for the year
    }
    interval = interval_map.get(period, '1d')
    
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        
        if df.empty:
            return jsonify({'error': 'No data found'}), 404
            
        # Format timestamps correctly for the chart
        if period == '1d' or period == '5d':
            labels = df.index.strftime('%H:%M').tolist()
        else:
            labels = df.index.strftime('%Y-%m-%d').tolist()
            
        numeric_data = {
            'labels': labels,
            'prices': [round(x, 2) for x in df['Close'].tolist()],
            'volumes': df['Volume'].tolist(),
            'current_price': round(stock.fast_info.get('lastPrice', df['Close'].iloc[-1]), 2),
            'open': round(df['Open'].iloc[0], 2),
            'high': round(df['High'].max(), 2),
            'low': round(df['Low'].min(), 2)
        }
        return jsonify(numeric_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route("/trade", methods=["POST"])
def execute_trade():
    action = request.form.get("action")       
    ticker = request.form.get("ticker").upper() 
    
    try:
        quantity = int(request.form.get("quantity"))
    except (ValueError, TypeError):
        flash("Invalid quantity entered.", "error")
        return redirect("/search")

    if quantity <= 0:
        flash("Quantity must be greater than 0.", "error")
        return redirect("/search")

    # ... rest of your validation logic ...
    if action == "SELL":
        row = db.execute("SELECT shares FROM portfolio WHERE user_id = ? AND ticker = ?", user_id, ticker)
        
        if not row:
            flash(f"You do not own any shares of {ticker}.", "error")
            return redirect("/search")
            
        shares_owned = row[0]["shares"]
        if quantity > shares_owned:
            flash(f"Insufficient shares. You only hold {shares_owned} shares.", "error")
            return redirect("/search")

@app.route("/analytics")
def analytics_page():
    """Calculates portfolio performance statistics and asset distributions."""
    conn = get_db_connection()
    
    # 1. Fetch baseline user context
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    cash = user['cash']
    
    # 2. Extract active holdings to calculate valuation and weights
    holdings_rows = conn.execute("SELECT * FROM holdings WHERE user_id = 1").fetchall()
    
    allocation_labels = ["Cash"]
    allocation_data = [round(cash, 2)]
    stock_value_total = 0
    holdings_list = []
    
    if holdings_rows:
        tickers = [row['ticker'] for row in holdings_rows]
        try:
            api_data = yf.Tickers(" ".join(tickers))
            for row in holdings_rows:
                ticker = row['ticker']
                info = api_data.tickers[ticker].info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose') or 0.0
                
                pos_value = row['shares'] * current_price
                stock_value_total += pos_value
                
                allocation_labels.append(ticker)
                allocation_data.append(round(pos_value, 2))
                
                # Performance calculations per asset
                cost_basis = row['shares'] * row['average_price']
                total_return = pos_value - cost_basis
                return_pct = (total_return / cost_basis) * 100 if cost_basis > 0 else 0
                
                holdings_list.append({
                    "ticker": ticker,
                    "shares": row['shares'],
                    "avg_price": round(row['average_price'], 2),
                    "current_price": round(current_price, 2),
                    "total_value": round(pos_value, 2),
                    "return_amt": round(total_return, 2),
                    "return_pct": round(return_pct, 2)
                })
        except Exception:
            # Offline / API Limit fallback structure
            for row in holdings_rows:
                pos_value = row['shares'] * row['average_price']
                stock_value_total += pos_value
                allocation_labels.append(row['ticker'])
                allocation_data.append(round(pos_value, 2))
                holdings_list.append({
                    "ticker": row['ticker'], "shares": row['shares'], "avg_price": round(row['average_price'], 2),
                    "current_price": round(row['average_price'], 2), "total_value": round(pos_value, 2),
                    "return_amt": 0.0, "return_pct": 0.0
                })

    net_portfolio_value = cash + stock_value_total

    # 3. Compile mock timeline tracking vector for the Equity curve chart
    # In production, this can pull from a historical snapshots DB table
    equity_labels = ["Jun 30", "Jul 01", "Jul 02", "Jul 03", "Jul 04", "Today"]
    equity_trend = [
        round(net_portfolio_value * 0.95, 2),
        round(net_portfolio_value * 0.97, 2),
        round(net_portfolio_value * 0.96, 2),
        round(net_portfolio_value * 1.02, 2),
        round(net_portfolio_value * 0.99, 2),
        round(net_portfolio_value, 2)
    ]

    # 4. Generate core KPI Performance score card values
    # These mock values represent aggregate statistics from historical orders
    performance_kpis = {
        "win_rate": 62.5,
        "profit_factor": 1.74,
        "total_trades": len(holdings_list) + 4, # Active plus example historic
        "net_profit": round(stock_value_total * 0.05, 2)
    }

    conn.close()

    return render_template(
        "analytics.html",
        net_value=round(net_portfolio_value, 2),
        allocation_labels=allocation_labels,
        allocation_data=allocation_data,
        equity_labels=equity_labels,
        equity_trend=equity_trend,
        kpis=performance_kpis,
        holdings=holdings_list
    )

@app.route("/news")
def news_page():
    """Renders real-time financial updates with extensive descriptive analysis."""
    
    puzzle_news_feed = [
        {
            "title": "Fed Signals Stable Policy Shifts Amid Balanced Q2 Inflation Vectors",
            "summary": "Central banking authorities indicate that current interest rate parameters are sufficiently restrictive to guide inflation targets back to baseline projections. Market analysts suggest this extended freeze provides stability for large-cap tech portfolios looking to lock in long-term capital structures without debt expansion pressure.",
            "source": "Macro Analytics", "time_elapsed": "14m ago",
            "image_url": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=800&q=80",
            "url": "https://example.com/news-1"
        },
        {
            "title": "Semiconductor Demands Hit Seasonal Highs as Orders Surge",
            "summary": "Global manufacturing lines are rapidly adjusting factory outputs upward following a massive wave of advanced infrastructure orders from cloud enterprise networks. This unexpected demand spike has driven commodity component prices up by nearly fifteen percent, boosting margins across major hardware producers.",
            "source": "Tech Sector Tracker", "time_elapsed": "28m ago",
            "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=500&q=80",
            "url": "https://example.com/news-2"
        },
        {
            "title": "Global Logistics Metrics Point Toward Stabilizing Supply Routes",
            "summary": "Maritime shipping rates across primary oceanic corridors dropped for the fourth consecutive week, indicating that global supply backlogs are finally clearing out. Retailers are taking advantage of this capacity corrections to pull holiday inventory schedules ahead, avoiding ports bottleneck risks observed last cycle.",
            "source": "Freight Matrix", "time_elapsed": "1h ago",
            "image_url": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=500&q=80",
            "url": "https://example.com/news-3"
        },
        {
            "title": "Crude Volatility Contracts as Reserves Increase",
            "summary": "Energy trading desks reported a tight contraction in standard daily pricing bands after domestic strategic reserves logged an unexpected surplus accumulation. Analysts anticipate that baseline fuel costs will remain anchored through the next quarter, offering a soft operational cost buffer to transportation and airline stocks.",
            "source": "Commodities", "time_elapsed": "2h ago",
            "image_url": "https://images.unsplash.com/photo-1535732820275-9ffd998cac22?auto=format&fit=crop&w=500&q=80",
            "url": "https://example.com/news-4"
        },
        {
            "title": "Retail Transaction Matrix Outperforms Consensus Estimations",
            "summary": "Consumer spending indexes tracking mid-tier retail hubs advanced unexpectedly last month, heavily defying downbeat market forecasts. High-frequency digital wallet records reveal that lower raw commodity prices are effectively unlocking secondary purchasing choices among core household units.",
            "source": "Consumer Index", "time_elapsed": "4h ago",
            "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=500&q=80",
            "url": "https://example.com/news-5"
        },
        {
            "title": "Corporate Bonds Realize Record Volume Inflow Channels",
            "summary": "Institutional funds have reallocated a significant portion of their liquid treasury holdings into highly rated corporate debt issues this week. This movement represents a massive strategic pivot toward locking in favorable premium yield baselines before projected monetary policy updates roll through late next fiscal year.",
            "source": "Fixed Income", "time_elapsed": "5h ago",
            "image_url": "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=500&q=80",
            "url": "https://example.com/news-6"
        }
    ]

    return render_template("news.html", news_list=puzzle_news_feed)

if __name__ == "__main__":
    app.run(debug=True)