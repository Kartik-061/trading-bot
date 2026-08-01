"""
app/screener/long_term.py

Historical trailing-return screener across multiple holding periods -
tests what a stock has actually done over the past 3mo/6mo/1yr/2yr.
Purely backward-looking: what a stock did in the past does not guarantee
what it does next. This is a research aid to narrow a large universe
(large + mid cap, not just 20 mega-caps) down to a shortlist worth your
own research for a chosen holding horizon - not a prediction.
"""
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# Reasonably liquid, well-known large + mid-cap NSE names across sectors.
# Not exhaustive - a real long-term screener would cover hundreds of names,
# but this is an honest wider starting universe, not just the mega-caps
# we'd been focused on before.
EXTENDED_UNIVERSE = [
    # Large-cap
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "WIPRO.NS", "ADANIENT.NS", "TATAMOTORS.NS",
    # Mid-cap / smaller, still liquid and well known
    "PERSISTENT.NS", "COFORGE.NS", "LTIM.NS", "POLYCAB.NS", "DIXON.NS",
    "TRENT.NS", "PAGEIND.NS", "ASTRAL.NS", "CUMMINSIND.NS", "APLAPOLLO.NS",
    "KPITTECH.NS", "JUBLFOOD.NS", "IPCALAB.NS", "BALKRISHNAIND.NS",
    "YESBANK.NS", "IDEA.NS", "SUZLON.NS", "PNB.NS", "TATAPOWER.NS",
    "IDFCFIRSTB.NS", "RVNL.NS", "IRCTC.NS",
]

PERIOD_WINDOWS_TRADING_DAYS = {
    "3mo": 63,
    "6mo": 126,
    "1y": 252,
    "2y": 504,
}

PER_TICKER_TIMEOUT_SECONDS = 8


def fetch_multi_period(symbol: str) -> dict:
    """
    Pulls 2 years of daily closes ONCE, computes trailing return over every
    holding-period window from that single fetch - efficient, one network
    call gives all 4 periods. Returns None on any failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y", interval="1d")

        if hist.empty or len(hist) < 30:
            return None

        closes = hist["Close"].tolist()
        current_price = float(closes[-1])

        returns = {}
        for label, days in PERIOD_WINDOWS_TRADING_DAYS.items():
            if len(closes) > days:
                past_price = float(closes[-days - 1])
            else:
                past_price = float(closes[0])
            returns[label] = round((current_price - past_price) / past_price * 100, 2)

        pe_ratio = None
        sector = None
        try:
            info = ticker.info
            pe_ratio = info.get("trailingPE")
            sector = info.get("sector")
        except Exception:
            pass

        return {
            "symbol": symbol.replace(".NS", ""),
            "last_price": round(current_price, 2),
            "returns_pct": returns,
            "pe_ratio": pe_ratio,
            "sector": sector,
            "data_points": len(closes),
        }
    except Exception:
        return None


def scan_long_term(symbols: list = None, rank_by: str = "1y") -> list:
    """
    Scans the universe in parallel (with per-ticker timeout, same pattern
    as the other screener), ranks by trailing return for the chosen
    holding period. rank_by: '3mo', '6mo', '1y', or '2y'.
    """
    symbols = symbols or EXTENDED_UNIVERSE
    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_multi_period, sym): sym for sym in symbols}
        for future in as_completed(futures, timeout=PER_TICKER_TIMEOUT_SECONDS * 3):
            try:
                candidate = future.result(timeout=PER_TICKER_TIMEOUT_SECONDS)
                if candidate:
                    results.append(candidate)
            except Exception:
                continue

    results.sort(key=lambda c: c["returns_pct"].get(rank_by, -9999), reverse=True)
    return results