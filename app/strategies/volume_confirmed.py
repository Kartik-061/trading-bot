"""
app/strategies/volume_confirmed.py

Same EMA/RSI crossover signal as before, but now requires volume
confirmation before trusting a BUY: the crossover must happen on volume
meaningfully above its recent average (real conviction/participation),
not just a quiet drift that happens to cross two lines.

This is a genuinely different ingredient from anything tested so far -
every previous strategy was price-only. Exits don't require volume
confirmation - getting out fast on a bad signal matters more than being
picky about how you exit.
"""
from collections import deque

from app.strategies.base import BaseStrategy
from app.strategies.ema_rsi import calc_ema, calc_rsi


class VolumeConfirmedStrategy(BaseStrategy):
    name = "volume_confirmed"

    def __init__(self, ema_short=9, ema_long=21, rsi_period=14,
                 rsi_buy_threshold=50, rsi_sell_threshold=50,
                 volume_multiplier=1.5, volume_window=20, max_history=200):
        self.ema_short_p = ema_short
        self.ema_long_p = ema_long
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy_threshold
        self.rsi_sell = rsi_sell_threshold
        self.volume_multiplier = volume_multiplier
        self.volume_window = volume_window
        self.prices = deque(maxlen=max_history)
        self.volumes = deque(maxlen=max_history)
        self.prev_relation = None

    def reset(self):
        self.prices.clear()
        self.volumes.clear()
        self.prev_relation = None

    def decide(self, price: float, holding_qty: int, volume: float = None) -> str:
        self.prices.append(price)
        if volume is not None:
            self.volumes.append(volume)

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

        volume_confirmed = True
        if volume is not None and len(self.volumes) >= self.volume_window:
            avg_volume = sum(list(self.volumes)[-self.volume_window:]) / self.volume_window
            volume_confirmed = avg_volume > 0 and volume >= avg_volume * self.volume_multiplier

        if crossed_up and rsi > self.rsi_buy and holding_qty == 0 and volume_confirmed:
            return "BUY"
        if crossed_down and rsi < self.rsi_sell and holding_qty > 0:
            return "SELL"
        return "HOLD"