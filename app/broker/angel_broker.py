"""
app/broker/angel_broker.py
Real Angel One Smart API wrapper. Only instantiated when BOT_MODE=live.
Also logs every fill to the DB, same as PaperBroker, so live and paper
trades show up in the same trade history table (filtered by is_live).
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.broker.base import BaseBroker
from app.config import settings
from app.models import Trade

logger = logging.getLogger("angel_broker")


class AngelBroker(BaseBroker):
    def __init__(self, db: Session, starting_capital: float, strategy_name: str = "ema_rsi",
                 user_id: int = None, max_concurrent_positions: int = 5):
        self.db = db
        self.cash = starting_capital
        self.starting_capital = starting_capital
        self.positions = {}
        self.strategy_name = strategy_name
        self.user_id = user_id
        self.max_concurrent_positions = max_concurrent_positions

    def connect(self):
        from SmartApi import SmartConnect
        import pyotp

        settings.validate_for_live()
        self.smart_api = SmartConnect(api_key=settings.ANGEL_API_KEY)
        totp = pyotp.TOTP(settings.ANGEL_TOTP_SECRET).now()
        session = self.smart_api.generateSession(
            settings.ANGEL_CLIENT_ID, settings.ANGEL_PASSWORD, totp
        )
        if not session.get("status"):
            raise RuntimeError(f"Angel One login failed: {session}")
        logger.info("Connected to Angel One (LIVE).")

    def get_ltp(self, exchange: str, symbol: str, token: str) -> float:
        data = self.smart_api.ltpData(exchange, symbol, token)
        return float(data["data"]["ltp"])

    def get_holding_qty(self, symbol: str) -> int:
        return self._holdings_cache.get(symbol, 0)

    def place_order(self, symbol: str, side: str, qty: int, price: float,
                     token: str = "", exchange: str = "NSE") -> dict:
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
        response = self.smart_api.placeOrder(order_params)
        status = bool(response.get("status", False)) if isinstance(response, dict) else False

        if status:
            self._holdings_cache[symbol] = self._holdings_cache.get(symbol, 0) + (
                qty if side == "BUY" else -qty
            )

        trade = Trade(
            timestamp=datetime.utcnow(),
            symbol=symbol, side=side, qty=qty, price=price,
            value=round(qty * price, 2), cash_after=0.0,
            is_live=True, strategy_name=self.strategy_name,
        )
        self.db.add(trade)
        self.db.commit()

        logger.info(f"LIVE ORDER: {side} {qty} {symbol} -> status={status}")
        return {"status": status, "raw_response": response}
