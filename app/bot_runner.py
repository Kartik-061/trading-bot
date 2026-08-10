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
from app.models import BotSession, PriceTick, PortfolioSnapshot

logger = logging.getLogger("bot_runner")

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

NSE_HOLIDAYS_2026 = {
    "2026-01-26", "2026-03-06", "2026-03-21", "2026-04-14", "2026-05-01",
    "2026-08-15", "2026-10-02", "2026-10-21", "2026-11-04", "2026-12-25",
}


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

    def start(self, symbols: list = None, strategy_name: str = "ema_rsi", tick_seconds: float = 2, starting_capital: float = None):
        if self.running:
            return {"status": False, "reason": "already_running"}

        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if strategy_cls is None:
            return {"status": False, "reason": f"unknown_strategy: {strategy_name}"}

        symbols = symbols or list(DEFAULT_WATCHLIST.keys())

        db = SessionLocal()
        bot_session = BotSession(
            started_at=datetime.utcnow(),
            symbol=",".join(symbols),
            strategy_name=strategy_name,
            starting_capital=starting_capital if starting_capital is not None else settings.PAPER_STARTING_CAPITAL,
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
        self.starting_capital = starting_capital if starting_capital is not None else settings.PAPER_STARTING_CAPITAL
        self.running = True

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return {"status": True, "session_id": self.session_id, "symbols": symbols}

    def _run_loop(self):
        db = SessionLocal()
        self.broker = PaperBroker(db, self.starting_capital, self.strategy_name, user_id=self.user_id)
        self.broker.connect()

        self.feed = YahooLiveFeed(self.symbols)

        try:
            while self.running:
                if not is_market_open():
                    self.last_signal = {sym: "MARKET_CLOSED" for sym in self.symbols}
                    time.sleep(min(self.tick_seconds * 10, 30))
                    continue
                for symbol in self.symbols:
                    try:
                        price = self.feed.get_price(symbol)
                    except Exception as e:
                        logger.warning(f"Price fetch failed for {symbol} (user_id={self.user_id}): {e}")
                        continue  # skip this symbol this tick, don't kill the whole loop
                    db.add(PriceTick(timestamp=datetime.utcnow(), symbol=symbol, price=price))
                    holding = self.broker.get_holding_qty(symbol)
                    signal = self.strategies[symbol].decide(price, holding)
                    self.last_signal[symbol] = signal
                    if signal in ("BUY", "SELL"):
                        self.broker.place_order(symbol, signal, settings.DEFAULT_QTY, price)
                latest_prices = {sym: self.feed.prices.get(sym, 0) for sym in self.symbols}
                portfolio_value = self.broker.portfolio_value(latest_prices)
                db.add(PortfolioSnapshot(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    timestamp=datetime.utcnow(),
                    portfolio_value=portfolio_value,
                    cash=self.broker.cash,
                ))
                db.commit()
                time.sleep(self.tick_seconds)
        except Exception as e:
            logger.exception(f"Bot loop crashed (user_id={self.user_id}): {e}")
            self.running = False          # <-- YEH LINE ADD KI
            self._finalize(db, status="crashed")
            db.close()
            return

        self._finalize(db, status="stopped")
        db.close()
        return

    def _finalize(self, db, status):
        bot_session = db.query(BotSession).filter(BotSession.id == self.session_id).first()
        if bot_session:
            bot_session.ended_at = datetime.utcnow()
            bot_session.status = status
            if self.broker:
                latest_prices = {sym: self.feed.prices.get(sym, 0) for sym in self.symbols}
                bot_session.final_value = self.broker.portfolio_value(latest_prices)
            db.commit()

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
        latest_prices = {sym: self.feed.prices.get(sym, 0) for sym in self.symbols}
        db = SessionLocal()
        bot_session = db.query(BotSession).filter(BotSession.id == self.session_id).first()
        started_at = bot_session.started_at.isoformat() if bot_session else None
        db.close()
        return {
            "running": True,
            "session_id": self.session_id,
            "symbols": self.symbols,
            "strategy": bot_session.strategy_name if bot_session else None,
            "started_at": started_at,
            "market_open": is_market_open(),
            "cash": self.broker.cash,
            "positions": self.broker.positions,
            "portfolio_value": self.broker.portfolio_value(latest_prices),
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


user_bot_manager = UserBotManager()
