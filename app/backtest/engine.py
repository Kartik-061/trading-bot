"""
app/backtest/engine.py
Runs any BaseStrategy over a list of historical closing prices and reports
real performance metrics. This is the honesty check before any real money -
"the architecture is solid" and "the strategy makes money" are answered
separately, and this file answers the second question.
"""
from dataclasses import dataclass, field


@dataclass
class BacktestResult:
    starting_capital: float
    final_value: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    total_return_pct: float
    trades: list = field(default_factory=list)


def run_backtest(strategy, prices: list, starting_capital: float = 100000, qty: int = 1) -> BacktestResult:
    """
    prices: list of historical closing prices, oldest first.
    Simulates the strategy tick by tick over that history.
    """
    cash = starting_capital
    holding_qty = 0
    entry_price = None
    trades = []
    equity_curve = [starting_capital]
    peak = starting_capital
    max_drawdown = 0.0

    for price in prices:
        signal = strategy.decide(price, holding_qty)

        if signal == "BUY" and holding_qty == 0:
            cost = qty * price
            if cost <= cash:
                cash -= cost
                holding_qty = qty
                entry_price = price
                trades.append({"side": "BUY", "price": price})

        elif signal == "SELL" and holding_qty > 0:
            proceeds = qty * price
            cash += proceeds
            pnl = proceeds - (qty * entry_price)
            trades.append({"side": "SELL", "price": price, "pnl": pnl})
            holding_qty = 0
            entry_price = None

        current_value = cash + (holding_qty * price)
        equity_curve.append(current_value)
        peak = max(peak, current_value)
        drawdown = (peak - current_value) / peak * 100 if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

    # close any open position at the last price so we can score the run
    if holding_qty > 0:
        final_price = prices[-1]
        proceeds = qty * final_price
        cash += proceeds
        pnl = proceeds - (qty * entry_price)
        trades.append({"side": "SELL", "price": final_price, "pnl": pnl, "note": "forced_close_at_backtest_end"})

    sell_trades = [t for t in trades if t["side"] == "SELL"]
    wins = [t for t in sell_trades if t.get("pnl", 0) > 0]
    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0.0

    return BacktestResult(
        starting_capital=starting_capital,
        final_value=round(cash, 2),
        total_trades=len(sell_trades),
        win_rate=round(win_rate, 2),
        max_drawdown_pct=round(max_drawdown, 2),
        total_return_pct=round((cash - starting_capital) / starting_capital * 100, 2),
        trades=trades,
    )
