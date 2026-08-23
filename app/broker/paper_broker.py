"""
app/broker/paper_broker.py
Simulated account. Every fill gets written to the `trades` table via SQLAlchemy -
this is the piece that turns "console print statements" into "queryable trade history",
same upgrade BookIQ got going from local files to Postgres.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.broker.base import BaseBroker
from app.models import Trade
from app.backtest.costs import buy_costs, sell_costs

logger = logging.getLogger("paper_broker")


class PaperBroker(BaseBroker):
    def __init__(self, db: Session, starting_capital: float, strategy_name: str = "ema_rsi",
                 user_id: int = None, max_concurrent_positions: int = 5):
        self.db = db
        self.starting_capital = starting_capital
        self.positions = {}  # symbol -> {"qty": int, "avg_price": float}
        self.strategy_name = strategy_name
        self.user_id = user_id
        self.max_concurrent_positions = max_concurrent_positions
        self.cash = starting_capital
        self._restore_state()

    def _restore_state(self):
        """Every stop/start cycle used to create a brand-new PaperBroker with
        fresh starting_capital and empty positions - so stopping and
        restarting the bot silently wiped out all prior gains/losses and
        open positions, even though the account is meant to be one ongoing
        paper-trading track record. Resume from trade history instead: if
        this user has traded before, pick up cash from the last trade's
        cash_after and rebuild positions by replaying every trade in order.
        A genuinely brand-new user (no trades yet) still starts clean."""
        if self.user_id is None:
            return
        past_trades = (
            self.db.query(Trade)
            .filter(Trade.user_id == self.user_id)
            .order_by(Trade.timestamp.asc())
            .all()
        )
        if not past_trades:
            return

        for t in past_trades:
            pos = self.positions.get(t.symbol, {"qty": 0, "avg_price": 0.0})
            if t.side == "BUY":
                new_qty = pos["qty"] + t.qty
                pos["avg_price"] = ((pos["avg_price"] * pos["qty"]) + (t.qty * t.price)) / new_qty
                pos["qty"] = new_qty
                self.positions[t.symbol] = pos
            elif t.side == "SELL":
                pos["qty"] -= t.qty
                if pos["qty"] <= 0:
                    self.positions.pop(t.symbol, None)
                else:
                    self.positions[t.symbol] = pos

        self.cash = past_trades[-1].cash_after
        logger.info(
            f"Resumed paper account for user_id={self.user_id} from {len(past_trades)} "
            f"past trades: cash=Rs.{self.cash:,.2f}, "
            f"open positions={[s for s, p in self.positions.items() if p['qty'] > 0]}"
        )

    def connect(self):
        logger.info(f"Paper broker ready (user_id={self.user_id}). Starting capital: Rs.{self.cash:,.2f}")

    def get_holding_qty(self, symbol: str) -> int:
        return self.positions.get(symbol, {"qty": 0})["qty"]

    def place_order(self, symbol: str, side: str, qty: int, price: float) -> dict:
        cost = qty * price

        if side == "BUY":
            open_positions = sum(1 for pos in self.positions.values() if pos["qty"] > 0)
            already_holding = self.positions.get(symbol, {"qty": 0})["qty"] > 0
            if not already_holding and open_positions >= self.max_concurrent_positions:
                return {"status": False, "reason": "max_concurrent_positions_reached"}

            # Real trading costs, same as engine.py - without this the live
            # bot's cash/portfolio numbers assume zero-cost trades, which
            # doesn't match the validated backtest and quietly overstates
            # returns (costs only ever reduce P&L, never help it).
            fees = buy_costs(price, qty)
            if cost + fees > self.cash:
                return {"status": False, "reason": "insufficient_funds"}

            self.cash -= (cost + fees)
            pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
            new_qty = pos["qty"] + qty
            pos["avg_price"] = ((pos["avg_price"] * pos["qty"]) + cost) / new_qty
            pos["qty"] = new_qty
            self.positions[symbol] = pos

        elif side == "SELL":
            pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
            if pos["qty"] < qty:
                return {"status": False, "reason": "insufficient_shares"}
            fees = sell_costs(price, qty)
            self.cash += (cost - fees)
            pos["qty"] -= qty
            if pos["qty"] == 0:
                # Fully closed - drop the entry rather than leaving a
                # qty=0 stub. self.positions is what /me/bot/status and the
                # frontend's Active Positions count read directly; a
                # lingering zero-qty entry gets counted as "active" forever.
                self.positions.pop(symbol, None)
            else:
                self.positions[symbol] = pos
        else:
            return {"status": False, "reason": "invalid_side"}

        trade = Trade(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            value=round(cost, 2),
            cash_after=round(self.cash, 2),
            is_live=False,
            strategy_name=self.strategy_name,
            user_id=self.user_id,
        )
        self.db.add(trade)
        self.db.commit()

        logger.info(f"PAPER {side} {qty} {symbol} @ Rs.{price:.2f} | Cash: Rs.{self.cash:,.2f} (user_id={self.user_id})")
        return {"status": True, "cash_after": self.cash}

    def portfolio_value(self, current_prices: dict) -> float:
        holdings = sum(
            pos["qty"] * current_prices.get(sym, 0)
            for sym, pos in self.positions.items() if pos["qty"] > 0
        )
        return round(self.cash + holdings, 2)