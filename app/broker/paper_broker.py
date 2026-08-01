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

logger = logging.getLogger("paper_broker")


class PaperBroker(BaseBroker):
    def __init__(self, db: Session, starting_capital: float, strategy_name: str = "ema_rsi"):
        self.db = db
        self.cash = starting_capital
        self.starting_capital = starting_capital
        self.positions = {}  # symbol -> {"qty": int, "avg_price": float}
        self.strategy_name = strategy_name

    def connect(self):
        logger.info(f"Paper broker ready. Starting capital: Rs.{self.cash:,.2f}")

    def get_holding_qty(self, symbol: str) -> int:
        return self.positions.get(symbol, {"qty": 0})["qty"]

    def place_order(self, symbol: str, side: str, qty: int, price: float) -> dict:
        cost = qty * price

        if side == "BUY":
            if cost > self.cash:
                return {"status": False, "reason": "insufficient_funds"}
            self.cash -= cost
            pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
            new_qty = pos["qty"] + qty
            pos["avg_price"] = ((pos["avg_price"] * pos["qty"]) + cost) / new_qty
            pos["qty"] = new_qty
            self.positions[symbol] = pos

        elif side == "SELL":
            pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
            if pos["qty"] < qty:
                return {"status": False, "reason": "insufficient_shares"}
            self.cash += cost
            pos["qty"] -= qty
            if pos["qty"] == 0:
                pos["avg_price"] = 0.0
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
        )
        self.db.add(trade)
        self.db.commit()

        logger.info(f"PAPER {side} {qty} {symbol} @ Rs.{price:.2f} | Cash: Rs.{self.cash:,.2f}")
        return {"status": True, "cash_after": self.cash}

    def portfolio_value(self, current_prices: dict) -> float:
        holdings = sum(
            pos["qty"] * current_prices.get(sym, 0)
            for sym, pos in self.positions.items() if pos["qty"] > 0
        )
        return round(self.cash + holdings, 2)
