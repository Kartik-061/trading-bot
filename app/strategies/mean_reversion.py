"""
app/strategies/mean_reversion.py

Opposite bet from EMA/RSI crossover: instead of "price is moving, ride the
trend," this says "price moved too far too fast, bet it snaps back."
Buys when RSI shows oversold (price dropped hard), sells when RSI shows
overbought (price ran up hard) or holder exits on reversion.

Worth testing against crossover specifically because they fail in opposite
market conditions - crossover tends to do better in trending markets,
mean reversion tends to do better in choppy/range-bound ones. Testing both
tells you more about what kind of market your watchlist actually is.
"""
from collections import deque

from app.strategies.base import BaseStrategy
from app.strategies.ema_rsi import calc_rsi


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"

    def __init__(self, rsi_period=14, oversold=30, overbought=70, max_history=200):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.prices = deque(maxlen=max_history)

    def reset(self):
        self.prices.clear()

    def decide(self, price: float, holding_qty: int) -> str:
        self.prices.append(price)
        rsi = calc_rsi(list(self.prices), self.rsi_period)

        if rsi is None:
            return "HOLD"

        if rsi < self.oversold and holding_qty == 0:
            return "BUY"
        if rsi > self.overbought and holding_qty > 0:
            return "SELL"
        return "HOLD"