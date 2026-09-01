"""
app/bot_runner.py
Runs the live/paper trading loop for a WATCHLIST of symbols in a background
thread. Each symbol gets its own strategy instance (they carry price-history
state, so sharing one across symbols would corrupt the signals).
"""
import threading
import time
import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models import BotSession, PriceTick
from app.broker.paper_broker import PaperBroker
from app.data_feed.feeds import SimulatedFeed
from app.strategies import STRATEGY_REGISTRY
from app.config import settings
from app.data_feed.feeds import SimulatedFeed, AngelLiveFeed
from app.services.price_feed import get_live_price
from app.models import BotSession, PriceTick, PortfolioSnapshot, Trade

logger = logging.getLogger("bot_runner")

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

NSE_HOLIDAYS_2026 = {
    "2026-01-26", "2026-03-06", "2026-03-21", "2026-04-14", "2026-05-01",
    "2026-08-15", "2026-10-02", "2026-10-21", "2026-11-04", "2026-12-25",
}


DECISION_WINDOW_START = dtime(15, 20)  # last ~10 minutes of the trading day


def is_decision_time(now_ist: datetime = None) -> bool:
    """
    The validated backtest (STRATEGY_EVALUATION.md, p=0.0008) computed RSI
    on 5 years of DAILY closes - RSI(14) there means 14 TRADING DAYS. But
    the live tick loop used to call strategy.decide() on every tick (as
    often as every 60 seconds), and MeanReversionStrategy.decide() appends
    every price it's given to its own rolling window - so RSI(14) live was
    actually being computed over the last 14 MINUTES, not 14 days. Same
    formula, completely different (and never statistically tested)
    timeframe - which is exactly why trades were round-tripping every few
    minutes instead of the ~5-trades-per-stock-per-year pace the backtest
    actually validated.

    Restricting actual decisions to a short window near market close means
    each symbol's strategy only ever sees one new price per trading day -
    genuinely matching the daily-close granularity that was validated,
    instead of a different, untested minute-scale strategy wearing the
    same name.
    """
    now_ist = now_ist or datetime.now(IST)
    if not is_market_open(now_ist):
        return False
    return DECISION_WINDOW_START <= now_ist.time() <= MARKET_CLOSE


def is_market_open(now_ist: datetime = None) -> bool:
    """
    True only during real NSE trading hours: 9:15-15:30 IST, Monday-Friday,
    excluding known holidays. The simulated feed has no concept of time on
    its own, so without this check it happily trades at 2am on a Saturday.
    """
    now_ist = now_ist or datetime.now(IST)
    if now_ist.weekday() >= 5:
        return False
    if now_ist.strftime("%Y-%m-%d") in NSE_HOLIDAYS_2026:
        return False
    current_time = now_ist.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE

logger = logging.getLogger("bot_runner")

# Default watchlist. Starting prices are just seeds for the simulated feed -
# irrelevant once real Angel One data replaces it.
DEFAULT_WATCHLIST = {
    "SBIFUNDS": 598.0,
    "RELIANCE": 2950.0,
    "TCS": 4150.0,
    "INFY": 1850.0,
    "HDFCBANK": 1650.0,
}

class YahooLiveFeed:
    """Same interface as SimulatedFeed/AngelLiveFeed (.get_price, .prices dict),
    backed by real (delayed) Yahoo Finance data instead of a random walk."""
    def __init__(self, symbols: list):
        self.prices = {}

    def get_price(self, symbol: str) -> float:
        data = get_live_price(symbol)
        price = data["last_price"]
        self.prices[symbol] = price
        return price


class AngelLiveFeed:
    """Same interface as YahooLiveFeed - backed by Angel One SmartAPI market
    data instead of yfinance. Data-only (never places orders), so it works
    on Render's free tier without a static IP. Selected via PRICE_FEED=angel."""
    def __init__(self, symbols: list):
        self.prices = {}

    def get_price(self, symbol: str) -> float:
        from app.services.angel_feed import get_angel_ltp
        data = get_angel_ltp(symbol)
        price = data["last_price"]
        self.prices[symbol] = price
        return price

    def refresh_bulk(self, symbols: list):
        """Fetch ALL symbols' LTP in one Angel API call (getMarketData -
        up to 50 symbols/call) instead of one getLtpData call per symbol.
        Angel rate-limits both endpoints at 1 request/second, but that's
        1 request per SYMBOL for getLtpData vs 1 request for the WHOLE
        BATCH here - the difference between a watchlist of 18-43 symbols
        needing 18-43 requests a tick versus needing 1. Populates
        self.prices directly; get_price() calls later this tick just read
        the cache this also writes to, no extra requests.

        Deliberately has its own try/except: a failure here (e.g. Angel
        session login failing) must not crash the whole tick loop/bot
        session - it should just mean no fresh bulk prices this tick,
        falling through to the per-symbol get_price() calls (each of
        which has its own error handling already)."""
        try:
            from app.services.angel_feed import get_angel_ltp_bulk
            results = get_angel_ltp_bulk(symbols)
            logger.info(f"refresh_bulk: got fresh prices for {len(results)}/{len(symbols)} symbols this tick.")
            for sym, data in results.items():
                self.prices[sym] = data["last_price"]
        except Exception as e:
            logger.warning(f"refresh_bulk failed entirely this tick (falling back to per-symbol fetch): {e}")

class BotRunner:
    def __init__(self, user_id: int = None):
        self.user_id = user_id
        self.thread = None
        self.running = False
        self.session_id = None
        self.broker = None
        self.feed = None
        self.strategies = {}
        self.symbols = []
        self.strategy_name = "ema_rsi"
        self.tick_seconds = 2
        self.last_signal = {}
        self.last_decision_date = {}  # symbol -> "YYYY-MM-DD" of the last day the strategy actually made a BUY/SELL/HOLD decision

    def _latest_prices(self) -> dict:
        """Build the symbol->price map used for portfolio valuation.
        Fallback order when the live feed has no price for a symbol (most
        commonly: market is closed, so the tick loop never called
        feed.get_price() this session):
        1. The most recent real PriceTick for that symbol - whatever price
           was last actually observed while the market was open. This is
           what keeps the closed-market portfolio value continuous with
           the equity curve chart's last real snapshot, instead of
           artificially jumping to a different number the moment the
           market closes.
        2. The position's own avg_price, only if there's truly no
           PriceTick history at all for that symbol (should be rare).
        3. 0, only if there's no position and no price history either -
           genuinely unknown, not "unknown means Rs.0 of value.\""""
        prices = {}
        live = self.feed.prices if self.feed else {}
        held_symbols = set(self.broker.positions.keys()) if self.broker else set()
        needs_fallback = [sym for sym in self.symbols if sym in held_symbols and not live.get(sym)]

        last_known = {}
        if needs_fallback:
            db = SessionLocal()
            try:
                for sym in needs_fallback:
                    tick = (
                        db.query(PriceTick)
                        .filter(PriceTick.symbol == sym)
                        .order_by(PriceTick.timestamp.desc())
                        .first()
                    )
                    if tick:
                        last_known[sym] = tick.price
            finally:
                db.close()

        for sym in self.symbols:
            if live.get(sym):
                prices[sym] = live[sym]
            elif sym in last_known:
                prices[sym] = last_known[sym]
            else:
                prices[sym] = self.broker.positions.get(sym, {}).get("avg_price", 0) if self.broker else 0
        return prices

    def start(self, symbols: list = None, strategy_name: str = "ema_rsi", tick_seconds: float = 2, starting_capital: float = None):
        if self.running:
            return {"status": False, "reason": "already_running"}

        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if strategy_cls is None:
            return {"status": False, "reason": f"unknown_strategy: {strategy_name}"}

        symbols = symbols or list(DEFAULT_WATCHLIST.keys())
        session_starting_capital = starting_capital if starting_capital is not None else settings.PAPER_STARTING_CAPITAL

        db = SessionLocal()

        # The TRUE "since inception" baseline is the very first session this
        # user ever ran, not whatever gets passed to this particular
        # start() call. broker.cash/positions already correctly resume
        # across restarts (_restore_state()) - but self.starting_capital
        # was always reset fresh here, so total_return_pct in status() was
        # comparing the real resumed portfolio value against a fake reset
        # baseline every time, producing a bogus "instant profit" on every
        # restart that had nothing to do with actual performance.
        first_session = (
            db.query(BotSession)
            .filter(BotSession.user_id == self.user_id)
            .order_by(BotSession.started_at.asc())
            .first()
        )
        inception_starting_capital = first_session.starting_capital if first_session else session_starting_capital

        bot_session = BotSession(
            started_at=datetime.utcnow(),
            symbol=",".join(symbols),
            strategy_name=strategy_name,
            starting_capital=session_starting_capital,
            is_live=(settings.MODE == "live"),
            status="running",
            user_id=self.user_id,
        )
        db.add(bot_session)
        db.commit()
        db.refresh(bot_session)
        self.session_id = bot_session.id
        db.close()

        self.symbols = symbols
        self.strategy_name = strategy_name
        self.strategies = {sym: strategy_cls() for sym in symbols}
        self.tick_seconds = tick_seconds
        self.last_signal = {sym: "HOLD" for sym in symbols}
        self.last_decision_date = {}
        self.starting_capital = inception_starting_capital
        self.running = True

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return {"status": True, "session_id": self.session_id, "symbols": symbols}

    def _run_loop(self):
        db = SessionLocal()
        self.broker = PaperBroker(db, self.starting_capital, self.strategy_name, user_id=self.user_id)
        self.broker.connect()

        self.feed = AngelLiveFeed(self.symbols) if settings.PRICE_FEED == "angel" else YahooLiveFeed(self.symbols)

        try:
            while self.running:
                if not is_market_open():
                    self.last_signal = {sym: "MARKET_CLOSED" for sym in self.symbols}
                    time.sleep(min(self.tick_seconds * 10, 30))
                    continue
                now_ist = datetime.now(IST)
                today_str = now_ist.strftime("%Y-%m-%d")
                if hasattr(self.feed, "refresh_bulk"):
                    self.feed.refresh_bulk(self.symbols)
                for symbol in self.symbols:
                    try:
                        price = self.feed.get_price(symbol)
                    except Exception as e:
                        logger.warning(f"Price fetch failed for {symbol} (user_id={self.user_id}): {e}")
                        continue  # skip this symbol this tick, don't kill the whole loop
                    db.add(PriceTick(timestamp=datetime.utcnow(), symbol=symbol, price=price))

                    if not is_decision_time(now_ist) or self.last_decision_date.get(symbol) == today_str:
                        continue  # not this symbol's one daily decision window yet, or already decided today

                    holding = self.broker.get_holding_qty(symbol)
                    signal = self.strategies[symbol].decide(price, holding)
                    self.last_signal[symbol] = signal
                    self.last_decision_date[symbol] = today_str
                    logger.info(
                        f"Decision for {symbol} (user_id={self.user_id}): {signal} "
                        f"(price={price}, holding={holding}, date={today_str})"
                    )
                    if signal == "BUY":
                        # Size like engine.py does: capital_pct_per_trade of
                        # current cash, not a fixed share count. This is the
                        # sizing scheme that was actually statistically
                        # validated (p=0.0008) - a flat DEFAULT_QTY here
                        # would mean the live bot trades a different, never-
                        # tested strategy from the one the backtest proved.
                        qty = max(1, int((self.broker.cash * settings.CAPITAL_PCT_PER_TRADE) // price))
                        self.broker.place_order(symbol, signal, qty, price)
                    elif signal == "SELL":
                        # Close the full held position, same as engine.py -
                        # a fixed DEFAULT_QTY SELL could leave a stray
                        # partial position sitting open instead of exiting.
                        self.broker.place_order(symbol, signal, holding, price)
                latest_prices = self._latest_prices()
                portfolio_value = self.broker.portfolio_value(latest_prices)
                try:
                    db.add(PortfolioSnapshot(
                        user_id=self.user_id,
                        session_id=self.session_id,
                        timestamp=datetime.utcnow(),
                        portfolio_value=portfolio_value,
                        cash=self.broker.cash,
                    ))
                    db.commit()
                except Exception as e:
                    # A dropped DB connection (Neon closing an idle session,
                    # a network blip) shouldn't take down the whole bot
                    # session over one missed snapshot write. Roll back to
                    # get the Session back to a usable state and try again
                    # next tick - trades themselves (place_order's own
                    # db.add/commit) get the same treatment implicitly since
                    # a poisoned Session would have failed there too; this
                    # keeps the loop itself alive either way.
                    logger.warning(f"Portfolio snapshot write failed (user_id={self.user_id}), continuing: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
                time.sleep(self.tick_seconds)
        except Exception as e:
            logger.exception(f"Bot loop crashed (user_id={self.user_id}): {e}")
            self.running = False
            try:
                db.rollback()
            except Exception:
                pass
            self._finalize(db, status="crashed")
            db.close()
            return

        self._finalize(db, status="stopped")
        db.close()
        return

    def _finalize(self, db, status):
        """Marks the session ended. Uses the passed-in db session if it's
        still usable, but falls back to a brand-new one if not - a session
        that just crashed the tick loop (e.g. a dropped DB connection) may
        be unrecoverable even after rollback(), and losing the "crashed"
        status write means the session sits shown as forever-running in the
        DB even though the bot process is actually dead."""
        try:
            bot_session = db.query(BotSession).filter(BotSession.id == self.session_id).first()
            if bot_session:
                bot_session.ended_at = datetime.utcnow()
                bot_session.status = status
                if self.broker:
                    latest_prices = self._latest_prices()
                    bot_session.final_value = self.broker.portfolio_value(latest_prices)
                db.commit()
            return
        except Exception as e:
            logger.warning(f"_finalize failed with the original db session, retrying with a fresh one: {e}")

        try:
            fresh_db = SessionLocal()
            try:
                bot_session = fresh_db.query(BotSession).filter(BotSession.id == self.session_id).first()
                if bot_session:
                    bot_session.ended_at = datetime.utcnow()
                    bot_session.status = status
                    if self.broker:
                        latest_prices = self._latest_prices()
                        bot_session.final_value = self.broker.portfolio_value(latest_prices)
                    fresh_db.commit()
            finally:
                fresh_db.close()
        except Exception as e:
            logger.error(f"_finalize failed even with a fresh db session (user_id={self.user_id}): {e}")

    def stop(self):
        if not self.running:
            return {"status": False, "reason": "not_running"}
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        return {"status": True}

    def status(self):
        if not self.running or not self.broker or (self.thread and not self.thread.is_alive()):
            return {"running": False, "market_open": is_market_open()}
        latest_prices = self._latest_prices()
        db = SessionLocal()
        bot_session = db.query(BotSession).filter(BotSession.id == self.session_id).first()
        started_at = bot_session.started_at.isoformat() if bot_session else None
        db.close()

        current_value = self.broker.portfolio_value(latest_prices)
        starting_capital = self.starting_capital
        total_return_pct = round((current_value - starting_capital) / starting_capital * 100, 2) if starting_capital else 0

        return {
            "running": True,
            "session_id": self.session_id,
            "symbols": self.symbols,
            "strategy": bot_session.strategy_name if bot_session else None,
            "started_at": started_at,
            "market_open": is_market_open(),
            "cash": self.broker.cash,
            "positions": self.broker.positions,
            "portfolio_value": current_value,
            "starting_capital": starting_capital,
            "total_return_pct": total_return_pct,
            "day_pnl": round(current_value - starting_capital, 2),
            "day_pnl_pct": total_return_pct,
        }

    def screener(self):
        """Ranks the watchlist by recent momentum. This is the honest version
        of 'best stock' - not a prediction, just which symbols currently have
        the strongest recent move AND a live signal from the strategy."""
        if not self.running or not self.feed:
            return {"running": False, "results": []}

        results = []
        for symbol in self.symbols:
            strat = self.strategies[symbol]
            prices = list(strat.prices) if hasattr(strat, "prices") else []
            if len(prices) >= 2:
                momentum_pct = round((prices[-1] - prices[0]) / prices[0] * 100, 3)
            else:
                momentum_pct = 0.0
            results.append({
                "symbol": symbol,
                "last_price": prices[-1] if prices else None,
                "momentum_pct": momentum_pct,
                "signal": self.last_signal.get(symbol, "HOLD"),
                "holding_qty": self.broker.get_holding_qty(symbol) if self.broker else 0,
            })

        results.sort(key=lambda r: abs(r["momentum_pct"]), reverse=True)
        return {"running": True, "results": results}


class UserBotManager:
    """One BotRunner instance per logged-in user - full portfolio isolation.
    Trade-off worth knowing: each active user's bot polls Yahoo Finance
    independently, so API call volume scales with concurrent active users.
    Fine for a handful of real users; would need a real shared-price-cache
    refactor before this scales to hundreds of simultaneous traders."""
    def __init__(self):
        self._runners = {}

    def get_runner(self, user_id: int) -> BotRunner:
        if user_id not in self._runners:
            self._runners[user_id] = BotRunner(user_id=user_id)
        return self._runners[user_id]

    def start(self, user_id: int, **kwargs):
        return self.get_runner(user_id).start(**kwargs)

    def stop(self, user_id: int):
        if user_id not in self._runners:
            return {"status": False, "reason": "not_running"}
        return self._runners[user_id].stop()

    def status(self, user_id: int):
        if user_id not in self._runners:
            return {"running": False, "market_open": is_market_open()}
        return self._runners[user_id].status()

    def screener(self, user_id: int):
        if user_id not in self._runners:
            return {"running": False, "results": []}
        return self._runners[user_id].screener()

    def reset(self, user_id: int, confirm: bool = False):
        """Wipes this user's trading history (Trade, BotSession,
        PortfolioSnapshot rows) so the next bot start begins completely
        fresh - no history for _restore_state() to resume from, no old
        starting_capital baseline to inherit. Irreversible, so requires
        explicit confirm=True, and requires the bot to be stopped first
        (resetting history out from under a live tick loop mid-write is
        asking for trouble)."""
        if not confirm:
            return {"status": False, "reason": "confirmation_required"}
        if user_id in self._runners and self._runners[user_id].running:
            return {"status": False, "reason": "stop_bot_first"}

        db = SessionLocal()
        try:
            trades_deleted = db.query(Trade).filter(Trade.user_id == user_id).delete()
            sessions_deleted = db.query(BotSession).filter(BotSession.user_id == user_id).delete()
            snapshots_deleted = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user_id).delete()
            db.commit()
        finally:
            db.close()

        # Drop the in-memory runner too (if one exists) - otherwise the
        # next start() would reuse a BotRunner object that still has the
        # old self.starting_capital/self.last_decision_date etc lingering
        # in memory, even though the DB history is gone.
        self._runners.pop(user_id, None)

        logger.info(
            f"Account reset for user_id={user_id}: {trades_deleted} trades, "
            f"{sessions_deleted} sessions, {snapshots_deleted} snapshots deleted."
        )
        return {
            "status": True,
            "trades_deleted": trades_deleted,
            "sessions_deleted": sessions_deleted,
            "snapshots_deleted": snapshots_deleted,
        }


user_bot_manager = UserBotManager()
