"""
app/backtest/costs.py

Real Indian intraday equity trading costs - approximate but realistic,
covering what actually eats into returns: brokerage, STT, exchange
transaction charges, GST on those charges, and stamp duty. SEBI turnover
fee is negligible at retail trade sizes and skipped.

These are typical discount-broker (Angel One-style) rates. Check your
actual broker rate card before assuming these are exact - rates change,
and this is meant to be realistic, not authoritative.
"""

BROKERAGE_PCT = 0.0003        # 0.03% per executed order
BROKERAGE_CAP = 20.0          # brokerage never exceeds Rs.20/order (typical discount broker)
STT_SELL_PCT = 0.00025        # 0.025% - intraday STT applies to the sell side only
EXCHANGE_TXN_PCT = 0.0000325  # ~0.00325% NSE transaction charge, both sides
GST_PCT = 0.18                # GST on (brokerage + exchange transaction charges)
STAMP_DUTY_BUY_PCT = 0.00003  # 0.003% on buy side only


def _brokerage(value: float) -> float:
    return min(value * BROKERAGE_PCT, BROKERAGE_CAP)


def buy_costs(price: float, qty: int) -> float:
    value = price * qty
    b = _brokerage(value)
    exch = value * EXCHANGE_TXN_PCT
    stamp = value * STAMP_DUTY_BUY_PCT
    gst = (b + exch) * GST_PCT
    return round(b + exch + stamp + gst, 4)


def sell_costs(price: float, qty: int) -> float:
    value = price * qty
    b = _brokerage(value)
    stt = value * STT_SELL_PCT
    exch = value * EXCHANGE_TXN_PCT
    gst = (b + exch) * GST_PCT
    return round(b + stt + exch + gst, 4)