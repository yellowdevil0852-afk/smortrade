# Smortrade
#### Video Demo:  <URL HERE>

---

# Smortrade Descrption

## Table of Contents
1. [Getting Started](#getting-started)
2. [Core Features](#core-features)
3. [Step-by-Step Workflows](#step-by-step-workflows)
4. [Troubleshooting](#troubleshooting)
5. [Configuration & License](#configuration--license)

---

## Getting Started

### System Requirements
- Python 3.7 or higher
- Modern web browser (Chrome, Firefox, Safari, Edge)
- Internet connection for live market data

### Installation

1. **Clone or Download the Repository**
   Ensure you have the project folder on your local machine.

2. **Install Dependencies**
   `pip install flask yfinance`

3. **Initialize the Database**
   `python init_db.py`
   This creates the SQLite database with default user `cs50_student` and a starting cash balance of $10,000.00.

4. **Start the Application**
   `python app.py`

5. **Access the Application**
   Navigate to `http://127.0.0.1:5000` in your web browser. The app operates in single-user sandbox mode with automatic session creation.

---

## Core Features

| Feature | Description |
| :--- | :--- |
| **Dashboard** | Overview of available cash, open positions, automated execution count, news feed, and recent trades. |
| **Stock Search & Trading** | Look up tickers, view real-time market data via Yahoo Finance, and execute market buy/sell orders. |
| **Analytics Terminal** | Metrics including Net Asset Valuation, Win Rate, Profit Factor Ratio, and Portfolio Equity Growth Curve. |
| **Automated Trading** | Conditional price-triggered rules that execute buys and sells automatically when target prices are hit. |
| **Targeted Watchlist** | Live price tracking for up to 6 selected stocks with 30-second auto-refresh cycles. |
| **Market News Feed** | Financial news stream structured in a grid layout with thumbnail visuals and ticker tags. |
| **User Profile** | Manage account details, track cumulative transaction fees, manage rules, or reset portfolio balance. |

---

## Step-by-Step Workflows

### Workflow 1: Buying and Selling Stocks
1. Go to **Stock Search** in the sidebar navigation.
2. Enter a ticker symbol (e.g., `AAPL`) or select one from quick search suggestions.
3. Select **BUY** or **SELL** from the Order Action dropdown.
4. Input the share quantity and review estimated costs.
5. Click **Route Order Ticket** to execute instantly.
6. Verify updated positions and cash balance on the **Dashboard**.

### Workflow 2: Setting Up Automated Trade Rules
1. Navigate to **Profile** and locate the **Price Trigger Rules** section.
2. Enter the ticker symbol, choose **BUY** or **SELL**, set share quantity, and enter the target trigger price.
3. Click **Submit Rule** to initialize tracking.
4. Monitor rule status:
   - **Ready**: Conditions met for execution.
   - **Waiting**: Target price not yet reached.
   - **Auto-Paused**: Triggered, but paused due to insufficient cash or shares.

### Workflow 3: Managing Your Watchlist
1. Search for a stock on the **Stock Search** page.
2. Click the **Star Icon** to add it to your main dashboard watchlist (maximum 6 stocks).
3. Monitor real-time price updates on the main dashboard screen.
4. Click the star icon again to remove any stock from the list.

### Workflow 4: Resetting Portfolio
1. Navigate to **Profile**.
2. Click **Reset Balance to $10,000**.
3. Confirm the prompt to restore initial cash, clear all open positions, wipe order history, and delete auto-trading rules.

---

## Troubleshooting

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **App won't start** | Port conflict or uninitialized database | Change port in `app.py` or run `python init_db.py`. |
| **Prices not updating** | Yahoo Finance API rate limits or network offline | Verify internet connection or wait a few minutes for rate limits to reset. |
| **Trade execution fails** | Insufficient funds or unowned shares | Ensure account cash covers purchases or sufficient shares exist for sales. |
| **Rules not running** | Paused state or price not met | Check status in **Profile** and ensure cash/shares are available for order execution. |
| **Blank charts** | CDN script blocked or missing data | Ensure network access to Chart.js CDN and check browser console logs. |

---

## Configuration & License

- **Default Balance**: $10,000.00 USD
- **Simulated Trade Fee**: $0.99 + $0.005 per share
- **Watchlist Capacity**: Maximum 6 stocks
- **Data Persistence**: All records persist locally inside `database.db`.
- **Disclaimer**: Smortrade is purely an educational simulation tool. No real monetary transactions or actual brokerage accounts are connected.