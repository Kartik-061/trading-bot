"""
app/strategies/base.py
Every strategy implements this interface. bot_runner.py and the backtester
both talk to strategies only through `decide()` - so adding a new strategy
never means touching the runner or the backtester.
"""
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    name = "base"

    @abstractmethod
    def decide(self, price: float, holding_qty: int) -> str:
        """Return 'BUY', 'SELL', or 'HOLD'. Called once per new candle/tick."""
        raise NotImplementedError

    def reset(self):
        """Override if the strategy holds state that needs clearing between runs."""
        pass
