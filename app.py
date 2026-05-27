from flask import Flask, render_template, url_for
import os

app = Flask(__name__)

@app.context_processor
def override_url_for():
    """
    Appends a unique timestamp query parameter to static files 
    to bypass aggressive browser caching.
    """
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
    # Mock data to simulate the visual layout without a live database connection
    metrics = {
        "current_asset": 12450.80,
        "asset_change_percent": 2.45,
        "auto_trades_since_logout": 4,
        "current_holdings_count": 12
    }
    
    targeted_stocks = [
        {"ticker": "AAPL", "price": 175.40, "change": 1.20},
        {"ticker": "TSLA", "price": 180.25, "change": -3.15},
        {"ticker": "NVDA", "price": 875.12, "change": 5.82},
        {"ticker": "MSFT", "price": 420.55, "change": 0.45},
        {"ticker": "AMD", "price": 170.10, "change": -1.10}
    ]
    
    market_news = [
        {"title": "Tech Stocks Rally on Favorable Inflation Reports", "source": "MarketWatch"},
        {"title": "Federal Reserve Hints at Steady Interest Rates This Quarter", "source": "Bloomberg"},
        {"title": "Automated Trading Algorithms See Record Volume Highs", "source": "Reuters"},
        {"title": "Chipmakers Surge Led by Increased Enterprise Hardware Demand", "source": "CNBC"},
        {"title": "Global Logistics Stabilize, Boosting E-Commerce Forecasts", "source": "Financial Times"}
    ]
    
    recent_transactions = [
        {"timestamp": "2026-05-27 14:22", "ticker": "NVDA", "type": "BUY (Auto)", "shares": 5, "price": 870.00, "total": 4350.00},
        {"timestamp": "2026-05-27 11:05", "ticker": "TSLA", "type": "SELL (Limit)", "shares": 10, "price": 182.00, "total": 1820.00},
        {"timestamp": "2026-05-26 16:00", "ticker": "AAPL", "type": "BUY (Auto)", "shares": 8, "price": 174.50, "total": 1396.00}
    ]

    return render_template(
        "index.html", 
        metrics=metrics, 
        targeted_stocks=targeted_stocks, 
        market_news=market_news, 
        recent_transactions=recent_transactions
    )

if __name__ == "__main__":
    app.run(debug=True)