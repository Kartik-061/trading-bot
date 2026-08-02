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
import yfinance as yf


def fetch_historical_closes(symbol: str, interval: str = "5m", period: str = "60d") -> list:
    """
    Returns a plain list of closing prices, oldest first - exactly what
    run_backtest() in engine.py expects.

    symbol: NSE symbol without .NS suffix (e.g. "RELIANCE") - suffix added here.
    interval: "5m", "15m", "1h", "1d", etc (Yahoo's supported intervals).
    period: how far back to pull. "60d" is the max Yahoo allows for 5m data.
    """
    ticker = yf.Ticker(f"{symbol.upper()}.NS")
    hist = ticker.history(interval=interval, period=period)

    if hist.empty:
        raise ValueError(
            f"No historical data returned for {symbol} at interval={interval}, period={period}. "
            f"Check the symbol is correct and actively traded."
        )

    return [round(float(p), 2) for p in hist["Close"].tolist()]


def fetch_historical_ohlcv(symbol: str, interval: str = "5m", period: str = "60d") -> list:
    """
    Returns a list of {"close": float, "volume": float} dicts, oldest first -
    what volume-aware strategies need. run_backtest() in engine.py accepts
    either this format or the plain float list from fetch_historical_closes.
    """
    ticker = yf.Ticker(f"{symbol.upper()}.NS")
    hist = ticker.history(interval=interval, period=period)

    if hist.empty:
        raise ValueError(
            f"No historical data returned for {symbol} at interval={interval}, period={period}. "
            f"Check the symbol is correct and actively traded."
        )

    return [
        {"close": round(float(row["Close"]), 2), "volume": float(row["Volume"])}
        for _, row in hist.iterrows()
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
        candles.append({
            "time": int(ts.timestamp()),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
        })
    return candles
