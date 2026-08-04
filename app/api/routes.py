"""
app/api/routes.py
REST endpoints, same shape as BookIQ's DRF views: thin controllers,
real logic lives in bot_runner / backtest / broker modules.
"""
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Trade, BotSession, PriceTick
from app.bot_runner import bot_runner
from app.backtest.engine import run_backtest
from app.strategies import STRATEGY_REGISTRY
from app.data_feed.feeds import SimulatedFeed
from app.screener.candidates import scan_universe, NIFTY_UNIVERSE
from app.screener.long_term import scan_long_term, PERIOD_WINDOWS_TRADING_DAYS
from app.screener.nse_universe import get_universe_batch
from app.backtest.historical_data import fetch_historical_closes, fetch_historical_ohlcv, fetch_ohlc_for_chart
from app.backtest.portfolio_stats import test_significance

from app.auth import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/bot/start")
def start_bot(symbols: Optional[str] = None, strategy: str = "ema_rsi",
              tick_seconds: float = Query(2, gt=0, le=300)):
    """symbols: comma-separated, e.g. 'SBIFUNDS,RELIANCE,TCS'. Omit to use the default watchlist."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    return bot_runner.start(symbols=symbol_list, strategy_name=strategy, tick_seconds=tick_seconds)


@router.get("/watchlist/screener")
def screener():
    """Ranks the watchlist by recent momentum + current signal. Honest 'best stock' finder -
    not a prediction, just which symbols are moving and what the strategy currently says."""
    return bot_runner.screener()


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


@router.post("/bot/stop")
def stop_bot():
    return bot_runner.stop()


@router.get("/bot/status")
def bot_status():
    return bot_runner.status()


@router.get("/trades")
def list_trades(limit: int = Query(50, gt=0, le=500), db: Session = Depends(get_db)):
    trades = db.query(Trade).order_by(desc(Trade.timestamp)).limit(limit).all()
    return [
        {
            "id": t.id, "timestamp": t.timestamp.isoformat(), "symbol": t.symbol,
            "side": t.side, "qty": t.qty, "price": t.price, "value": t.value,
            "cash_after": t.cash_after, "is_live": t.is_live, "strategy": t.strategy_name,
        }
        for t in trades
    ]


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(BotSession).order_by(desc(BotSession.started_at)).all()
    return [
        {
            "id": s.id, "started_at": s.started_at.isoformat(),
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "symbol": s.symbol, "strategy": s.strategy_name,
            "starting_capital": s.starting_capital, "final_value": s.final_value,
            "is_live": s.is_live, "status": s.status,
        }
        for s in sessions
    ]


@router.get("/discover")
def discover(limit: int = Query(10, gt=0, le=100)):
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
def backtest_historical(strategy: str = "ema_rsi", symbol: str = "RELIANCE",
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
        return {"status": False, "reason": str(e)}

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
def backtest_batch(symbols: str = "SBIFUNDS,RELIANCE,TCS,INFY,HDFCBANK",
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
def backtest_significance(strategy: str = "ema_rsi", symbols: str = "SBIFUNDS,RELIANCE,TCS,INFY,HDFCBANK",
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
            if strategy == "volume_confirmed":
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
def discover_long_term(rank_by: Literal["3mo", "6mo", "1y", "2y"] = "1y",
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
def discover_universe_batch(offset: int = Query(0, ge=0),
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
def stock_chart(symbol: str, period: Literal["1mo", "3mo", "6mo", "1y", "2y", "5y"] = "1y"):
    """
    Full OHLC candles for one stock, for the long-term screener's
    click-to-view-detail chart.
    """
    try:
        candles = fetch_ohlc_for_chart(symbol, period=period)
    except ValueError as e:
        return {"status": False, "reason": str(e)}

    return {"symbol": symbol.upper(), "period": period, "candles": candles}
