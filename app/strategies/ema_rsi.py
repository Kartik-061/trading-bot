"""
app/strategies/ema_rsi.py
v1 strategy: EMA(9)/EMA(21) crossover confirmed by RSI(14).
Same logic we validated in the single-file version, now as a swappable
component instead of hardcoded into the main loop.
"""
from collections import deque

from app.strategies.base import BaseStrategy


def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class EmaRsiStrategy(BaseStrategy):
    name = "ema_rsi"

    def __init__(self, ema_short=9, ema_long=21, rsi_period=14,
                 rsi_buy_threshold=50, rsi_sell_threshold=50, max_history=200):
        self.ema_short_p = ema_short
        self.ema_long_p = ema_long
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy_threshold
        self.rsi_sell = rsi_sell_threshold
        self.prices = deque(maxlen=max_history)
        self.prev_relation = None  # "above" / "below"

    def reset(self):
        self.prices.clear()
        self.prev_relation = None

    def decide(self, price: float, holding_qty: int, volume: float = None) -> str:
        self.prices.append(price)
        prices_list = list(self.prices)

        ema_short = calc_ema(prices_list, self.ema_short_p)
        ema_long = calc_ema(prices_list, self.ema_long_p)
        rsi = calc_rsi(prices_list, self.rsi_period)

        if ema_short is None or ema_long is None or rsi is None:
            return "HOLD"

        current_relation = "above" if ema_short > ema_long else "below"
        crossed_up = self.prev_relation == "below" and current_relation == "above"
        crossed_down = self.prev_relation == "above" and current_relation == "below"
        self.prev_relation = current_relation

        if crossed_up and rsi > self.rsi_buy and holding_qty == 0:
            return "BUY"
        if crossed_down and rsi < self.rsi_sell and holding_qty > 0:
            return "SELL"
        return "HOLD"
