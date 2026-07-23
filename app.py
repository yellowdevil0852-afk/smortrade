import json
import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, render_template, url_for, jsonify, request, redirect, flash, session
import yfinance as yf
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

app = Flask(__name__)
app.secret_key = "smortrade_local_dev_secret_key"

DEFAULT_HOT_TICKERS = ["NVDA", "AAPL", "TSLA", "AMD", "MSFT"]
HOT_INDICATOR_UNIVERSE = ["NVDA", "AAPL", "TSLA", "AMD", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "SPY", "QQQ", "PLTR", "ORCL", "CRM", "INTC"]
DEFAULT_USER_ID = 1

def get_db_connection():
    """Establishes an active reference connection to the SQLite database."""
    conn = sqlite3.connect("database.db", timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_transactions_table(conn):
    """Create the transactions ledger if this install has not been migrated yet."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            type TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price NUMERIC NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )


def ensure_watchlist_table(conn):
    """Create the targeted watchlist table if this install has not been migrated yet."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            target_price REAL NOT NULL DEFAULT 0.0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(user_id, ticker)
        )
        """
    )


def ensure_user_profile_columns(conn):
    """Return the available columns from the users table for profile rendering."""
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    return {column["name"] for column in columns}


def format_profile_timestamp(value):
    """Format a SQLite timestamp into a compact date for the profile page."""
    if not value:
        return "Unknown"

    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
        return parsed.strftime("%b %d, %Y")
    except ValueError:
        return text.split(" ")[0]


def _compute_transaction_stats(conn):
    """Walk the transaction ledger and derive win/loss and P&L statistics."""
    transaction_rows = conn.execute(
        "SELECT ticker, type, shares, price, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        (DEFAULT_USER_ID,)
    ).fetchall()

    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    position_state = {}

    for row in transaction_rows:
        ticker = (row["ticker"] or "").upper()
        trade_type = (row["type"] or "").upper()
        shares = int(row["shares"] or 0)
        price = float(row["price"] or 0.0)

        state = position_state.get(ticker, {"shares": 0, "cost": 0.0})

        if "BUY" in trade_type:
            state["shares"] += shares
            state["cost"] += shares * price
        elif "SELL" in trade_type:
            average_cost = state["cost"] / state["shares"] if state["shares"] else price
            sold_shares = min(shares, state["shares"]) if state["shares"] else shares
            pnl = (price - average_cost) * sold_shares

            if price > average_cost:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)

            if state["shares"] > 0:
                state["shares"] -= sold_shares
                state["cost"] = max(0.0, state["cost"] - (average_cost * sold_shares))

        position_state[ticker] = state

    return {
        "wins": wins,
        "losses": losses,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_executions": len(transaction_rows),
    }


def build_profile_metrics(conn, user_row):
    """Build the simulated analytics shown on the profile page."""
    transaction_rows = conn.execute(
        "SELECT ticker, type, shares, price, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        (DEFAULT_USER_ID,)
    ).fetchall()

    total_fees_paid = sum(0.99 + (0.005 * float(row["shares"] or 0)) for row in transaction_rows)
    stats = _compute_transaction_stats(conn)
    wins = stats["wins"]
    losses = stats["losses"]

    if len(transaction_rows) == 0:
        win_loss_ratio = "0:0"
    elif losses == 0:
        win_loss_ratio = f"{wins}:0"
    else:
        win_loss_ratio = f"{wins}:{losses}"

    return {
        "win_loss_ratio": win_loss_ratio,
        "total_fees_paid": round(total_fees_paid, 2),
    }


def build_analytics_kpis(conn):
    """Derive live performance KPIs from the transaction ledger."""
    stats = _compute_transaction_stats(conn)
    wins = stats["wins"]
    losses = stats["losses"]
    closed_trades = wins + losses

    if closed_trades == 0:
        win_rate = 0.0
    else:
        win_rate = round((wins / closed_trades) * 100, 1)

    gross_profit = stats["gross_profit"]
    gross_loss = stats["gross_loss"]
    if gross_loss == 0:
        profit_factor = "N/A" if gross_profit == 0 else "∞"
    else:
        profit_factor = round(gross_profit / gross_loss, 2)

    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_trades": stats["total_executions"],
        "net_profit": round(gross_profit - gross_loss, 2),
    }


def ensure_auto_trades_table(conn):
    """Create the automatic trade rules table if this install has not been migrated yet."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_trades (
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
        """
    )


def fetch_auto_trade_rules(conn):
    """Return automatic trade rules for the profile page and runtime evaluation."""
    ensure_auto_trades_table(conn)
    rows = conn.execute(
        "SELECT * FROM auto_trades WHERE user_id = ? ORDER BY enabled DESC, id DESC",
        (DEFAULT_USER_ID,)
    ).fetchall()

    rules = []
    current_cash = None

    for row in rows:
        ticker = (row["ticker"] or "").upper()
        action = (row["action"] or "BUY").upper()
        shares = int(row["shares"] or 0)
        target_price = float(row["target_price"] or 0.0)

        current_price = None
        try:
            current_price = get_live_stock_price(ticker)
        except Exception:
            pass

        if current_cash is None:
            user = conn.execute("SELECT cash FROM users WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()
            current_cash = float(user["cash"] or 0.0) if user else 0.0

        required_cash = round(target_price * shares, 2) if action == "BUY" else 0.0
        holding = conn.execute(
            "SELECT shares FROM holdings WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER_ID, ticker)
        ).fetchone()
        holding_shares = int(holding["shares"] or 0) if holding else 0

        if current_price is None:
            trigger_state = "Waiting for live price"
        elif action == "BUY":
            trigger_state = "Ready" if current_price >= target_price else "Waiting"
        else:
            trigger_state = "Ready" if current_price >= target_price else "Waiting"

        rules.append({
            "id": row["id"],
            "ticker": ticker,
            "action": action,
            "shares": shares,
            "target_price": round(target_price, 2),
            "current_price": round(current_price, 2) if current_price is not None else None,
            "trigger_state": trigger_state,
            "enabled": bool(row["enabled"]),
            "status": row["status"] or ("active" if row["enabled"] else "paused"),
            "paused_reason": row["paused_reason"],
            "last_executed_at": row["last_executed_at"],
            "created_at": row["created_at"],
            "required_cash": required_cash,
            "holding_shares": holding_shares,
            "has_sufficient_cash": current_cash >= required_cash if action == "BUY" else True,
            "has_sufficient_shares": holding_shares >= shares if action == "SELL" else True,
        })

    return rules


def set_auto_trade_state(conn, rule_id, enabled, status, paused_reason=None):
    """Persist a new state for an automatic trade rule."""
    conn.execute(
        "UPDATE auto_trades SET enabled = ?, status = ?, paused_reason = ? WHERE id = ? AND user_id = ?",
        (1 if enabled else 0, status, paused_reason, rule_id, DEFAULT_USER_ID)
    )


def execute_trade_order(conn, ticker, action, shares, market_price, ledger_type=None):
    """Execute a buy or sell order against the current user account."""
    action = action.upper().strip()
    ticker = ticker.upper().strip()
    transaction_type = ledger_type or action

    user = conn.execute("SELECT * FROM users WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()
    holding = conn.execute(
        "SELECT * FROM holdings WHERE user_id = ? AND ticker = ?",
        (DEFAULT_USER_ID, ticker)
    ).fetchone()

    trade_total = round(market_price * shares, 2)

    if action == "BUY":
        if user["cash"] < trade_total:
            return False, f"Insufficient cash to buy {shares} shares of {ticker}."

        if holding:
            existing_shares = holding["shares"]
            existing_cost = existing_shares * holding["average_price"]
            new_total_shares = existing_shares + shares
            new_average_price = (existing_cost + trade_total) / new_total_shares
            conn.execute(
                "UPDATE holdings SET shares = ?, average_price = ? WHERE id = ?",
                (new_total_shares, round(new_average_price, 4), holding["id"])
            )
        else:
            conn.execute(
                "INSERT INTO holdings (user_id, ticker, shares, average_price) VALUES (?, ?, ?, ?)",
                (DEFAULT_USER_ID, ticker, shares, market_price)
            )

        conn.execute(
            "UPDATE users SET cash = cash - ? WHERE id = ?",
            (trade_total, DEFAULT_USER_ID)
        )
    else:
        if not holding:
            return False, f"You do not own any shares of {ticker}."

        if shares > holding["shares"]:
            return False, f"Insufficient shares. You only hold {holding['shares']} shares."

        remaining_shares = holding["shares"] - shares
        if remaining_shares > 0:
            conn.execute(
                "UPDATE holdings SET shares = ? WHERE id = ?",
                (remaining_shares, holding["id"])
            )
        else:
            conn.execute("DELETE FROM holdings WHERE id = ?", (holding["id"],))

        conn.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            (trade_total, DEFAULT_USER_ID)
        )

    conn.execute(
        "INSERT INTO transactions (user_id, ticker, type, shares, price) VALUES (?, ?, ?, ?, ?)",
        (DEFAULT_USER_ID, ticker, transaction_type, shares, market_price)
    )

    return True, f"{transaction_type} order executed for {shares} shares of {ticker} at ${market_price:,.2f}."


def process_auto_trade_rules(conn):
    """Evaluate active automatic trade rules against live prices and pause unsafe rules."""
    ensure_auto_trades_table(conn)
    rules = conn.execute(
        "SELECT * FROM auto_trades WHERE user_id = ? ORDER BY enabled DESC, id ASC",
        (DEFAULT_USER_ID,)
    ).fetchall()

    summary = {"executed": [], "paused": []}

    for rule in rules:
        if not rule["enabled"]:
            continue

        ticker = (rule["ticker"] or "").upper()
        action = (rule["action"] or "BUY").upper()
        shares = int(rule["shares"] or 0)
        target_price = float(rule["target_price"] or 0.0)

        if action == "BUY":
            current_cash = conn.execute(
                "SELECT cash FROM users WHERE id = ?",
                (DEFAULT_USER_ID,)
            ).fetchone()[0]
            required_cash = round(target_price * shares, 2)
            if float(current_cash or 0.0) < required_cash:
                set_auto_trade_state(conn, rule["id"], False, "paused", "Paused: insufficient cash")
                summary["paused"].append(f"{ticker} paused due to insufficient cash.")
                continue
        else:
            holding = conn.execute(
                "SELECT shares FROM holdings WHERE user_id = ? AND ticker = ?",
                (DEFAULT_USER_ID, ticker)
            ).fetchone()
            holding_shares = int(holding[0]) if holding else 0
            if holding_shares < shares:
                set_auto_trade_state(conn, rule["id"], False, "paused", "Paused: insufficient shares")
                summary["paused"].append(f"{ticker} paused due to insufficient shares.")
                continue

        try:
            live_price = get_live_stock_price(ticker)
        except Exception:
            continue

        trigger_ready = live_price >= target_price
        if action == "BUY":
            current_cash = conn.execute(
                "SELECT cash FROM users WHERE id = ?",
                (DEFAULT_USER_ID,)
            ).fetchone()[0]
            required_cash = round(target_price * shares, 2)
            if float(current_cash or 0.0) < required_cash:
                set_auto_trade_state(conn, rule["id"], False, "paused", "Paused: insufficient cash")
                summary["paused"].append(f"{ticker} paused due to insufficient cash.")
                continue

        if not trigger_ready:
            continue

        success, message = execute_trade_order(
            conn,
            ticker=ticker,
            action=action,
            shares=shares,
            market_price=live_price,
            ledger_type=f"AUTO {action}"
        )

        if success:
            conn.execute(
                "UPDATE auto_trades SET enabled = 0, status = ?, paused_reason = NULL, last_executed_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                ("executed", rule["id"], DEFAULT_USER_ID)
            )
            summary["executed"].append(message)
        else:
            if "Insufficient cash" in message:
                set_auto_trade_state(conn, rule["id"], False, "paused", "Paused: insufficient cash")
                summary["paused"].append(f"{ticker} paused due to insufficient cash.")
            elif "Insufficient shares" in message or "do not own" in message:
                set_auto_trade_state(conn, rule["id"], False, "paused", "Paused: insufficient shares")
                summary["paused"].append(f"{ticker} paused due to insufficient shares.")

    return summary


def watchlist_has_target_price(conn):
    """Detect whether the live watchlist table requires a target_price value."""
    columns = conn.execute("PRAGMA table_info(watchlist)").fetchall()
    return any(column["name"] == "target_price" for column in columns)


def get_live_stock_price(ticker):
    """Fetch a current tradable price with resilient fallbacks."""
    stock = yf.Ticker(ticker)

    try:
        fast_info = getattr(stock, "fast_info", {}) or {}
        price = fast_info.get("lastPrice") or fast_info.get("last_price")
        if price:
            return float(price)
    except Exception:
        pass

    info = stock.info or {}
    price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    if price:
        return float(price)

    raise ValueError(f"Unable to resolve a live price for {ticker}")


def get_hot_indicator_tickers(conn):
    """Return a stable liquid-market universe for live volume ranking."""
    return HOT_INDICATOR_UNIVERSE


def build_hot_indicators(limit=5):
    """Build a live top-volume list from the tracked ticker universe."""
    conn = get_db_connection()
    tickers = get_hot_indicator_tickers(conn)
    conn.close()

    ranked_rows = []

    try:
        api_data = yf.Tickers(" ".join(tickers))
        for ticker in tickers:
            try:
                info = api_data.tickers[ticker].info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose') or 0.0
                open_price = info.get('regularMarketOpen') or current_price or 1.0
                volume = info.get('regularMarketVolume') or info.get('volume') or info.get('averageVolume') or 0
                change_percent = ((current_price - open_price) / open_price) * 100 if open_price else 0.0

                ranked_rows.append({
                    "ticker": ticker,
                    "price": round(float(current_price or 0.0), 2),
                    "change": round(float(change_percent), 2),
                    "volume": int(volume or 0)
                })
            except Exception:
                ranked_rows.append({"ticker": ticker, "price": 0.0, "change": 0.0, "volume": 0})
    except Exception:
        ranked_rows = [{"ticker": ticker, "price": 0.0, "change": 0.0, "volume": 0} for ticker in tickers]

    ranked_rows.sort(key=lambda item: item["volume"], reverse=True)
    return ranked_rows[:limit]


def build_targeted_watchlist_payload(conn=None, limit=6):
    """Build the live targeted watchlist payload used by the dashboard and search page."""
    owns_connection = conn is None
    conn = conn or get_db_connection()

    try:
        ensure_watchlist_table(conn)
        watchlist_rows = conn.execute(
            "SELECT id, ticker FROM watchlist WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (DEFAULT_USER_ID, limit)
        ).fetchall()
        tickers = [row["ticker"].upper() for row in watchlist_rows]

        items = []
        if tickers:
            try:
                api_data = yf.Tickers(" ".join(tickers))
                for ticker in tickers:
                    try:
                        info = api_data.tickers[ticker].info
                        current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose') or 0.0
                        open_price = info.get('regularMarketOpen') or current_price or 1.0
                        change_percent = ((current_price - open_price) / open_price) * 100 if open_price else 0.0

                        items.append({
                            "ticker": ticker,
                            "price": round(float(current_price or 0.0), 2),
                            "change": round(float(change_percent), 2)
                        })
                    except Exception:
                        items.append({"ticker": ticker, "price": 0.0, "change": 0.0})
            except Exception:
                items = [{"ticker": ticker, "price": 0.0, "change": 0.0} for ticker in tickers]

        remaining_slots = max(0, limit - len(items))
        return {
            "items": items,
            "remaining_slots": remaining_slots,
            "message": "add more targeted stock" if remaining_slots > 0 else "",
            "tickers": [item["ticker"] for item in items]
        }
    finally:
        if owns_connection:
            conn.close()


def search_market_stocks(query, limit=10):
    """Return live symbol search matches for the market search box."""
    query = (query or "").strip()
    if not query:
        return []

    search_url = (
        "https://query1.finance.yahoo.com/v1/finance/search"
        f"?q={quote_plus(query)}&quotesCount={limit}&newsCount=0&listsCount=0&enableFuzzyQuery=true"
    )

    try:
        request = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        results = []
        for quote in payload.get("quotes", []):
            ticker = (quote.get("symbol") or "").strip().upper()
            if not ticker:
                continue

            name = quote.get("shortname") or quote.get("longname") or quote.get("name") or ticker
            results.append({"ticker": ticker, "name": name})

            if len(results) >= limit:
                break

        if results:
            return results
    except Exception:
        pass

    fallback_ticker = query.upper()
    if fallback_ticker.replace(".", "").replace("-", "").isalnum():
        return [{"ticker": fallback_ticker, "name": fallback_ticker}]

    return []


def format_relative_news_time(published_at):
    """Format a publish timestamp into a short relative label."""
    if not published_at:
        return "Just now"

    now = datetime.now(timezone.utc)
    published = datetime.fromtimestamp(int(published_at), tz=timezone.utc)
    delta_seconds = max(0, int((now - published).total_seconds()))

    if delta_seconds < 60:
        return "Just now"
    if delta_seconds < 3600:
        return f"{delta_seconds // 60}m ago"
    if delta_seconds < 86400:
        return f"{delta_seconds // 3600}h ago"
    return f"{delta_seconds // 86400}d ago"


def extract_news_thumbnail(article):
    """Return the best available thumbnail URL for a news item."""
    thumbnail = article.get("thumbnail") or {}
    resolutions = thumbnail.get("resolutions") or []
    if not resolutions:
        return "/static/images/news-placeholder.jpg"

    best_resolution = max(
        resolutions,
        key=lambda item: item.get("width", 0) * item.get("height", 0)
    )
    return best_resolution.get("url") or "/static/images/news-placeholder.jpg"


def fetch_live_market_news(limit=24):
    """Fetch a live, de-duplicated market news feed sorted newest to oldest."""
    queries = ["market", "stocks", "economy", "earnings", "fed", "crypto"]
    articles = []
    seen_links = set()

    for query in queries:
        search_url = (
            "https://query1.finance.yahoo.com/v1/finance/search"
            f"?q={quote_plus(query)}&quotesCount=0&newsCount=10&listsCount=0&enableFuzzyQuery=true"
        )

        try:
            request = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            continue

        for article in payload.get("news", []):
            link = (article.get("link") or "").strip()
            title = (article.get("title") or "").strip()
            if not link or not title or link in seen_links:
                continue

            seen_links.add(link)
            related_tickers = article.get("relatedTickers") or []
            summary_parts = []
            publisher = (article.get("publisher") or "Yahoo Finance").strip()
            if publisher:
                summary_parts.append(publisher)
            if related_tickers:
                summary_parts.append(f"Related tickers: {', '.join(related_tickers[:4])}")

            articles.append({
                "title": title,
                "summary": " · ".join(summary_parts) if summary_parts else "Live market update",
                "source": publisher or "Yahoo Finance",
                "time_elapsed": format_relative_news_time(article.get("providerPublishTime")),
                "published_at": int(article.get("providerPublishTime") or 0),
                "image_url": extract_news_thumbnail(article),
                "url": link
            })

            if len(articles) >= limit:
                break

        if len(articles) >= limit:
            break

    articles.sort(key=lambda item: item.get("published_at", 0), reverse=True)
    return articles[:limit]


@app.route("/api/hot-indicators")
def api_hot_indicators():
    """Returns the current top volume indicators as JSON for live sidebar refreshes."""
    return jsonify(build_hot_indicators())


@app.route("/api/search")
def api_search():
    """Returns live symbol matches for the search dropdown."""
    query = request.args.get("q", "")
    return jsonify(search_market_stocks(query))

@app.route("/api/watchlist")
def api_watchlist():
    """Returns real-time targeted watchlist prices as JSON for background updates."""
    return jsonify(build_targeted_watchlist_payload())


@app.route("/api/watchlist/toggle", methods=["POST"])
def toggle_watchlist():
    """Adds or removes a stock from the targeted watchlist, capped at six items."""
    payload = request.get_json(silent=True) or request.form or {}
    ticker = (payload.get("ticker") or "").upper().strip()

    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400

    conn = get_db_connection()
    try:
        ensure_watchlist_table(conn)

        existing = conn.execute(
            "SELECT id FROM watchlist WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER_ID, ticker)
        ).fetchone()

        if existing:
            conn.execute("DELETE FROM watchlist WHERE id = ?", (existing["id"],))
            conn.commit()
            payload = build_targeted_watchlist_payload(conn)
            payload["is_targeted"] = False
            return jsonify(payload)

        current_count = conn.execute(
            "SELECT COUNT(id) FROM watchlist WHERE user_id = ?",
            (DEFAULT_USER_ID,)
        ).fetchone()[0]

        if current_count >= 6:
            return jsonify({"error": "Targeted watchlist can hold at most 6 stocks."}), 400

        target_price = 0.0
        try:
            target_price = get_live_stock_price(ticker)
        except Exception:
            pass

        if watchlist_has_target_price(conn):
            conn.execute(
                "INSERT INTO watchlist (user_id, ticker, target_price) VALUES (?, ?, ?)",
                (DEFAULT_USER_ID, ticker, target_price)
            )
        else:
            conn.execute(
                "INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)",
                (DEFAULT_USER_ID, ticker)
            )
        conn.commit()

        payload = build_targeted_watchlist_payload(conn)
        payload["is_targeted"] = True
        return jsonify(payload)
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()

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
    ensure_transactions_table(conn)
    
    # Grab details for the default user (id = 1)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()
    ensure_auto_trades_table(conn)
    process_auto_trade_rules(conn)
    conn.commit()
    
    # Calculate Core Metric Numbers for Layer 1
    holdings_count = conn.execute("SELECT COUNT(id) FROM holdings WHERE user_id = ?", (DEFAULT_USER_ID,)).fetchone()[0]
    recent_txs_rows = conn.execute(
        "SELECT timestamp, ticker, type, shares, price, (shares * price) as total FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5",
        (DEFAULT_USER_ID,)
    ).fetchall()
    
    # Calculate auto-trades executed since the logged logout timestamp
    auto_trades_count = conn.execute(
        "SELECT COUNT(id) FROM transactions WHERE user_id = ? AND type LIKE '%Auto%' AND timestamp > ?",
        (DEFAULT_USER_ID, user['last_logout_at'])
    ).fetchone()[0]

    # Assemble metrics object dynamically
    metrics = {
        "current_asset": user['cash'],
        "asset_change_percent": 1.18,  # Hardcoded placeholder for layout continuity
        "auto_trades_since_logout": auto_trades_count,
        "current_holdings_count": holdings_count
    }

    targeted_watchlist = build_targeted_watchlist_payload(conn)
    conn.close()

    return render_template(
        "index.html", 
        metrics=metrics, 
        targeted_stocks=targeted_watchlist["items"],
        targeted_watchlist_message=targeted_watchlist["message"],
        targeted_watchlist_tickers=targeted_watchlist["tickers"],
        market_news=fetch_live_market_news(limit=5), 
        recent_transactions=recent_txs_rows
    )


@app.route("/profile", methods=["GET", "POST"])
def profile_page():
    """Render the account profile view and handle balance reset actions."""
    conn = get_db_connection()
    try:
        ensure_transactions_table(conn)
        ensure_auto_trades_table(conn)
        user = conn.execute("SELECT * FROM users WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()

        if request.method == "POST":
            action = (request.form.get("action") or "").strip().lower()
            if action == "reset_balance":
                for table_name in ("transactions", "holdings", "watchlist", "auto_trades"):
                    try:
                        conn.execute(f"DELETE FROM {table_name} WHERE user_id = ?", (DEFAULT_USER_ID,))
                    except sqlite3.OperationalError:
                        pass

                conn.execute(
                    "UPDATE users SET cash = ? WHERE id = ?",
                    (10000.00, DEFAULT_USER_ID)
                )
                conn.commit()
                flash("Account balance reset to $10,000.00.", "success")
                return redirect(url_for("profile_page"))

            if action == "add_auto_trade":
                ticker = (request.form.get("ticker") or "").upper().strip()
                trade_action = (request.form.get("trade_action") or "BUY").upper().strip()
                shares_raw = request.form.get("shares") or "0"
                target_price_raw = request.form.get("target_price") or "0"

                if not ticker:
                    flash("Ticker is required for an automatic trade rule.", "error")
                    return redirect(url_for("profile_page"))

                if trade_action not in {"BUY", "SELL"}:
                    flash("Automatic trade action must be BUY or SELL.", "error")
                    return redirect(url_for("profile_page"))

                try:
                    shares = int(shares_raw)
                    target_price = float(target_price_raw)
                except (TypeError, ValueError):
                    flash("Shares and trigger price must be valid numbers.", "error")
                    return redirect(url_for("profile_page"))

                if shares <= 0 or target_price <= 0:
                    flash("Shares and trigger price must be greater than zero.", "error")
                    return redirect(url_for("profile_page"))

                current_cash = float(user["cash"] or 0.0)
                required_cash = round(target_price * shares, 2)
                current_holding = conn.execute(
                    "SELECT shares FROM holdings WHERE user_id = ? AND ticker = ?",
                    (DEFAULT_USER_ID, ticker)
                ).fetchone()

                if trade_action == "BUY" and current_cash < required_cash:
                    flash(f"Not enough cash to schedule {ticker} at ${target_price:,.2f}.", "error")
                    return redirect(url_for("profile_page"))

                if trade_action == "SELL" and (not current_holding or int(current_holding[0]) < shares):
                    flash(f"You do not hold enough shares of {ticker} to schedule this sell rule.", "error")
                    return redirect(url_for("profile_page"))

                conn.execute(
                    "INSERT INTO auto_trades (user_id, ticker, action, shares, target_price, enabled, status) VALUES (?, ?, ?, ?, ?, 1, 'active')",
                    (DEFAULT_USER_ID, ticker, trade_action, shares, target_price)
                )
                conn.commit()

                summary = process_auto_trade_rules(conn)
                conn.commit()

                if summary["executed"]:
                    flash("Automatic trade executed: " + " | ".join(summary["executed"]), "success")
                if summary["paused"]:
                    flash("Automatic trade paused: " + " | ".join(summary["paused"]), "warning")
                flash(f"Automatic rule saved for {ticker}.", "success")
                return redirect(url_for("profile_page"))

            if action == "remove_auto_trade":
                rule_id = request.form.get("rule_id")
                try:
                    rule_id_int = int(rule_id)
                except (TypeError, ValueError):
                    flash("Invalid automatic trade rule.", "error")
                    return redirect(url_for("profile_page"))

                conn.execute(
                    "DELETE FROM auto_trades WHERE id = ? AND user_id = ?",
                    (rule_id_int, DEFAULT_USER_ID)
                )
                conn.commit()
                flash("Automatic trade rule removed.", "success")
                return redirect(url_for("profile_page"))

        auto_summary = process_auto_trade_rules(conn)
        if auto_summary["executed"]:
            flash("Automatic trade executed: " + " | ".join(auto_summary["executed"]), "success")
        if auto_summary["paused"]:
            flash("Automatic trade paused: " + " | ".join(auto_summary["paused"]), "warning")
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()
        user_columns = ensure_user_profile_columns(conn)
        join_source = user["created_at"] if "created_at" in user_columns else user["last_logout_at"]
        profile_metrics = build_profile_metrics(conn, user)
        auto_trade_rules = fetch_auto_trade_rules(conn)

        return render_template(
            "profile.html",
            username=user["username"],
            cash_balance=float(user["cash"] or 0.0),
            account_join_date=format_profile_timestamp(join_source),
            win_loss_ratio=profile_metrics["win_loss_ratio"],
            total_fees_paid=profile_metrics["total_fees_paid"],
            auto_trade_rules=auto_trade_rules,
        )
    finally:
        conn.close()

@app.route("/search")
def search_page():
    """Renders the standalone trading workspace with live tracking blocks."""
    conn = get_db_connection()
    ensure_auto_trades_table(conn)
    process_auto_trade_rules(conn)
    conn.commit()
    
    # 1. Grab user balance information
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    targeted_watchlist = build_targeted_watchlist_payload(conn)
    
    # 2. Grab all positions to calculate real-time values
    holdings_rows = conn.execute("SELECT * FROM holdings WHERE user_id = ?", (DEFAULT_USER_ID,)).fetchall()
    
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
        hot_stocks=hot_stocks,
        targeted_stocks=targeted_watchlist["items"],
        targeted_watchlist_message=targeted_watchlist["message"],
        targeted_watchlist_tickers=targeted_watchlist["tickers"]
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
    action = (request.form.get("action") or "").upper().strip()
    ticker = (request.form.get("ticker") or "").upper().strip()
    shares_raw = request.form.get("shares") or request.form.get("quantity")

    try:
        shares = int(shares_raw)
    except (ValueError, TypeError):
        flash("Invalid quantity entered.", "error")
        return redirect("/search")

    if not ticker:
        flash("Select an asset before submitting the order.", "error")
        return redirect("/search")

    if action not in {"BUY", "SELL"}:
        flash("Unsupported order action.", "error")
        return redirect("/search")

    if shares <= 0:
        flash("Quantity must be greater than 0.", "error")
        return redirect("/search")

    conn = get_db_connection()
    ensure_transactions_table(conn)
    ensure_auto_trades_table(conn)

    try:
        market_price = get_live_stock_price(ticker)
        success, message = execute_trade_order(conn, ticker, action, shares, market_price)
        if not success:
            flash(message, "error")
            return redirect("/search")

        conn.commit()

        auto_summary = process_auto_trade_rules(conn)
        conn.commit()

        if auto_summary["executed"]:
            flash("Automatic trade executed: " + " | ".join(auto_summary["executed"]), "success")
        if auto_summary["paused"]:
            flash("Automatic trade paused: " + " | ".join(auto_summary["paused"]), "warning")

        flash(message, "success")
        return redirect("/search")
    except Exception as exc:
        conn.rollback()
        flash(f"Trade failed: {exc}", "error")
        return redirect("/search")
    finally:
        conn.close()

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

    performance_kpis = build_analytics_kpis(conn)

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
    return render_template("news.html", news_list=fetch_live_market_news())

if __name__ == "__main__":
    app.run(debug=True)