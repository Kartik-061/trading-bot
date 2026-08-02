"""
app/screener/long_term.py

Historical trailing-return screener across multiple holding periods -
tests what a stock has actually done over the past 3mo/6mo/1yr/2yr.
Purely backward-looking: what a stock did in the past does not guarantee
what it does next. This is a research aid to narrow a large universe
down to a shortlist worth your own research - not a prediction.

Periods are calculated by actual CALENDAR DATE, not a fixed trading-day
count. A fixed count (e.g. "504 trading days = 2 years") is fragile -
real market data rarely lands on exactly that number due to holidays, so
a naive count-based cutoff often reports "not enough history" for stocks
that clearly do have 2 years of data. Comparing real dates avoids that.
"""
import math
from datetime import timedelta

import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed


def _clean(val):
    """NaN/inf aren't valid, honest data - convert to None. Some sources
    (like this one) hand back the literal string 'Infinity' instead of a
    real float infinity, so that needs an explicit check too."""
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("infinity", "-infinity", "nan"):
            return None
        return val
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except TypeError:
        pass
    return val


# Reasonably liquid, well-known large + mid-cap NSE names across sectors.
# Only used as the DEFAULT when no explicit symbol list is passed - the
# universe-batch endpoint passes real symbols from the NSE master list instead.
EXTENDED_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "WIPRO.NS", "ADANIENT.NS", "TATAMOTORS.NS",
    "PERSISTENT.NS", "COFORGE.NS", "LTIM.NS", "POLYCAB.NS", "DIXON.NS",
    "TRENT.NS", "PAGEIND.NS", "ASTRAL.NS", "CUMMINSIND.NS", "APLAPOLLO.NS",
    "KPITTECH.NS", "JUBLFOOD.NS", "IPCALAB.NS", "BALKRISHNAIND.NS",
    "YESBANK.NS", "IDEA.NS", "SUZLON.NS", "PNB.NS", "TATAPOWER.NS",
    "IDFCFIRSTB.NS", "RVNL.NS", "IRCTC.NS",
]

# Calendar days, not trading days - avoids the fragile "exact count" problem.
PERIOD_WINDOWS_TRADING_DAYS = {
    "3mo": 90,
    "6mo": 182,
    "1y": 365,
    "2y": 730,
}

PER_TICKER_TIMEOUT_SECONDS = 8


def fetch_multi_period(symbol: str) -> dict:
    """
    Pulls 2 years of daily closes ONCE, computes trailing return over every
    holding-period window from that single fetch by real calendar date.
    Returns None on any failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y", interval="1d")

        if hist.empty or len(hist) < 30:
            return None

        current_price = float(hist["Close"].iloc[-1])
        latest_date = hist.index[-1]

        returns = {}
        for label, cal_days in PERIOD_WINDOWS_TRADING_DAYS.items():
            cutoff = latest_date - timedelta(days=cal_days)
            past_rows = hist[hist.index <= cutoff]

            if past_rows.empty:
                returns[label] = None
            else:
                past_price = float(past_rows["Close"].iloc[-1])
                returns[label] = round((current_price - past_price) / past_price * 100, 2)

        pe_ratio = None
        sector = None
        try:
            info = ticker.info
            pe_ratio = info.get("trailingPE")
            sector = info.get("sector")
        except Exception:
            pass

        # Annualized volatility from daily returns - how much this stock swings,
        # not a prediction, just the real risk you'd be taking holding it.
        volatility_pct = None
        daily_returns = hist["Close"].pct_change().dropna()
        if len(daily_returns) >= 10:
            volatility_pct = round(float(daily_returns.std()) * (252 ** 0.5) * 100, 2)

        return {
            "symbol": symbol.replace(".NS", ""),
            "last_price": round(current_price, 2),
            "returns_pct": returns,
            "pe_ratio": _clean(pe_ratio),
            "sector": sector,
            "volatility_pct": volatility_pct,
            "data_points": len(hist),
        }
    except Exception:
        return None


def fetch_index_baseline() -> dict:
    """
    Nifty 50 index returns for the same periods - fetched ONCE per scan, not
    once per stock. This is what makes 'relative strength' honest: did the
    stock actually beat the market, or did it just ride a market-wide rally
    that lifted almost everything? Returns None if the fetch fails - relative
    strength is then skipped rather than the whole scan failing.
    """
    result = fetch_multi_period("^NSEI")
    return result["returns_pct"] if result else None


def scan_long_term(symbols: list = None, rank_by: str = "1y") -> list:
    """
    Scans the universe in parallel, ranks by trailing return for the chosen
    holding period. rank_by: '3mo', '6mo', '1y', or '2y'.
    """
    symbols = symbols or EXTENDED_UNIVERSE
    index_returns = fetch_index_baseline()
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

    for r in results:
        stock_ret = r["returns_pct"].get(rank_by)
        index_ret = index_returns.get(rank_by) if index_returns else None
        if stock_ret is not None and index_ret is not None:
            r["relative_strength_pct"] = round(stock_ret - index_ret, 2)
        else:
            r["relative_strength_pct"] = None

    results.sort(key=lambda c: (c["returns_pct"].get(rank_by) is None,
                                 -(c["returns_pct"].get(rank_by) or 0)))
    return results
