from ib_insync import *
from datetime import datetime
import logging
from enum import Enum

# Silence IBKR noise
logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
util.startLoop()

# ---------- CONFIG ----------
HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 77
TICKER_FILE = "tickers.txt"
TIMEOUT = 2


class DataType(Enum):
    """Available data types from IBKR"""
    PRICE = "price"
    BID_ASK = "bid_ask"
    LEVEL2 = "level2"
    NEWS = "news"
    OPTIONS = "options"
    FUTURES = "futures"
    FUNDAMENTALS = "fundamentals"
    HISTORICAL = "historical"
    VOLUME = "volume"
    TICK_DATA = "tick_data"


class IBKRDataFetcher:
    """
    Comprehensive IBKR data fetcher - FIXED VERSION
    
    Handles common IBKR API issues:
    - Level 2 subscription requirements
    - News API parameter changes
    - Market data permissions
    - Error handling
    """

    def __init__(self, host=HOST, port=PORT, client_id=CLIENT_ID):
        self.ib = IB()
        self.ib.connect(host, port, clientId=client_id)
        self.ib.errorEvent += self._suppress_errors
        print(f"✓ Connected to IBKR at {host}:{port}")
        
        # Track which features are available
        self.has_level2 = False
        self.has_news = False
        self.has_realtime_data = False

    def _suppress_errors(self, reqId, errorCode, errorString, contract):
        """Suppress non-critical IBKR messages"""
        suppressed_codes = [10089, 300, 10167, 2104, 2106, 2158, 10092, 354]
        
        if errorCode == 10092:
            # Level 2 not available
            self.has_level2 = False
        elif errorCode == 354:
            # News not available
            self.has_news = False
        elif errorCode not in suppressed_codes:
            print(f"⚠️  IBKR {errorCode}: {errorString}")

    def _valid_price(self, price):
        """Check if price is valid"""
        return price is not None and not (isinstance(price, float) and (price != price or price <= 0))

    def _get_contract(self, symbol, sec_type="STK"):
        """Get and qualify a contract"""
        if sec_type == "STK":
            contract = Stock(symbol, "SMART", "USD")
        elif sec_type == "FUT":
            contract = Future(symbol, exchange="GLOBEX")
        else:
            contract = Contract(symbol=symbol, secType=sec_type)
        
        self.ib.qualifyContracts(contract)
        return contract

    # ========== PRICE DATA ==========
    
    def get_price(self, symbol):
        """
        Get current price with bid/ask
        
        Returns dict with: last, bid, ask, spread, volume, high, low, open, close, source
        """
        contract = self._get_contract(symbol)
        
        # Try live first
        self.ib.reqMarketDataType(1)
        ticker = self.ib.reqMktData(contract, "", False, False)
        self.ib.sleep(TIMEOUT)
        
        source = "LIVE"
        
        # If no live data, try delayed
        if not self._valid_price(ticker.last):
            self.ib.reqMarketDataType(3)
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(TIMEOUT)
            source = "DELAYED"
        
        # If still no data, use historical
        if not self._valid_price(ticker.last):
            bars = self.ib.reqHistoricalData(
                contract, "", "1 D", "1 min", "TRADES", useRTH=True
            )
            if bars:
                bar = bars[-1]
                return {
                    "symbol": symbol,
                    "last": round(bar.close, 2),
                    "bid": None,
                    "ask": None,
                    "spread": None,
                    "open": round(bar.open, 2),
                    "high": round(bar.high, 2),
                    "low": round(bar.low, 2),
                    "close": round(bar.close, 2),
                    "volume": int(bar.volume),
                    "source": "HISTORICAL",
                    "time": datetime.now().isoformat()
                }
        
        # We have ticker data
        self.has_realtime_data = self._valid_price(ticker.last)
        
        return {
            "symbol": symbol,
            "last": round(ticker.last, 2) if self._valid_price(ticker.last) else None,
            "bid": round(ticker.bid, 2) if self._valid_price(ticker.bid) else None,
            "ask": round(ticker.ask, 2) if self._valid_price(ticker.ask) else None,
            "spread": round(ticker.ask - ticker.bid, 4) if self._valid_price(ticker.bid) and self._valid_price(ticker.ask) else None,
            "volume": int(ticker.volume) if ticker.volume else 0,
            "high": round(ticker.high, 2) if self._valid_price(ticker.high) else None,
            "low": round(ticker.low, 2) if self._valid_price(ticker.low) else None,
            "open": round(ticker.open, 2) if self._valid_price(ticker.open) else None,
            "close": round(ticker.close, 2) if self._valid_price(ticker.close) else None,
            "source": source,
            "time": datetime.now().isoformat()
        }

    # ========== LEVEL 2 / MARKET DEPTH ==========
    
    def get_level2(self, symbol, depth=10):
        """
        Get Level 2 market depth data
        
        NOTE: Requires market depth subscription from IBKR
        Will return empty if not subscribed
        
        Returns dict with: bids [(price, size), ...], asks [(price, size), ...]
        """
        contract = self._get_contract(symbol)
        
        try:
            ticker = self.ib.reqMktDepth(contract, numRows=depth)
            self.ib.sleep(TIMEOUT + 1)
            
            bids = [(d.price, d.size) for d in (ticker.domBids or [])]
            asks = [(d.price, d.size) for d in (ticker.domAsks or [])]
            
            self.ib.cancelMktDepth(contract)
            
            self.has_level2 = len(bids) > 0 or len(asks) > 0
            
            return {
                "symbol": symbol,
                "bids": bids[:depth],
                "asks": asks[:depth],
                "available": self.has_level2,
                "time": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"⚠️  Level 2 not available: {e}")
            return {
                "symbol": symbol,
                "bids": [],
                "asks": [],
                "available": False,
                "time": datetime.now().isoformat()
            }

    # ========== NEWS ==========
    
    def get_news(self, symbol, count=10):
        """
        Get recent news headlines
        
        NOTE: Requires news subscription from IBKR
        
        Returns list of dicts with: headline, provider, time
        """
        contract = self._get_contract(symbol)
        
        try:
            # The API signature changed - need to provide totalResults parameter
            # Try the new way first
            news = self.ib.reqHistoricalNews(
                contract.conId, 
                providerCode="", 
                startDateTime="", 
                endDateTime="",
                totalResults=count
            )
            
            self.has_news = True
            
            return [
                {
                    "headline": article.headline,
                    "provider": article.providerCode,
                    "time": str(article.time),
                    "article_id": article.articleId if hasattr(article, 'articleId') else None
                }
                for article in news
            ]
        except TypeError as e:
            # API signature issue - try alternative approach
            try:
                # Get news providers first
                providers = self.ib.reqNewsProviders()
                if not providers:
                    print(f"ℹ️  No news providers available")
                    return []
                
                # Try with first provider
                provider_code = providers[0].code
                news = self.ib.reqHistoricalNews(
                    contract.conId,
                    providerCode=provider_code,
                    startDateTime="",
                    endDateTime="",
                    totalResults=count
                )
                
                self.has_news = True
                return [
                    {
                        "headline": article.headline,
                        "provider": article.providerCode,
                        "time": str(article.time),
                    }
                    for article in news
                ]
            except Exception as e2:
                print(f"ℹ️  News not available (may require subscription): {type(e2).__name__}")
                return []
        except Exception as e:
            print(f"ℹ️  News not available (may require subscription): {type(e).__name__}")
            return []

    def get_news_article(self, provider_code, article_id):
        """Get full news article text"""
        try:
            article = self.ib.reqNewsArticle(provider_code, article_id)
            return article.articleText if hasattr(article, 'articleText') else None
        except Exception as e:
            print(f"⚠️  Article fetch error: {e}")
            return None

    # ========== OPTIONS ==========
    
    def get_options(self, symbol, expiry_limit=3, strike_range=0.1):
        """
        Get options chain
        
        Args:
            symbol: Stock symbol
            expiry_limit: Number of expiration dates to fetch
            strike_range: % range around current price (0.1 = ±10%)
        
        Returns list of option dicts
        """
        contract = self._get_contract(symbol)
        
        try:
            # Get chains
            chains = self.ib.reqSecDefOptParams(
                contract.symbol, "", contract.secType, contract.conId
            )
            
            if not chains:
                print(f"ℹ️  No options available for {symbol}")
                return []
            
            chain = chains[0]
            expirations = sorted(chain.expirations)[:expiry_limit]
            
            # Get current price to find ATM strikes
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(1)
            current_price = ticker.last if self._valid_price(ticker.last) else None
            
            if not current_price:
                # Try to get from historical
                bars = self.ib.reqHistoricalData(contract, "", "1 D", "1 min", "TRADES", useRTH=True)
                if bars:
                    current_price = bars[-1].close
                else:
                    print(f"⚠️  Cannot determine current price for {symbol}")
                    return []
            
            # Filter strikes near current price
            strikes = [
                s for s in sorted(chain.strikes)
                if abs(s - current_price) < current_price * strike_range
            ]
            
            options = []
            
            for expiry in expirations:
                for strike in strikes[:10]:  # Limit to 10 strikes per expiry
                    for right in ['C', 'P']:
                        opt_contract = Option(symbol, expiry, strike, right, 'SMART')
                        
                        try:
                            self.ib.qualifyContracts(opt_contract)
                            
                            opt_ticker = self.ib.reqMktData(opt_contract, "", False, False)
                            self.ib.sleep(0.3)
                            
                            greeks = opt_ticker.modelGreeks if hasattr(opt_ticker, 'modelGreeks') else None
                            
                            options.append({
                                "symbol": symbol,
                                "expiry": expiry,
                                "strike": strike,
                                "right": right,
                                "bid": round(opt_ticker.bid, 2) if self._valid_price(opt_ticker.bid) else None,
                                "ask": round(opt_ticker.ask, 2) if self._valid_price(opt_ticker.ask) else None,
                                "last": round(opt_ticker.last, 2) if self._valid_price(opt_ticker.last) else None,
                                "volume": int(opt_ticker.volume) if opt_ticker.volume else 0,
                                "open_interest": int(opt_ticker.openInterest) if opt_ticker.openInterest else 0,
                                "iv": round(greeks.impliedVol, 4) if greeks and greeks.impliedVol else None,
                                "delta": round(greeks.delta, 4) if greeks and greeks.delta else None,
                                "gamma": round(greeks.gamma, 4) if greeks and greeks.gamma else None,
                                "theta": round(greeks.theta, 4) if greeks and greeks.theta else None,
                                "vega": round(greeks.vega, 4) if greeks and greeks.vega else None,
                            })
                            
                            self.ib.cancelMktData(opt_contract)
                        except Exception as e:
                            # Skip this option if there's an error
                            continue
            
            return options
            
        except Exception as e:
            print(f"⚠️  Options error for {symbol}: {e}")
            return []

    # ========== FUTURES ==========
    
    def get_futures(self, symbol, exchange="GLOBEX"):
        """Get futures contracts"""
        try:
            contract = Future(symbol, exchange=exchange)
            chains = self.ib.reqContractDetails(contract)
            
            futures = []
            for chain in chains[:5]:  # Limit to 5 contracts
                fut_contract = chain.contract
                ticker = self.ib.reqMktData(fut_contract)
                self.ib.sleep(0.5)
                
                futures.append({
                    "symbol": symbol,
                    "expiry": fut_contract.lastTradeDateOrContractMonth,
                    "last": round(ticker.last, 2) if self._valid_price(ticker.last) else None,
                    "bid": round(ticker.bid, 2) if self._valid_price(ticker.bid) else None,
                    "ask": round(ticker.ask, 2) if self._valid_price(ticker.ask) else None,
                    "volume": int(ticker.volume) if ticker.volume else 0,
                })
                
                self.ib.cancelMktData(fut_contract)
            
            return futures
        except Exception as e:
            print(f"⚠️  Futures error for {symbol}: {e}")
            return []

    # ========== HISTORICAL DATA ==========
    
    def get_historical(self, symbol, duration="1 M", bar_size="1 day", what_to_show="TRADES"):
        """
        Get historical bars
        
        Args:
            duration: "1 D", "1 W", "1 M", "1 Y", etc.
            bar_size: "1 min", "5 mins", "1 hour", "1 day", etc.
            what_to_show: "TRADES", "MIDPOINT", "BID", "ASK"
        
        Returns list of bar dicts
        """
        contract = self._get_contract(symbol)
        
        try:
            bars = self.ib.reqHistoricalData(
                contract, "", duration, bar_size, what_to_show, useRTH=True
            )
            
            return [
                {
                    "date": bar.date.isoformat() if hasattr(bar.date, 'isoformat') else str(bar.date),
                    "open": round(bar.open, 2),
                    "high": round(bar.high, 2),
                    "low": round(bar.low, 2),
                    "close": round(bar.close, 2),
                    "volume": int(bar.volume),
                    "average": round(bar.average, 2) if hasattr(bar, 'average') and bar.average else None,
                }
                for bar in bars
            ]
        except Exception as e:
            print(f"⚠️  Historical data error for {symbol}: {e}")
            return []

    # ========== TICK DATA ==========
    
    def get_tick_data(self, symbol, tick_type="Last", duration=10):
        """
        Get recent tick data
        
        Args:
            tick_type: "Last", "BidAsk", "MidPoint"
            duration: seconds to collect ticks
        
        Returns list of ticks
        """
        contract = self._get_contract(symbol)
        
        try:
            # Request tick-by-tick data
            ticker = self.ib.reqTickByTickData(contract, tick_type)
            self.ib.sleep(duration)
            
            ticks = []
            if hasattr(ticker, 'ticks'):
                for tick in ticker.ticks:
                    tick_data = {
                        "time": tick.time.isoformat() if hasattr(tick, 'time') else None,
                    }
                    
                    if hasattr(tick, 'price'):
                        tick_data["price"] = round(tick.price, 2)
                    if hasattr(tick, 'size'):
                        tick_data["size"] = int(tick.size)
                    if hasattr(tick, 'bidPrice'):
                        tick_data["bid"] = round(tick.bidPrice, 2)
                    if hasattr(tick, 'askPrice'):
                        tick_data["ask"] = round(tick.askPrice, 2)
                    
                    ticks.append(tick_data)
            
            self.ib.cancelTickByTickData(contract, tick_type)
            return ticks
        except Exception as e:
            print(f"⚠️  Tick data error for {symbol}: {e}")
            return []

    # ========== FUNDAMENTALS ==========
    
    def get_fundamentals(self, symbol, report_type="ReportSnapshot"):
        """
        Get fundamental data
        
        report_type options:
            - ReportSnapshot: Company overview
            - ReportsFinSummary: Financial summary
            - ReportRatios: Financial ratios
            - ReportsFinStatements: Financial statements
            - RESC: Analyst estimates
            - CalendarReport: Calendar events
        """
        contract = self._get_contract(symbol)
        
        try:
            data = self.ib.reqFundamentalData(contract, report_type)
            return data
        except Exception as e:
            print(f"⚠️  Fundamentals error for {symbol}: {e}")
            return None

    # ========== CONVENIENCE METHOD ==========
    
    def get_all(self, symbol, data_types=None):
        """
        Get multiple data types at once
        
        Args:
            symbol: Stock symbol
            data_types: List of DataType enums, or None for basic set
        
        Returns dict with requested data
        """
        if data_types is None:
            # Default to basic data that usually works
            data_types = [DataType.PRICE, DataType.HISTORICAL]
        
        result = {"symbol": symbol}
        
        for dt in data_types:
            try:
                if dt == DataType.PRICE:
                    result["price"] = self.get_price(symbol)
                elif dt == DataType.LEVEL2:
                    result["level2"] = self.get_level2(symbol)
                elif dt == DataType.NEWS:
                    result["news"] = self.get_news(symbol)
                elif dt == DataType.OPTIONS:
                    result["options"] = self.get_options(symbol)
                elif dt == DataType.FUTURES:
                    result["futures"] = self.get_futures(symbol)
                elif dt == DataType.HISTORICAL:
                    result["historical"] = self.get_historical(symbol)
                elif dt == DataType.FUNDAMENTALS:
                    result["fundamentals"] = self.get_fundamentals(symbol)
            except Exception as e:
                print(f"⚠️  Error fetching {dt.value} for {symbol}: {e}")
        
        return result

    def get_subscription_status(self):
        """
        Check what data subscriptions are available
        
        Returns dict with available features
        """
        return {
            "realtime_data": self.has_realtime_data,
            "level2": self.has_level2,
            "news": self.has_news,
        }

    def close(self):
        """Disconnect from IBKR"""
        self.ib.disconnect()
        print("✓ Disconnected from IBKR")


# ========== USAGE EXAMPLES ==========

if __name__ == "__main__":
    import json
    
    # Initialize
    fetcher = IBKRDataFetcher()
    
    symbol = "AAPL"
    
    print(f"\n{'='*70}")
    print(f"Fetching data for {symbol}...")
    print(f"{'='*70}\n")
    
    # Example 1: Get price data
    print("1. PRICE DATA")
    price = fetcher.get_price(symbol)
    print(json.dumps(price, indent=2))
    
    # Example 2: Get Level 2 (may not work without subscription)
    print("\n2. LEVEL 2 DATA")
    level2 = fetcher.get_level2(symbol, depth=5)
    if level2["available"]:
        print(json.dumps(level2, indent=2))
    else:
        print("   ⚠️  Level 2 data requires market depth subscription")
    
    # Example 3: Get news (may not work without subscription)
    print("\n3. NEWS")
    news = fetcher.get_news(symbol, count=5)
    if news:
        for item in news[:3]:
            print(f"  • {item['headline']}")
    else:
        print("   ⚠️  News requires news subscription")
    
    # # Example 4: Get options
    # print("\n4. OPTIONS CHAIN (top 5)")
    # options = fetcher.get_options(symbol, expiry_limit=1, strike_range=0.05)
    # if options:
    #     for opt in options[:5]:
    #         print(f"  {opt['expiry']} ${opt['strike']} {opt['right']}: "
    #               f"Bid ${opt['bid']} Ask ${opt['ask']}")
    # else:
    #     print("   No options data available")
    
    # Example 5: Get historical data (this should always work)
    print("\n4. HISTORICAL DATA (last 5 days)")
    historical = fetcher.get_historical(symbol, duration="5 D", bar_size="1 day")
    for bar in historical[-5:]:
        date = bar['date'][:10] if len(bar['date']) > 10 else bar['date']
        print(f"  {date}: Close ${bar['close']}")
    
    # Check subscription status
    print("\n5. SUBSCRIPTION STATUS")
    status = fetcher.get_subscription_status()
    print(f"  Real-time data: {'✓' if status['realtime_data'] else '✗ (using delayed/historical)'}")
    print(f"  Level 2: {'✓' if status['level2'] else '✗ (requires subscription)'}")
    print(f"  News: {'✓' if status['news'] else '✗ (requires subscription)'}")
    
    # Close connection
    fetcher.close()