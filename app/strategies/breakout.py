"""
app/strategies/breakout.py

Momentum/breakout strategy - a genuinely different bet from everything else
tested so far. Mean-reversion bets price snaps back after moving too far.
Trend-following waits for a slow, confirmed trend. This bets on a specific,
well-documented pattern: price breaking above its own recent (~52-week)
high on above-average volume - real buying conviction pushing into new
territory, not just noise.

Honest framing, worth remembering before trusting any backtest here: this
is the same pattern people point to after the fact on stocks that moved
50%+ in a year. For every one of those, there are many similar-looking
breakouts that went nowhere - survivorship bias is real. This strategy
gets the exact same bar as everything else: pooled significance testing
across many stocks, not "it caught one big winner in the backtest window."

Exit logic: fixed stop-loss from entry (protects against a failed breakout
immediately reversing), OR price closing back below a short EMA (trend
exhaustion exit - if the move loses its own momentum, get out rather than
waiting for a full round-trip back to the stop).
"""
from collections import deque

from app.strategies.base import BaseStrategy
from app.strategies.ema_rsi import calc_ema


class BreakoutStrategy(BaseStrategy):
    name = "breakout"

    def __init__(self, lookback=260, breakout_confirm_pct=0.0,
                 volume_multiplier=1.5, volume_window=20,
                 stop_loss_pct=8.0, exit_ema_period=20, max_history=280):
        """
        lookback: bars used to compute the prior high (260 ~= 52 weeks of
            daily candles). The breakout is measured against this high,
            excluding the current bar.
        breakout_confirm_pct: how far above the prior high price must close
            to count as a real breakout, not just touching the line. 0.0
            means any new high counts; e.g. 1.0 requires closing >1% above
            the prior high for extra confirmation.
        volume_multiplier/volume_window: same volume-confirmation logic as
            VolumeConfirmedStrategy - breakout volume must exceed its
            recent average by this multiple, or the signal is ignored.
        stop_loss_pct: hard exit if price falls this far below entry.
        exit_ema_period: secondary exit - closing below this EMA signals
            the breakout has lost momentum, get out even if the stop
            hasn't been hit yet.
        """
        self.lookback = lookback
        self.breakout_confirm_pct = breakout_confirm_pct
        self.volume_multiplier = volume_multiplier
        self.volume_window = volume_window
        self.stop_loss_pct = stop_loss_pct
        self.exit_ema_period = exit_ema_period

        self.prices = deque(maxlen=max_history)
        self.volumes = deque(maxlen=max_history)
        self.entry_price = None

    def reset(self):
        self.prices.clear()
        self.volumes.clear()
        self.entry_price = None

    def decide(self, price: float, holding_qty: int, volume: float = None) -> str:
        prices_list = list(self.prices)  # prior history, before appending today
        if volume is not None:
            self.volumes.append(volume)
        self.prices.append(price)

        # Exit checks first, same convention as every other strategy today:
        # risk control doesn't wait for a nicer signal once we're in.
        if holding_qty > 0 and self.entry_price is not None:
            loss_pct = (self.entry_price - price) / self.entry_price * 100
            if loss_pct >= self.stop_loss_pct:
                self.entry_price = None
                return "SELL"

            exit_ema = calc_ema(list(self.prices), self.exit_ema_period)
            if exit_ema is not None and price < exit_ema:
                self.entry_price = None
                return "SELL"

        if holding_qty > 0:
            return "HOLD"

        # Entry: need enough history to know what "prior high" even means.
        if len(prices_list) < self.lookback:
            return "HOLD"

        prior_high = max(prices_list[-self.lookback:])
        breakout_level = prior_high * (1 + self.breakout_confirm_pct / 100)

        if price <= breakout_level:
            return "HOLD"

        volume_confirmed = True
        if volume is not None and len(self.volumes) >= self.volume_window:
            avg_volume = sum(list(self.volumes)[-self.volume_window:]) / self.volume_window
            volume_confirmed = avg_volume > 0 and volume >= avg_volume * self.volume_multiplier

        if volume_confirmed:
            self.entry_price = price
            return "BUY"

        return "HOLD"