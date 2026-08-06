"""
app/services/price_feed.py

Real (delayed, not tick-live) price feed via yfinance. No credentials
required, works anywhere including Render. This replaces whatever
hardcoded/mock price source is currently feeding the dashboard.

Note: yfinance data for NSE is typically 15-20 min delayed, not
millisecond-live. That's the honest tradeoff until Angel One is wired
in properly (and that only works with a static IP anyway).
"""
import yfinance as yf
from functools import lru_cache
from datetime import datetime, timedelta

_cache = {}
_CACHE_TTL_SECONDS = 60  # don't hammer yfinance on every dashboard refresh


def _nse_symbol(symbol: str) -> str:
    """NSE symbols need a .NS suffix for yfinance."""
    return symbol if symbol.endswith(".NS") else f"{symbol}.NS"


def get_live_price(symbol: str) -> dict:
    now = datetime.utcnow()
    cached = _cache.get(symbol)
    if cached and (now - cached["fetched_at"]).total_seconds() < _CACHE_TTL_SECONDS:
        return cached["data"]

    ticker = yf.Ticker(_nse_symbol(symbol))
    info = ticker.fast_info  # cheaper than .info, has what we need

    data = {
        "symbol": symbol,
        "last_price": round(info["last_price"], 2),
        "previous_close": round(info["previous_close"], 2),
        "day_high": round(info["day_high"], 2),
        "day_low": round(info["day_low"], 2),
        "change_pct": round(
            (info["last_price"] - info["previous_close"]) / info["previous_close"] * 100, 2
        ),
        "fetched_at": now.isoformat(),
    }
    _cache[symbol] = {"data": data, "fetched_at": now}
    return data


def get_live_prices_bulk(symbols: list) -> dict:
    """Fetch multiple symbols; fails individually rather than all-or-nothing."""
    result = {}
    for sym in symbols:
        try:
            result[sym] = get_live_price(sym)
        except Exception as e:
            result[sym] = {"symbol": sym, "error": str(e)}
    return result