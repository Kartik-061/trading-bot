"""
app/api/routes.py
REST endpoints, same shape as BookIQ's DRF views: thin controllers,
real logic lives in bot_runner / backtest / broker modules.
"""
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Trade, BotSession, PriceTick
from app.backtest.engine import run_backtest
from app.strategies import STRATEGY_REGISTRY
from app.data_feed.feeds import SimulatedFeed
from app.screener.candidates import scan_universe, NIFTY_UNIVERSE
from app.screener.long_term import scan_long_term, PERIOD_WINDOWS_TRADING_DAYS
from app.screener.nse_universe import get_universe_batch
from app.backtest.historical_data import fetch_historical_closes, fetch_historical_ohlcv, fetch_ohlc_for_chart
from app.backtest.portfolio_stats import test_significance
from fastapi import HTTPException

from app.auth import verify_api_key
from app.rate_limit import limiter

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/prices/{symbol}/candles")
def get_candles(symbol: str, interval_seconds: int = Query(5, gt=0, le=3600),
                 limit: int = Query(100, gt=0, le=1000), db: Session = Depends(get_db)):
    """Aggregates raw price ticks into OHLC candles for charting."""
    ticks = (
        db.query(PriceTick)
        .filter(PriceTick.symbol == symbol.upper())
        .order_by(PriceTick.timestamp)
        .all()
    )
    if not ticks:
        return []

    candles = []
    bucket = []
    bucket_start = ticks[0].timestamp

    def flush(bucket, bucket_start):
        if not bucket:
            return None
        prices = [t.price for t in bucket]
        return {
            "time": int(bucket_start.timestamp()),
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
        }

    for t in ticks:
        if (t.timestamp - bucket_start).total_seconds() >= interval_seconds and bucket:
            candles.append(flush(bucket, bucket_start))
            bucket = []
            bucket_start = t.timestamp
        bucket.append(t)

    last = flush(bucket, bucket_start)
    if last:
        candles.append(last)

    return candles[-limit:]


@router.get("/discover")
@limiter.limit("10/minute")
def discover(request: Request, limit: int = Query(10, gt=0, le=100)):
    """
    Scans a wider universe of NSE stocks for research purposes: real momentum
    and valuation data, ranked transparently. NOT investment advice, NOT a
    prediction of future returns - a starting point for your own judgment.
    """
    results = scan_universe()
    return {
        "disclaimer": "Informational research data only, not investment advice. "
                       "Past momentum and valuation do not guarantee future returns.",
        "candidates": results[:limit],
    }


@router.post("/backtest")
def backtest(strategy: str = "ema_rsi", symbol: str = "SBIFUNDS",
             starting_price: float = Query(598.0, gt=0),
             num_ticks: int = Query(500, gt=0, le=10000),
             starting_capital: float = Query(100000, gt=0)):
    """
    Runs a strategy over simulated historical data as a placeholder.
    Swap the price generation here for real historical candles from
    Angel One's historical data API once you're ready to test on real data -
    that's the next real milestone, not this endpoint's job to fake.
    """
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        return {"status": False, "reason": f"unknown_strategy: {strategy}"}

    feed = SimulatedFeed({symbol: starting_price})
    prices = [feed.get_price(symbol) for _ in range(num_ticks)]

    result = run_backtest(strategy_cls(), prices, starting_capital=starting_capital)
    return {
        "strategy": strategy,
        "starting_capital": result.starting_capital,
        "final_value": result.final_value,
        "total_return_pct": result.total_return_pct,
        "total_trades": result.total_trades,
        "win_rate_pct": result.win_rate,
        "max_drawdown_pct": result.max_drawdown_pct,
        "total_costs_rs": result.total_costs,
        "note": "Backtested on simulated data - run against real historical candles before trusting these numbers.",
    }


@router.post("/backtest/historical")
@limiter.limit("10/minute")
def backtest_historical(request: Request, strategy: str = "ema_rsi", symbol: str = "RELIANCE",
                         interval: str = "5m", period: str = "60d",
                         starting_capital: float = Query(100000, gt=0)):
    """
    Runs a strategy over REAL historical price data from Yahoo Finance.
    This is the honest test - simulated backtest tells you the code works,
    this one tells you whether the strategy has any actual edge.
    """
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        return {"status": False, "reason": f"unknown_strategy: {strategy}"}

    try:
        prices = fetch_historical_closes(symbol, interval=interval, period=period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = run_backtest(strategy_cls(), prices, starting_capital=starting_capital)
    return {
        "strategy": strategy,
        "symbol": symbol.upper(),
        "interval": interval,
        "period": period,
        "num_candles": len(prices),
        "starting_capital": result.starting_capital,
        "final_value": result.final_value,
        "total_return_pct": result.total_return_pct,
        "total_trades": result.total_trades,
        "win_rate_pct": result.win_rate,
        "max_drawdown_pct": result.max_drawdown_pct,
        "total_costs_rs": result.total_costs,
        "note": "Tested on real historical price data.",
    }


@router.post("/backtest/batch")
@limiter.limit("5/minute")
def backtest_batch(request: Request, symbols: str = "SBIFUNDS,RELIANCE,TCS,INFY,HDFCBANK",
                    interval: str = "5m", period: str = "60d",
                    starting_capital: float = Query(100000, gt=0)):
    """
    Runs several strategy variants across every symbol given, on real
    historical data. One flat result on one stock proves little - this
    grid is what actually tells you whether there's a pattern (e.g.
    "mean reversion works on volatile small-caps but not on RELIANCE").
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    variants = [
        {"name": "ema_rsi_default", "cls": STRATEGY_REGISTRY["ema_rsi"], "kwargs": {}},
        {"name": "ema_rsi_fast", "cls": STRATEGY_REGISTRY["ema_rsi"], "kwargs": {"ema_short": 5, "ema_long": 13}},
        {"name": "mean_reversion_default", "cls": STRATEGY_REGISTRY["mean_reversion"], "kwargs": {}},
        {"name": "mean_reversion_tight_rsi", "cls": STRATEGY_REGISTRY["mean_reversion"],
         "kwargs": {"oversold": 35, "overbought": 65}},
        {"name": "mean_reversion_tight_stop", "cls": STRATEGY_REGISTRY["mean_reversion"],
         "kwargs": {"stop_loss_pct": 1.0}},
        {"name": "mean_reversion_fast_exit", "cls": STRATEGY_REGISTRY["mean_reversion"],
         "kwargs": {"stop_loss_pct": 1.0, "take_profit_rsi": 45}},
        # Swing-timeframe variants - much wider stop so normal daily noise
        # doesn't trigger a false exit. Use these with interval="1d".
        {"name": "ema_rsi_swing", "cls": STRATEGY_REGISTRY["ema_rsi"],
         "kwargs": {"ema_short": 20, "ema_long": 50}},
        {"name": "mean_reversion_swing", "cls": STRATEGY_REGISTRY["mean_reversion"],
         "kwargs": {"stop_loss_pct": 6.0, "take_profit_rsi": 60}},
    ]

    results = []
    for symbol in symbol_list:
        try:
            prices = fetch_historical_closes(symbol, interval=interval, period=period)
        except ValueError as e:
            results.append({"symbol": symbol, "error": str(e)})
            continue

        for variant in variants:
            strategy = variant["cls"](**variant["kwargs"])
            result = run_backtest(strategy, prices, starting_capital=starting_capital)
            results.append({
                "symbol": symbol,
                "strategy_variant": variant["name"],
                "num_candles": len(prices),
                "total_return_pct": result.total_return_pct,
                "total_trades": result.total_trades,
                "win_rate_pct": result.win_rate,
                "max_drawdown_pct": result.max_drawdown_pct,
                "total_costs_rs": result.total_costs,
            })

    results.sort(key=lambda r: r.get("total_return_pct", -9999), reverse=True)
    return {
        "note": "Grid backtest: multiple strategy variants x multiple symbols, on real historical data.",
        "results": results,
    }


@router.post("/backtest/significance")
@limiter.limit("5/minute")
def backtest_significance(request: Request, strategy: str = "ema_rsi", symbols: str = "SBIFUNDS,RELIANCE,TCS,INFY,HDFCBANK",
                           interval: str = "5m", period: str = "60d",
                           starting_capital: float = Query(100000, gt=0),
                           ema_short: int = None, ema_long: int = None,
                           oversold: int = None, overbought: int = None,
                           stop_loss_pct: float = None, take_profit_rsi: int = None,
                           volume_multiplier: float = None):
    """
    The rigorous version of 'does this strategy work' - pools every trade's
    P&L across every symbol given and tests whether the average trade result
    is statistically distinguishable from zero, instead of eyeballing which
    stocks happened to look positive.
    """
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        return {"status": False, "reason": f"unknown_strategy: {strategy}"}

    kwargs = {}
    for name, val in [("ema_short", ema_short), ("ema_long", ema_long),
                      ("oversold", oversold), ("overbought", overbought),
                      ("stop_loss_pct", stop_loss_pct), ("take_profit_rsi", take_profit_rsi),
                      ("volume_multiplier", volume_multiplier)]:
        if val is not None:
            kwargs[name] = val

    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    symbol_data = {}

    for symbol in symbol_list:
        try:
            if strategy == "volume_confirmed" or strategy == "breakout":
                symbol_data[symbol] = fetch_historical_ohlcv(symbol, interval=interval, period=period)
            else:
                symbol_data[symbol] = fetch_historical_closes(symbol, interval=interval, period=period)
        except ValueError:
            continue  # skip symbols that failed to fetch, don't kill the whole test

    if not symbol_data:
        return {"status": False, "reason": "No data fetched for any symbol."}

    result = test_significance(strategy_cls, kwargs, symbol_data, starting_capital=starting_capital)
    result["strategy"] = strategy
    result["strategy_kwargs"] = kwargs
    return result


@router.get("/discover/long-term")
@limiter.limit("10/minute")
def discover_long_term(request: Request, rank_by: Literal["3mo", "6mo", "1y", "2y"] = "1y",
                        limit: int = Query(15, gt=0, le=100)):
    """
    Ranks a wide universe of NSE stocks (large + mid cap, 42 names) by
    trailing return over the chosen holding period. Purely backward-looking
    historical data - NOT a prediction of future performance. Use this to
    narrow down names worth your own research, not as a buy signal.
    """
    results = scan_long_term(rank_by=rank_by)
    return {
        "disclaimer": "Backward-looking historical performance only. Past returns over "
                       "any period do not predict future returns. Not investment advice - "
                       "use this to narrow down names worth your own research.",
        "ranked_by": rank_by,
        "candidates": results[:limit],
    }


@router.get("/discover/universe-batch")
@limiter.limit("5/minute")
def discover_universe_batch(request: Request, offset: int = Query(0, ge=0),
                             batch_size: int = Query(50, gt=0, le=500),
                             rank_by: Literal["3mo", "6mo", "1y", "2y"] = "1y"):
    """
    Scans a PAGE of the full ~2,000-stock NSE universe (real official master
    list, same source Groww/Angel One use). One page at a time on purpose -
    scanning all ~2000 in one request would take many minutes and likely
    trigger Yahoo Finance rate limiting. Page through with offset: 0, 50,
    100, 150... until has_more is false.

    Needs data/EQUITY_L.csv downloaded from:
    https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
    """
    try:
        batch_info = get_universe_batch(offset=offset, batch_size=batch_size)
    except FileNotFoundError as e:
        return {"status": False, "reason": str(e)}

    results = scan_long_term(symbols=batch_info["symbols"], rank_by=rank_by)

    return {
        "disclaimer": "Backward-looking historical performance only. Past returns over "
                       "any period do not predict future returns. Not investment advice.",
        "total_symbols_in_universe": batch_info["total_symbols_in_universe"],
        "offset": batch_info["offset"],
        "batch_size": batch_info["batch_size"],
        "has_more": batch_info["has_more"],
        "next_offset": batch_info["next_offset"],
        "scanned_successfully": len(results),
        "ranked_by": rank_by,
        "candidates": results,
    }


@router.get("/discover/stock-chart/{symbol}")
@limiter.limit("15/minute")
def stock_chart(request: Request, symbol: str, period: Literal["1mo", "3mo", "6mo", "1y", "2y", "5y"] = "1y"):
    """
    Full OHLC candles for one stock, for the long-term screener's
    click-to-view-detail chart.
    """
    try:
        candles = fetch_ohlc_for_chart(symbol, period=period)
    except ValueError as e:
        return {"status": False, "reason": str(e)}

    return {"symbol": symbol.upper(), "period": period, "candles": candles}

from app.services.price_feed import get_live_price, get_live_prices_bulk

@router.get("/prices/{symbol}/live")
def live_price(symbol: str):
    """Real (delayed ~15-20min) price from Yahoo Finance. No credentials needed."""
    return get_live_price(symbol.upper())


@router.get("/prices/live")
def live_prices_bulk(symbols: str = "SBIFUNDS,RELIANCE,TCS,INFY,HDFCBANK"):
    """Same as above but for multiple symbols, comma-separated."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    return get_live_prices_bulk(symbol_list)

@router.get("/discover/stock-info/{symbol}")
@limiter.limit("15/minute")
def stock_info(request: Request, symbol: str):
    """Basic fundamentals for stock research - separate from fast_info-based
    live prices since .info is heavier; rate-limited accordingly."""
    import yfinance as yf
    try:
        ticker = yf.Ticker(f"{symbol.upper()}.NS")
        info = ticker.info
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Yahoo Finance rate limit hit or temporarily unavailable. "
                   "This demo uses a free data source with no SLA — try again in a few minutes.",
        )
    return {
        "symbol": symbol.upper(),
        "name": info.get("longName"),
        "sector": info.get("sector"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "dividend_yield": info.get("dividendYield"),
    }