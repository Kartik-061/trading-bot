"""
app/bot_runner.py
Runs the live/paper trading loop for a WATCHLIST of symbols in a background
thread. Each symbol gets its own strategy instance (they carry price-history
state, so sharing one across symbols would corrupt the signals).
"""
import threading
import time
import logging
from datetime import datetime

from app.database import SessionLocal
from app.models import BotSession, PriceTick
from app.broker.paper_broker import PaperBroker
from app.data_feed.feeds import SimulatedFeed
from app.strategies import STRATEGY_REGISTRY
from app.config import settings

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


class BotRunner:
    """Singleton-ish controller. One bot run at a time, tracking a watchlist."""

    def __init__(self):
        self.thread = None
        self.running = False
        self.session_id = None
        self.broker = None
        self.feed = None
        self.strategies = {}   # symbol -> strategy instance
        self.symbols = []
        self.tick_seconds = 2
        self.last_signal = {}  # symbol -> "BUY"/"SELL"/"HOLD"

    def start(self, symbols: list = None, strategy_name: str = "ema_rsi", tick_seconds: float = 2):
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
            starting_capital=settings.PAPER_STARTING_CAPITAL,
            is_live=(settings.MODE == "live"),
            status="running",
        )
        db.add(bot_session)
        db.commit()
        db.refresh(bot_session)
        self.session_id = bot_session.id
        db.close()

        self.symbols = symbols
        self.strategies = {sym: strategy_cls() for sym in symbols}
        self.tick_seconds = tick_seconds
        self.last_signal = {sym: "HOLD" for sym in symbols}
        self.running = True

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return {"status": True, "session_id": self.session_id, "symbols": symbols}

    def _run_loop(self):
        db = SessionLocal()
        self.broker = PaperBroker(db, settings.PAPER_STARTING_CAPITAL, "ema_rsi")
        self.broker.connect()

        seed_prices = {sym: DEFAULT_WATCHLIST.get(sym, 500.0) for sym in self.symbols}
        self.feed = SimulatedFeed(seed_prices)

        try:
            while self.running:
                for symbol in self.symbols:
                    price = self.feed.get_price(symbol)

                    db.add(PriceTick(timestamp=datetime.utcnow(), symbol=symbol, price=price))

                    holding = self.broker.get_holding_qty(symbol)
                    signal = self.strategies[symbol].decide(price, holding)
                    self.last_signal[symbol] = signal

                    if signal in ("BUY", "SELL"):
                        self.broker.place_order(symbol, signal, settings.DEFAULT_QTY, price)

                db.commit()
                time.sleep(self.tick_seconds)
        except Exception as e:
            logger.exception(f"Bot loop crashed: {e}")
            self._finalize(db, status="crashed")
            db.close()
            return

        self._finalize(db, status="stopped")
        db.close()

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
        if not self.running or not self.broker:
            return {"running": False}
        latest_prices = {sym: self.feed.prices.get(sym, 0) for sym in self.symbols}
        return {
            "running": True,
            "session_id": self.session_id,
            "symbols": self.symbols,
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


bot_runner = BotRunner()
