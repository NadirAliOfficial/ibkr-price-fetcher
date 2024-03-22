# IBKR Price Fetcher (Live · Delayed · Historical)

A user-friendly Python tool to fetch stock prices from Interactive Brokers with automatic fallback logic.

The script automatically chooses the best available data source:

1. **Live market data** (if subscription + market open)
2. **Delayed market data** (if live not available)
3. **Historical data** (weekends, holidays, or no subscription)

No code changes are required to add or remove tickers.

---

## Features

* Live, delayed, and historical price support
* Weekend and holiday safe
* No `nan` values
* Clean output (IBKR warnings hidden)
* Easy ticker management via text file
* Works with TWS or IB Gateway
* Suitable for bots, dashboards, and cron jobs

---

## Project Structure

```
live-qts/
│
├── main.py          # Main script
├── tickers.txt      # List of symbols (editable)
├── README.md        # Documentation
├── .venv/           # Virtual environment (optional)
```

---

## Requirements

* Python 3.9+
* Interactive Brokers account
* IB Trader Workstation (TWS) or IB Gateway
* API access enabled in IBKR

---

## Installation

### 1. Create virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install ib-insync
```

---

## IBKR Setup

In **TWS or IB Gateway**:

1. Open **Global Configuration**
2. Go to **API → Settings**
3. Enable:

   * Enable ActiveX and Socket Clients
4. Disable:

   * Read-Only API
5. Restart TWS / Gateway

Default ports:

* TWS (Paper): `7497`
* Gateway (Paper): `4002`

---

## Adding or Removing Tickers

Edit **`tickers.txt`**:

```
# US Stocks
AAPL
MSFT
GOOGL
AMZN
TSLA
```

Rules:

* One symbol per line
* Blank lines allowed
* Lines starting with `#` are ignored

No code edits needed.

---

## Running the Script

```bash
python main.py
```

---

## Sample Output

```
Symbol | Price     | Source       | Note
------------------------------------------------------------
AAPL   | 270.98    | HISTORICAL   | Market closed or no subscription
MSFT   | 472.93    | HISTORICAL   | Market closed or no subscription
GOOGL  | 315.08    | DELAYED      | Delayed market price
AMZN   | 226.50    | HISTORICAL   | Market closed or no subscription
TSLA   | 438.10    | HISTORICAL   | Market closed or no subscription
```

---

## Data Sources Explained

### LIVE

* Requires market data subscription
* Market must be open
* Real-time prices

### DELAYED

* Available if live subscription is missing
* Usually delayed by ~15 minutes
* Automatically selected when available

### HISTORICAL

* Always available
* Used on weekends, holidays, or off-hours
* Uses last traded price from recent history

---

## Error Handling

* IBKR subscription warnings are hidden
* No raw IBKR error messages shown
* Script never crashes due to missing data
* Always returns a valid price when possible

This behavior is intentional and production-safe.

---

## Common Questions

### Why do I see HISTORICAL on weekends?

US stock markets are closed on weekends. The script automatically falls back to historical data.

### Why don’t I see LIVE prices?

You need an active IBKR market data subscription and the market must be open.

### Is this safe for automation?

Yes. The script:

* Handles missing subscriptions
* Works during market closures
* Produces consistent output

---

## Customization

You can easily extend this project to add:

* CSV export
* SQLite caching
* Telegram or Discord alerts
* Forex, Futures, or Crypto support
* Async multi-symbol scanning
* CLI arguments

---

## Disclaimer

This tool is for informational and educational purposes only.
It does not place trades and does not provide financial advice.

---

## Credits

Built using `ib-insync` and the Interactive Brokers API.
<!-- updated: 2024-03-22-r01 -->
