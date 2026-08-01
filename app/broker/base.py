"""
app/broker/base.py
Same interface for paper and live brokers, so bot_runner.py never branches
on "if paper else live" - it just calls broker.place_order(...).
"""
from abc import ABC, abstractmethod


class BaseBroker(ABC):
    @abstractmethod
    def connect(self):
        ...

    @abstractmethod
    def place_order(self, symbol: str, side: str, qty: int, price: float) -> dict:
        """Returns {'status': bool, 'cash_after': float, ...}"""
        ...

    @abstractmethod
    def get_holding_qty(self, symbol: str) -> int:
        ...
