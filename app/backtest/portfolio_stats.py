"""
app/backtest/portfolio_stats.py

Answers the question we've been dodging by eyeballing symbol-by-symbol
results: is this strategy's average trade actually different from zero,
or could "3 out of 8 stocks looked positive" just be noise?

Pools every individual trade's net P&L across all symbols tested, then
runs a one-sample z-test against zero.
"""
import math

from app.backtest.engine import run_backtest


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def test_significance(strategy_cls, strategy_kwargs: dict, symbol_data: dict,
                       starting_capital: float = 100000) -> dict:
    all_trade_pnls = []
    per_symbol = {}

    for symbol, prices in symbol_data.items():
        strategy = strategy_cls(**strategy_kwargs)
        result = run_backtest(strategy, prices, starting_capital=starting_capital)
        sell_trades = [t for t in result.trades if t["side"] == "SELL"]
        pnls = [t["pnl"] for t in sell_trades]
        all_trade_pnls.extend(pnls)
        per_symbol[symbol] = {
            "total_return_pct": result.total_return_pct,
            "num_trades": len(pnls),
        }

    n = len(all_trade_pnls)
    if n < 2:
        return {
            "error": "Not enough pooled trades to test significance meaningfully.",
            "total_pooled_trades": n,
            "per_symbol": per_symbol,
        }

    mean_pnl = sum(all_trade_pnls) / n
    variance = sum((x - mean_pnl) ** 2 for x in all_trade_pnls) / (n - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    if std_dev == 0:
        z_score = 0.0
    else:
        standard_error = std_dev / math.sqrt(n)
        z_score = mean_pnl / standard_error if standard_error > 0 else 0.0

    p_value = 2 * (1 - _normal_cdf(abs(z_score)))

    return {
        "num_symbols": len(symbol_data),
        "total_pooled_trades": n,
        "mean_pnl_per_trade_rs": round(mean_pnl, 2),
        "std_dev_pnl_rs": round(std_dev, 2),
        "z_score": round(z_score, 3),
        "p_value": round(p_value, 4),
        "statistically_significant_at_5pct": bool(p_value < 0.05),
        "per_symbol": per_symbol,
        "interpretation": (
            "p < 0.05 means the average trade profit is unlikely to be pure chance - "
            "real signal. p >= 0.05 (common for simple retail strategies) means we "
            "cannot rule out that any positive-looking symbols were just noise."
        ),
    }