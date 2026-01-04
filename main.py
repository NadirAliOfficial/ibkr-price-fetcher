from ib_insync import *
from dataclasses import dataclass
from datetime import datetime
import math
import logging

# ---------- SILENCE IBKR NOISE ----------
logging.getLogger("ib_insync").setLevel(logging.CRITICAL)

util.startLoop()

# ---------- CONFIG ----------
HOST = "127.0.0.1"
PORT = 7497          # 4002 for Gateway
CLIENT_ID = 77
TICKER_FILE = "tickers.txt"
TIMEOUT = 2
# ----------------------------


@dataclass
class PriceResult:
    symbol: str
    price: float
    source: str
    time: str
    note: str


def load_tickers(path=TICKER_FILE):
    with open(path) as f:
        return [
            line.strip().upper()
            for line in f
            if line.strip() and not line.startswith("#")
        ]


class IBKRPriceService:

    def __init__(self):
        self.ib = IB()
        self.ib.connect(HOST, PORT, clientId=CLIENT_ID)
        self.ib.errorEvent += self._on_error

    def _on_error(self, reqId, errorCode, errorString, contract):
        # Hide all non-critical IBKR noise
        if errorCode in (10089, 300, 10167):
            return

    def _valid(self, price):
        return price is not None and not math.isnan(price)

    def get_price(self, symbol):
        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)

        # ---- LIVE ----
        self.ib.reqMarketDataType(1)
        ticker = self.ib.reqMktData(contract)
        self.ib.sleep(TIMEOUT)

        if self._valid(ticker.last):
            return self._result(symbol, ticker.last, "LIVE", "Live market price")

        # ---- DELAYED ----
        self.ib.reqMarketDataType(3)
        ticker = self.ib.reqMktData(contract)
        self.ib.sleep(TIMEOUT)

        if self._valid(ticker.last):
            return self._result(symbol, ticker.last, "DELAYED", "Delayed market price")

        # ---- HISTORICAL ----
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True
        )

        return self._result(
            symbol,
            bars[-1].close,
            "HISTORICAL",
            "Market closed or no subscription"
        )

    def _result(self, symbol, price, source, note):
        return PriceResult(
            symbol=symbol,
            price=round(price, 2),
            source=source,
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            note=note
        )

    def close(self):
        self.ib.disconnect()


# ---------- MAIN ----------
if __name__ == "__main__":
    symbols = load_tickers()
    service = IBKRPriceService()

    print("\nSymbol | Price     | Source       | Note")
    print("-" * 60)

    for sym in symbols:
        try:
            r = service.get_price(sym)
            print(
                f"{r.symbol:6} | "
                f"{r.price:9} | "
                f"{r.source:12} | "
                f"{r.note}"
            )
        except Exception:
            print(f"{sym:6} | ERROR     | FAILED       | Could not fetch price")

    service.close()
