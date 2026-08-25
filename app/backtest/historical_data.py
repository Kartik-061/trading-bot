"""
app/backtest/historical_data.py

Pulls REAL historical price candles from Yahoo Finance for backtesting -
same data source as the research screener, just historical instead of
current. This is what turns the backtest from "tested on random noise"
into "tested on what this stock actually did."

Limitation to know: Yahoo only keeps 5-minute-interval data for the last
60 days. For longer history, use a bigger interval (e.g. "1d") but you'll
get far fewer candles for an intraday strategy to react to.
"""
import logging
import time

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger("historical_data")

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [5, 15, 30]  # widening backoff, not a fixed retry delay


def _fetch_history_with_retry(ticker_symbol: str, interval: str, period: str):
    """Yahoo's free/unofficial API rate-limits bursts of sequential
    requests - hit this for real running a 43-symbol batch backtest with
    no delay between calls. Retries with widening backoff specifically on
    YFRateLimitError; any other error still fails immediately (a genuinely
    bad symbol shouldn't sit through 3 pointless retries)."""
    ticker = yf.Ticker(ticker_symbol)
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            return ticker.history(interval=interval, period=period)
        except YFRateLimitError as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_SECONDS[attempt]
                logger.warning(
                    f"Yahoo rate-limited fetching {ticker_symbol} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}), waiting {wait}s: {e}"
                )
                time.sleep(wait)
    raise RuntimeError(
        f"Yahoo Finance rate-limited {ticker_symbol} after {_MAX_RETRIES} retries. "
        f"This usually means too many symbols were requested back-to-back - try a "
        f"smaller batch, or wait a few minutes and retry. Original error: {last_error}"
    )


def fetch_historical_closes(symbol: str, interval: str = "5m", period: str = "60d") -> list:
    """
    Returns a plain list of closing prices, oldest first - exactly what
    run_backtest() in engine.py expects.

    symbol: NSE symbol without .NS suffix (e.g. "RELIANCE") - suffix added here.
    interval: "5m", "15m", "1h", "1d", etc (Yahoo's supported intervals).
    period: how far back to pull. "60d" is the max Yahoo allows for 5m data.
    """
    hist = _fetch_history_with_retry(f"{symbol.upper()}.NS", interval, period)

    if hist.empty:
        raise ValueError(
            f"No historical data returned for {symbol} at interval={interval}, period={period}. "
            f"Check the symbol is correct and actively traded."
        )

    return [round(float(p), 2) for p in hist["Close"].tolist() if p == p]

def fetch_historical_ohlcv(symbol: str, interval: str = "5m", period: str = "60d") -> list:
    """
    Returns a list of {"close": float, "volume": float} dicts, oldest first -
    what volume-aware strategies need. run_backtest() in engine.py accepts
    either this format or the plain float list from fetch_historical_closes.
    """
    hist = _fetch_history_with_retry(f"{symbol.upper()}.NS", interval, period)

    if hist.empty:
        raise ValueError(
            f"No historical data returned for {symbol} at interval={interval}, period={period}. "
            f"Check the symbol is correct and actively traded."
        )

    return [
    {"close": round(float(row["Close"]), 2), "volume": float(row["Volume"])}
    for _, row in hist.iterrows()
    if row["Close"] == row["Close"]
]


def fetch_ohlc_for_chart(symbol: str, period: str = "1y", interval: str = "1d") -> list:
    """
    Full OHLC candles (not just close) for charting a stock's history -
    used by the long-term screener's click-to-view-detail feature.
    Returns candles in the {time, open, high, low, close} shape the
    Lightweight Charts library expects.
    """
    ticker = yf.Ticker(f"{symbol.upper()}.NS")
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        raise ValueError(f"No historical data for {symbol} at period={period}")

    candles = []
    for ts, row in hist.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        if o != o or h != h or l != l or c != c:  # skip if any value is NaN
            continue
        candles.append({
            "time": int(ts.timestamp()),
            "open": round(float(o), 2),
            "high": round(float(h), 2),
            "low": round(float(l), 2),
            "close": round(float(c), 2),
        })
    return candles
