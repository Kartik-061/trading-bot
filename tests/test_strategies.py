"""
tests/test_strategies.py
Verifies each strategy's decide() logic in isolation, using crafted price
sequences that force known conditions rather than relying on random data.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.strategies.ema_rsi import EmaRsiStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.volume_confirmed import VolumeConfirmedStrategy


def test_ema_rsi_holds_during_warmup():
    strat = EmaRsiStrategy(ema_short=9, ema_long=21)
    signal = strat.decide(price=100, holding_qty=0)
    assert signal == "HOLD"


def test_ema_rsi_never_buys_while_already_holding():
    strat = EmaRsiStrategy()
    for price in [100 + i * 0.5 for i in range(30)]:
        strat.decide(price, holding_qty=0)
    signal = strat.decide(price=115, holding_qty=1)
    assert signal != "BUY"


def test_ema_rsi_crossover_produces_buy():
    strat = EmaRsiStrategy(ema_short=9, ema_long=21, rsi_period=14)
    prices = [100] * 25 + [100 + i * 2 for i in range(1, 15)]
    signals = [strat.decide(p, holding_qty=0) for p in prices]
    assert "BUY" in signals


def test_mean_reversion_buys_when_oversold():
    strat = MeanReversionStrategy(oversold=30, overbought=70)
    prices = [100] * 15 + [100 - i * 3 for i in range(1, 15)]
    signals = [strat.decide(p, holding_qty=0) for p in prices]
    assert "BUY" in signals


def test_mean_reversion_stop_loss_triggers():
    strat = MeanReversionStrategy(stop_loss_pct=2.0)
    strat.entry_price = 100
    signal = strat.decide(price=97, holding_qty=1)
    assert signal == "SELL"


def test_volume_confirmed_blocks_buy_on_low_volume():
    strat = VolumeConfirmedStrategy(volume_multiplier=2.0, volume_window=10)
    prices = [100] * 15 + [100 + i * 2 for i in range(1, 15)]
    low_volumes = [1000] * 30

    signals = []
    for p, v in zip(prices, low_volumes):
        signals.append(strat.decide(p, holding_qty=0, volume=v))

    assert "BUY" not in signals


def test_volume_confirmed_allows_buy_on_volume_spike():
    strat = VolumeConfirmedStrategy(volume_multiplier=1.5, volume_window=10)
    prices = [100] * 25 + [100 + i * 2 for i in range(1, 15)]
    volumes = [1000] * 25 + [5000] * 14

    signals = []
    for p, v in zip(prices, volumes):
        signals.append(strat.decide(p, holding_qty=0, volume=v))

    assert "BUY" in signals