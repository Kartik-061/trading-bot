"""
tests/test_engine.py
Verifies the backtest engine itself: position sizing scales with capital
(not a fixed 1 share), costs actually reduce cash, forced-close at the end
works, and win-rate calculation is correct.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.backtest.engine import run_backtest


class AlwaysBuyThenSellStrategy:
    name = "test_strategy"

    def __init__(self):
        self.tick = 0

    def decide(self, price, holding_qty, volume=None):
        self.tick += 1
        if self.tick == 5 and holding_qty == 0:
            return "BUY"
        if self.tick == 10 and holding_qty > 0:
            return "SELL"
        return "HOLD"


def test_position_sizing_scales_with_capital_not_fixed_at_one_share():
    prices = [7.0] * 20
    strategy = AlwaysBuyThenSellStrategy()
    result = run_backtest(strategy, prices, starting_capital=100000, capital_pct_per_trade=0.1)

    buy_trades = [t for t in result.trades if t["side"] == "BUY"]
    assert len(buy_trades) == 1
    assert buy_trades[0]["qty"] > 1000


def test_costs_actually_reduce_final_value():
    prices = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100]

    with_costs = run_backtest(AlwaysBuyThenSellStrategy(), prices, starting_capital=100000, include_costs=True)
    without_costs = run_backtest(AlwaysBuyThenSellStrategy(), prices, starting_capital=100000, include_costs=False)

    assert with_costs.total_costs > 0
    assert without_costs.total_costs == 0
    assert with_costs.final_value < without_costs.final_value


def test_forced_close_at_end_of_backtest():
    class NeverSellsStrategy:
        name = "never_sells"
        def __init__(self):
            self.bought = False
        def decide(self, price, holding_qty, volume=None):
            if not self.bought:
                self.bought = True
                return "BUY"
            return "HOLD"

    prices = [100, 101, 102, 103, 104]
    result = run_backtest(NeverSellsStrategy(), prices, starting_capital=100000)

    sell_trades = [t for t in result.trades if t["side"] == "SELL"]
    assert len(sell_trades) == 1
    assert sell_trades[0].get("note") == "forced_close_at_backtest_end"


def test_win_rate_calculation():
    prices = [100] * 4 + [90] * 4 + [110] * 4
    strategy = AlwaysBuyThenSellStrategy()
    result = run_backtest(strategy, prices, starting_capital=100000)

    assert result.total_trades == 1
    assert result.win_rate == 100.0


def test_no_trades_returns_zero_not_crash():
    class NeverTradesStrategy:
        name = "never_trades"
        def decide(self, price, holding_qty, volume=None):
            return "HOLD"

    prices = [100, 101, 102]
    result = run_backtest(NeverTradesStrategy(), prices, starting_capital=100000)
    assert result.total_trades == 0
    assert result.win_rate == 0.0
    assert result.final_value == 100000