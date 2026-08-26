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
from datetime import datetime, timedelta, timezone

import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import settings

from app.cache import ttl_cache


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


@ttl_cache(ttl_seconds=900)
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


@ttl_cache(ttl_seconds=900)
def fetch_multi_period_angel(symbol: str) -> dict:
    """
    Angel One version of fetch_multi_period() - same trailing-return and
    volatility computation, sourced from get_angel_ohlc() instead of
    yfinance. pe_ratio and sector are always None here: Angel's SmartAPI
    has no fundamentals endpoint at all (same limitation documented on
    /discover/stock-info), so there's nothing to fetch them from.

    NOT live-tested against Angel's real servers - verify a batch scan
    actually returns results before relying on this.
    """
    from app.services.angel_feed import get_angel_ohlc

    bare_symbol = symbol.replace(".NS", "")
    try:
        candles = get_angel_ohlc(bare_symbol, period="2y")
    except Exception:
        return None

    if not candles or len(candles) < 30:
        return None

    current_price = candles[-1]["close"]
    latest_date = datetime.fromtimestamp(candles[-1]["time"], tz=timezone.utc)

    returns = {}
    for label, cal_days in PERIOD_WINDOWS_TRADING_DAYS.items():
        cutoff = latest_date - timedelta(days=cal_days)
        past_candles = [c for c in candles if datetime.fromtimestamp(c["time"], tz=timezone.utc) <= cutoff]
        if not past_candles:
            returns[label] = None
        else:
            past_price = past_candles[-1]["close"]
            returns[label] = round((current_price - past_price) / past_price * 100, 2) if past_price else None

    closes = [c["close"] for c in candles]
    daily_returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
    volatility_pct = None
    if len(daily_returns) >= 10:
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        volatility_pct = round((variance ** 0.5) * (252 ** 0.5) * 100, 2)

    return {
        "symbol": bare_symbol,
        "last_price": round(current_price, 2),
        "returns_pct": returns,
        "pe_ratio": None,  # Angel has no fundamentals endpoint
        "sector": None,    # Angel has no fundamentals endpoint
        "volatility_pct": volatility_pct,
        "data_points": len(candles),
    }


def fetch_index_baseline_angel() -> dict:
    """Angel One version of fetch_index_baseline(). Returns None (skipping
    relative strength, not crashing the scan) if the Nifty token can't be
    confidently found - see get_nifty_token()'s docstring for why that
    lookup isn't guaranteed."""
    from app.services.angel_feed import get_nifty_token, _get_ohlc_by_token

    token = get_nifty_token()
    if not token:
        return None
    try:
        candles = _get_ohlc_by_token(token, period="2y", label="NIFTY50")
    except Exception:
        return None
    if not candles or len(candles) < 30:
        return None

    current_price = candles[-1]["close"]
    latest_date = datetime.fromtimestamp(candles[-1]["time"], tz=timezone.utc)
    returns = {}
    for label, cal_days in PERIOD_WINDOWS_TRADING_DAYS.items():
        cutoff = latest_date - timedelta(days=cal_days)
        past_candles = [c for c in candles if datetime.fromtimestamp(c["time"], tz=timezone.utc) <= cutoff]
        returns[label] = None
        if past_candles and past_candles[-1]["close"]:
            past_price = past_candles[-1]["close"]
            returns[label] = round((current_price - past_price) / past_price * 100, 2)
    return returns


def scan_long_term(symbols: list = None, rank_by: str = "1y") -> list:
    symbols = symbols or EXTENDED_UNIVERSE
    use_angel = settings.PRICE_FEED == "angel"
    fetch_fn = fetch_multi_period_angel if use_angel else fetch_multi_period
    index_returns = fetch_index_baseline_angel() if use_angel else fetch_index_baseline()
    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_fn, sym): sym for sym in symbols}
        # No overall timeout here on purpose: the `with` block's own
        # executor.shutdown(wait=True) already blocks until every submitted
        # future finishes, no matter what. A shorter timeout on as_completed()
        # doesn't save any time - it just abandons the iteration early and
        # throws away results for symbols whose fetch had already completed
        # (or was about to). That was the real cause of the "12/42" bug: full
        # wait time paid, most of the data discarded anyway. Each individual
        # fetch is still bounded by PER_TICKER_TIMEOUT_SECONDS below.
        for future in as_completed(futures):
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
