"""
app/screener/candidates.py

Pulls real data (not predictions) on a wider universe of NSE stocks so you can
do your own research faster, instead of guessing. Ranks by a transparent,
adjustable formula - momentum + a value tilt. This is a research aid, not a
recommendation engine.

Fetches run in parallel with a hard per-ticker timeout - Yahoo Finance
sometimes stalls or rate-limits a single request, and without a timeout that
one stuck ticker would block the entire scan indefinitely.
"""
import math
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

NIFTY_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "WIPRO.NS", "ADANIENT.NS", "TATAMOTORS.NS",
]

PER_TICKER_TIMEOUT_SECONDS = 8


def clean(val):
    """NaN/inf aren't valid JSON - convert them to None."""
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except TypeError:
        pass
    return val


def fetch_candidate(symbol: str) -> dict:
    """Pulls basic fundamentals + 3-month momentum for one symbol. Returns
    None on any failure so one bad symbol doesn't kill the whole batch."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="3mo")

        if hist.empty or len(hist) < 2:
            return None

        start_price = float(hist["Close"].iloc[0])
        end_price = float(hist["Close"].iloc[-1])
        momentum_3m_pct = round((end_price - start_price) / start_price * 100, 2)

        pe_ratio = None
        market_cap_cr = None
        sector = None

        try:
            fast = ticker.fast_info
            if fast.get("marketCap"):
                market_cap_cr = round(fast["marketCap"] / 1e7, 0)
        except Exception:
            pass

        try:
            info = ticker.info
            pe_ratio = info.get("trailingPE")
            sector = info.get("sector")
        except Exception:
            pass

        return {
            "symbol": symbol.replace(".NS", ""),
            "last_price": clean(round(end_price, 2)),
            "momentum_3m_pct": clean(momentum_3m_pct),
            "pe_ratio": clean(pe_ratio),
            "market_cap_cr": clean(market_cap_cr),
            "sector": sector,
        }
    except Exception:
        return None


def score_candidate(c: dict) -> float:
    momentum_score = c["momentum_3m_pct"] or 0
    value_score = 0
    if c.get("pe_ratio") and c["pe_ratio"] > 0:
        value_score = (25 - c["pe_ratio"]) * 0.3
    return round(momentum_score + value_score, 2)


def scan_universe(symbols: list = None) -> list:
    """Scans the universe IN PARALLEL with a hard timeout per ticker, so a
    single stuck/rate-limited request can't freeze the whole scan."""
    symbols = symbols or NIFTY_UNIVERSE
    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_candidate, sym): sym for sym in symbols}
        for future in as_completed(futures, timeout=PER_TICKER_TIMEOUT_SECONDS * 3):
            try:
                candidate = future.result(timeout=PER_TICKER_TIMEOUT_SECONDS)
                if candidate:
                    candidate["research_score"] = score_candidate(candidate)
                    results.append(candidate)
            except Exception:
                continue

    results.sort(key=lambda c: c["research_score"], reverse=True)
    return results