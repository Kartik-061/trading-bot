"""
app/screener/candidates.py

Pulls real data (not predictions) on a wider universe of NSE stocks so you can
do your own research faster, instead of guessing. Ranks by a transparent,
adjustable formula - momentum + a value tilt. This is a research aid, not a
recommendation engine. No model, mine included, can reliably predict which
stock goes up next; what this CAN do honestly is surface real numbers so you
spend your judgment on 15 pre-filtered names instead of 500 random ones.

Needs internet access to Yahoo Finance - won't work in a sandboxed/offline
environment, only on your actual machine.
"""
import yfinance as yf
from app.cache import ttl_cache

# Starter universe - large, liquid NSE stocks. Expand this list freely;
# yfinance just needs the ".NS" suffix for NSE tickers.
NIFTY_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "WIPRO.NS", "ADANIENT.NS", "TATAMOTORS.NS",
]


def fetch_candidate(symbol: str) -> dict:
    """
    Pulls basic fundamentals + 3-month momentum for one symbol.
    Returns None on failure (bad ticker, no data, network issue) rather than
    raising, so one bad symbol doesn't kill a whole batch scan.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="3mo")

        if hist.empty or len(hist) < 2:
            return None

        start_price = float(hist["Close"].iloc[0])
        end_price = float(hist["Close"].iloc[-1])
        momentum_3m_pct = round((end_price - start_price) / start_price * 100, 2)

        return {
            "symbol": symbol.replace(".NS", ""),
            "last_price": round(end_price, 2),
            "momentum_3m_pct": momentum_3m_pct,
            "pe_ratio": info.get("trailingPE"),
            "market_cap_cr": round(info.get("marketCap", 0) / 1e7, 0) if info.get("marketCap") else None,
            "sector": info.get("sector"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception:
        return None


def score_candidate(c: dict) -> float:
    """
    Transparent scoring, not a black box:
    - momentum_3m_pct: rewards recent uptrend (weight 1.0)
    - value tilt: modest bonus for lower P/E, relative to a rough 25x anchor
      (weight 0.3) - keeps pure momentum chasing in check a little.
    Adjust the weights yourself once you have opinions - this is a starting
    point, not a final answer.
    """
    momentum_score = c["momentum_3m_pct"]
    value_score = 0
    if c.get("pe_ratio") and c["pe_ratio"] > 0:
        value_score = (25 - c["pe_ratio"]) * 0.3
    return round(momentum_score + value_score, 2)


@ttl_cache(ttl_seconds=300)
def scan_universe(symbols: list = None) -> list:
    """
    Scans the universe, scores each, returns ranked highest-first.
    Skips symbols that failed to fetch (bad ticker, no internet, etc).
    """
    symbols = symbols or NIFTY_UNIVERSE
    results = []
    for sym in symbols:
        candidate = fetch_candidate(sym)
        if candidate:
            candidate["research_score"] = score_candidate(candidate)
            results.append(candidate)

    results.sort(key=lambda c: c["research_score"], reverse=True)
    return results
