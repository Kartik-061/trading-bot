"""
app/backtest/engine.py
Runs any BaseStrategy over a list of historical closing prices and reports
real performance metrics.

Position sizing: buys as many shares as capital_pct_per_trade of current
cash allows, not a fixed 1 share. This matters a lot - 1 share of a Rs.7
stock is 0.007% of a Rs.100,000 account, so even a huge % move in the stock
is invisible against total capital. Sizing by % of capital makes returns
comparable across stocks of very different prices.
"""
from dataclasses import dataclass, field

from app.backtest.costs import buy_costs, sell_costs


@dataclass
class BacktestResult:
    starting_capital: float
    final_value: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    total_return_pct: float
    total_costs: float = 0.0
    trades: list = field(default_factory=list)


def run_backtest(strategy, prices: list, starting_capital: float = 100000,
                  capital_pct_per_trade: float = 0.1, include_costs: bool = True) -> BacktestResult:
    """
    prices: list of historical closing prices, oldest first.
    capital_pct_per_trade: fraction of current cash to deploy per trade
        (0.1 = 10%). Share count is derived from this, not fixed.
    """
    cash = starting_capital
    holding_qty = 0
    entry_price = None
    trades = []
    peak = starting_capital
    max_drawdown = 0.0
    total_costs = 0.0

    for entry in prices:
        if isinstance(entry, dict):
            price = entry["close"]
            volume = entry.get("volume")
        else:
            price = entry
            volume = None

        signal = strategy.decide(price, holding_qty, volume=volume)

        if signal == "BUY" and holding_qty == 0:
            budget = cash * capital_pct_per_trade
            qty = max(1, int(budget // price)) if price > 0 else 0

            if qty > 0:
                cost = qty * price
                fees = buy_costs(price, qty) if include_costs else 0.0
                if cost + fees <= cash:
                    cash -= (cost + fees)
                    total_costs += fees
                    holding_qty = qty
                    entry_price = price
                    trades.append({"side": "BUY", "price": price, "qty": qty, "fees": fees})

        elif signal == "SELL" and holding_qty > 0:
            qty = holding_qty
            proceeds = qty * price
            fees = sell_costs(price, qty) if include_costs else 0.0
            cash += (proceeds - fees)
            total_costs += fees
            entry_fees = trades[-1].get("fees", 0.0) if trades and trades[-1]["side"] == "BUY" else 0.0
            pnl = (proceeds - fees) - (qty * entry_price) - entry_fees
            trades.append({"side": "SELL", "price": price, "qty": qty, "pnl": pnl, "fees": fees})
            holding_qty = 0
            entry_price = None

        current_value = cash + (holding_qty * price)
        peak = max(peak, current_value)
        drawdown = (peak - current_value) / peak * 100 if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

    if holding_qty > 0:
        last_entry = prices[-1]
        final_price = last_entry["close"] if isinstance(last_entry, dict) else last_entry
        qty = holding_qty
        proceeds = qty * final_price
        fees = sell_costs(final_price, qty) if include_costs else 0.0
        cash += (proceeds - fees)
        total_costs += fees
        entry_fees = trades[-1].get("fees", 0.0) if trades and trades[-1]["side"] == "BUY" else 0.0
        pnl = (proceeds - fees) - (qty * entry_price) - entry_fees
        trades.append({"side": "SELL", "price": final_price, "qty": qty, "pnl": pnl, "fees": fees,
                        "note": "forced_close_at_backtest_end"})

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
        total_costs=round(total_costs, 2),
        trades=trades,
    )