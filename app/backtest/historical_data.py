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

    Always raises ValueError on any failure (bad ticker, network hiccup,
    empty data) so callers only ever need to catch one exception type.
    """
    try:
        ticker = yf.Ticker(f"{symbol.upper()}.NS")
        hist = ticker.history(interval=interval, period=period)
    except Exception as e:
        raise ValueError(f"Failed to fetch data for {symbol}: {e}")

    if hist.empty:
        raise ValueError(
            f"No historical data returned for {symbol} at interval={interval}, period={period}. "
            f"Check the symbol is correct and actively traded."
        )

    return [round(float(p), 2) for p in hist["Close"].tolist()]