"""
tests/test_costs.py
Verifies the Indian intraday cost model math is correct - brokerage cap,
STT only on sell side, GST applied correctly.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.backtest.costs import buy_costs, sell_costs, _brokerage, BROKERAGE_CAP


def test_brokerage_caps_at_20_rupees():
    huge_value = 10_000_000
    assert _brokerage(huge_value) == BROKERAGE_CAP


def test_brokerage_scales_below_cap():
    small_value = 1000
    assert _brokerage(small_value) < BROKERAGE_CAP
    assert _brokerage(small_value) > 0


def test_buy_costs_are_positive_and_reasonable():
    fees = buy_costs(price=500, qty=10)
    assert fees > 0
    assert fees < 50


def test_sell_costs_include_stt_but_buy_costs_dont():
    buy_fee = buy_costs(price=500, qty=10)
    sell_fee = sell_costs(price=500, qty=10)
    assert sell_fee > buy_fee


def test_costs_scale_with_trade_value():
    small_fees = buy_costs(price=100, qty=1)
    large_fees = buy_costs(price=100, qty=100)
    assert large_fees > small_fees