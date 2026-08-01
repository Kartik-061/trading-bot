"""
app/strategies/mean_reversion.py

v2: added real exit management. The batch backtest showed this strategy wins
often (57-67% win rate across stocks) but still nets flat/negative returns -
meaning losses are bigger than wins. Two fixes for that specific problem:

1. Stop-loss: caps how much one bad trade can cost, so a few wins can't get
   wiped out by one trade that keeps going against us.
2. Faster take-profit: exits at RSI 50 (neutral) instead of waiting for a
   full swing to overbought (70) - since wins are already frequent, the fix
   is capturing them sooner, not waiting for a bigger move that often
   doesn't come.
"""
from collections import deque

from app.strategies.base import BaseStrategy
from app.strategies.ema_rsi import calc_rsi


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"

    def __init__(self, rsi_period=14, oversold=30, overbought=70,
                 stop_loss_pct=1.5, take_profit_rsi=50, max_history=200):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_rsi = take_profit_rsi
        self.prices = deque(maxlen=max_history)
        self.entry_price = None

    def reset(self):
        self.prices.clear()
        self.entry_price = None

    def decide(self, price: float, holding_qty: int, volume: float = None) -> str:
        self.prices.append(price)

        # Stop-loss check comes first and doesn't need RSI - if we're
        # holding and down too much, exit regardless of what the indicator says.
        if holding_qty > 0 and self.entry_price is not None:
            loss_pct = (self.entry_price - price) / self.entry_price * 100
            if loss_pct >= self.stop_loss_pct:
                self.entry_price = None
                return "SELL"

        rsi = calc_rsi(list(self.prices), self.rsi_period)
        if rsi is None:
            return "HOLD"

        if holding_qty == 0 and rsi < self.oversold:
            self.entry_price = price
            return "BUY"

        if holding_qty > 0 and (rsi >= self.take_profit_rsi or rsi > self.overbought):
            self.entry_price = None
            return "SELL"

        return "HOLD"