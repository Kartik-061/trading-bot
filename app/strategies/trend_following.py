"""
app/strategies/trend_following.py

Trend-following strategy - mechanically different from mean_reversion on
purpose. Mean-reversion bets price snaps back after an extreme. This bets
the opposite: once a real trend is confirmed, ride it until it reverses.
That's the actual point of having both - in a market regime where one
loses, the other often doesn't, which is what "diversification" means in
practice, not just "different RSI numbers."

Honest caveat: this engine only feeds close prices into decide(), not
high/low. True ATR and ADX both require the high-low range. What's built
here are close-price-only proxies:
- "ATR" here = average absolute close-to-close move over atr_period.
  Real ATR would be wider (it captures intrabar range too), so this
  will run tighter stops than a textbook ATR implementation.
- "trend strength" here = net directional movement over adx_period,
  as a % of total movement - same spirit as ADX (are moves piling up
  in one direction, or cancelling out), not the literal ADX formula.
Both are legitimate, useful signals - just not identical to the
Pine-Script versions of the same names. Flagging this so nobody later
assumes this matches a TradingView backtest number.
"""
from collections import deque

from app.strategies.base import BaseStrategy


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"

    def __init__(self, ema_fast=20, ema_slow=50, atr_period=14, adx_period=14,
                 adx_threshold=20.0, atr_stop_mult=2.5, take_profit_rmult=2.0,
                 max_history=200):
        self.ema_fast_period = ema_fast
        self.ema_slow_period = ema_slow
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_stop_mult = atr_stop_mult
        self.take_profit_rmult = take_profit_rmult

        self.prices = deque(maxlen=max_history)
        self.abs_diffs = deque(maxlen=atr_period)   # for ATR proxy
        self.signed_diffs = deque(maxlen=adx_period)  # for trend-strength proxy

        self.ema_fast_val = None
        self.ema_slow_val = None
        self.prev_ema_diff_sign = None  # +1 / -1 / None, tracks last crossover state

        self.entry_price = None
        self.atr_at_entry = None

    def reset(self):
        self.prices.clear()
        self.abs_diffs.clear()
        self.signed_diffs.clear()
        self.ema_fast_val = None
        self.ema_slow_val = None
        self.prev_ema_diff_sign = None
        self.entry_price = None
        self.atr_at_entry = None

    def _update_emas(self, price: float):
        k_fast = 2 / (self.ema_fast_period + 1)
        k_slow = 2 / (self.ema_slow_period + 1)
        self.ema_fast_val = price if self.ema_fast_val is None else (
            price * k_fast + self.ema_fast_val * (1 - k_fast)
        )
        self.ema_slow_val = price if self.ema_slow_val is None else (
            price * k_slow + self.ema_slow_val * (1 - k_slow)
        )

    def _atr_proxy(self):
        if len(self.abs_diffs) < self.atr_period:
            return None
        return sum(self.abs_diffs) / len(self.abs_diffs)

    def _trend_strength_proxy(self):
        if len(self.signed_diffs) < self.adx_period:
            return None
        up = sum(d for d in self.signed_diffs if d > 0)
        down = sum(-d for d in self.signed_diffs if d < 0)
        total = up + down
        if total == 0:
            return 0.0
        return abs(up - down) / total * 100

    def decide(self, price: float, holding_qty: int, volume: float = None) -> str:
        prev_price = self.prices[-1] if self.prices else None
        self.prices.append(price)

        if prev_price is not None:
            diff = price - prev_price
            self.abs_diffs.append(abs(diff))
            self.signed_diffs.append(diff)

        self._update_emas(price)

        min_history = max(self.ema_slow_period, self.atr_period, self.adx_period)
        if len(self.prices) < min_history:
            return "HOLD"

        atr = self._atr_proxy()
        trend_strength = self._trend_strength_proxy()
        if atr is None or trend_strength is None or atr == 0:
            return "HOLD"

        ema_diff = self.ema_fast_val - self.ema_slow_val
        current_sign = 1 if ema_diff > 0 else -1

        # Exit checks first, same reasoning as mean_reversion: risk control
        # doesn't wait for a "nicer" signal once we're in a losing position.
        if holding_qty > 0 and self.entry_price is not None and self.atr_at_entry:
            stop_price = self.entry_price - (self.atr_stop_mult * self.atr_at_entry)
            target_price = self.entry_price + (
                self.atr_stop_mult * self.atr_at_entry * self.take_profit_rmult
            )
            if price <= stop_price or price >= target_price:
                self.entry_price = None
                self.atr_at_entry = None
                self.prev_ema_diff_sign = current_sign
                return "SELL"

            # Trend reversal exit: fast EMA crosses back below slow EMA.
            if self.prev_ema_diff_sign == 1 and current_sign == -1:
                self.entry_price = None
                self.atr_at_entry = None
                self.prev_ema_diff_sign = current_sign
                return "SELL"

        # Entry: bullish crossover + confirmed trend strength, only when flat.
        if (holding_qty == 0 and self.prev_ema_diff_sign == -1
                and current_sign == 1 and trend_strength >= self.adx_threshold):
            self.entry_price = price
            self.atr_at_entry = atr
            self.prev_ema_diff_sign = current_sign
            return "BUY"

        self.prev_ema_diff_sign = current_sign
        return "HOLD"