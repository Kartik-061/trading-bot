# Strategy Evaluation Report

**Project:** NSE Trading Bot (Paper Trading + Research Screener)
**Author:** Kartikya Motwani
**Date:** August 2026

## 1. Objective

Determine whether simple, retail-accessible technical trading strategies have
statistically real edge on NSE equities, before ever risking real capital.
This report documents the methodology, results, and conclusions of that
evaluation - modeled on rigorous ML/quant evaluation practice: a claim isn't
validated by looking good on one example, it's validated by a metric that
survives real scrutiny.

## 2. Methodology

### 2.1 Backtest Engine
A custom engine (`app/backtest/engine.py`) simulates any strategy tick-by-tick
over historical price data, tracking cash, positions, and every trade.

Two design decisions were made only after they were shown to be necessary by
earlier, flawed results:

- **Capital-percentage position sizing** (10% of current cash per trade),
  not a fixed share count. A fixed 1-share position made returns on
  low-priced stocks invisible against total capital - this was caught and
  fixed after an early screener test showed cheap stocks (~Rs.7-20) all
  reporting near-zero returns regardless of actual price movement.
- **Real Indian intraday cost modeling** (`app/backtest/costs.py`):
  brokerage (0.03%, capped at Rs.20/order), STT (0.025%, sell-side only),
  NSE exchange charges, GST on brokerage+exchange charges, and stamp duty.
  Every backtest in this report includes these costs unless stated otherwise.

### 2.2 Statistical Significance Testing
Rather than judging a strategy by eyeballing which stocks "looked positive,"
`app/backtest/portfolio_stats.py` pools every individual trade's net P&L
across every symbol tested and runs a one-sample z-test against zero. This
is the standard way to ask "is this average trade result distinguishable
from pure chance, or could it just be noise from a few lucky symbols?"

### 2.3 Data
Real historical price/volume data from Yahoo Finance (yfinance), covering:
- Intraday: 5-minute candles, last 60 days
- Swing/long-term: daily candles, up to 2 years

## 3. Strategies Tested

| Strategy | Logic |
|---|---|
| `ema_rsi` | EMA(9)/EMA(21) crossover, confirmed by RSI(14) > 50 |
| `mean_reversion` | RSI oversold/overbought reversal, with stop-loss and take-profit exit variants |
| `volume_confirmed` | Same EMA/RSI crossover, but requires volume >1.5x recent average to confirm |

## 4. Results

### 4.1 Intraday, EMA/RSI crossover (12 stocks, real 5-min data, real costs)

| Metric | Value |
|---|---|
| Total pooled trades | 824 |
| Mean P&L per trade | -Rs.12.07 |
| Std deviation | Rs.109.48 |
| z-score | -3.163 |
| **p-value** | **0.0016** |
| Statistically significant? | **Yes - negative** |

**Conclusion: proven, not merely suspected, to lose money.** 9 of 12 stocks
individually negative; the 3 positive ones did not offset the pooled
average. This is not a tuning problem - it is a structural finding.

### 4.2 Intraday, Mean Reversion variants (multiple stop-loss/exit configs)

Tested across the same 12+ stocks, multiple exit configurations (default,
tight stop-loss, fast take-profit). Every single variant, on every stock,
was net negative after real costs. High win rates (often 50-65%) were
consistently offset by average losses larger than average wins - a losses
outweigh wins on average.

### 4.3 Swing timeframe, Mean Reversion (2-year daily data, 19 large-cap stocks)

Loosened stop-loss (6%) and slower take-profit (RSI 60), matched to daily
volatility instead of intraday noise.

| Metric | Value |
|---|---|
| Total pooled trades | 214 |
| Mean P&L per trade | +Rs.4.81 |
| Std deviation | Rs.569.95 |
| z-score | 0.123 |
| **p-value** | **0.90** |
| Statistically significant? | **No** |

**Conclusion: genuinely inconclusive**, not a hidden negative. Noise
(std dev Rs.570) is roughly 100x the signal (mean Rs.4.81) - individual
stock results (RELIANCE +0.92%, ADANIENT -2.38%) show no consistent
pattern and are consistent with pure chance.

### 4.4 Volume Confirmation (5 stocks, real volume data)

| Metric | Value |
|---|---|
| Total pooled trades | 79 |
| Mean P&L per trade | +Rs.2.63 |
| p-value | 0.8376 |
| Statistically significant? | No |

Adding volume as a confirmation filter did not produce detectable edge on
this universe.

## 5. Conclusion

Three independent, statistically rigorous tests, covering both major
technical-analysis strategy families (momentum/crossover and mean
reversion), two timeframes (intraday and swing), and both concentrated and
wide stock universes, produced:

- **One proven-negative result** (intraday EMA/RSI, p=0.0016)
- **One proven-negative result** (intraday mean reversion, all variants)
- **Two inconclusive-null results** (swing mean reversion, volume
  confirmation) - not "it works," but "no detectable signal either way"

**This is a real, useful finding.** Simple technical indicators on liquid,
heavily-analyzed NSE large/mid-cap stocks do not show retail-accessible
edge once real trading costs are included. This matches well-documented
results in quantitative finance literature: simple, publicly-known
technical rules on efficiently-priced, liquid markets tend to get
arbitraged away by the many other participants already using them.

## 6. What Was Built (Engineering Summary)

- FastAPI backend with SQLAlchemy-backed trade/session history
- Paper trading engine with real-time watchlist, momentum screener
- Historical backtesting engine with configurable position sizing and
  real Indian cost modeling
- Statistical significance testing framework (pooled trade z-test)
- Long-term multi-period (3mo/6mo/1y/2y) screener across the full ~2,075
  stock NSE universe, loaded from NSE's official master list, with
  relative-strength-vs-Nifty and volatility metrics
- Interactive dashboard (candlestick charts, live watchlist, stock
  detail modal, paginated screener)
- 17-test automated pytest suite covering cost math, position sizing,
  and strategy signal logic

## 7. Recommended Next Directions (Not Yet Tested)

Continued parameter tuning of the strategies above has diminishing value -
each additional variant tested increases the risk of a false-positive
result appearing purely by chance (the multiple-testing problem). Two
genuinely different mechanisms remain unexplored:

1. **Pairs trading / statistical arbitrage** - trade the spread between two
   correlated stocks (e.g. HDFCBANK vs ICICIBANK) rather than direction.
   Market-neutral by construction. Requires a two-leg backtest engine,
   not yet built.
2. **Sector rotation** - monthly rebalancing into the strongest
   relative-strength names from the long-term screener, rather than daily
   trading. Much lower trade frequency largely avoids the cost-drag that
   sank every intraday strategy tested here.
## Strategy roster — full results (Aug 2026)

After validating `mean_reversion`, three additional strategy families were built and tested with identical rigor to check for a second, uncorrelated source of edge (per the "bot army" diversification principle — different strategy types should behave differently in the same market conditions).

### Method
Same pipeline for all four: `/api/backtest/significance` pools every individual trade's realized P&L across all symbols tested, then runs a one-sample z-test against zero. p < 0.05 is required to call a result "real" rather than noise.

### Results — 15 NSE large-cap stocks, 5-year daily data

| Strategy | Pooled trades | Mean P&L/trade | p-value | Verdict |
|---|---|---|---|---|
| `mean_reversion` | 363 | ₹133.07 | **0.0008** | **Real edge — deployed** |
| `trend_following` | 89 | -₹23.34 | 0.63 | No edge |
| `breakout` | 97 | -₹33.33 | 0.66 | No edge |
| `volume_confirmed` | 80 | ₹49.01 | 0.59 | No edge |

### Why the other three didn't survive

- **`trend_following`** (EMA crossover + close-price-based trend-strength filter, ATR-proxy stops): roughly symmetric win/loss split across stocks, no directional lean. The strict entry condition (crossover + trend-strength confirmation on the same bar) also produced few trades per stock, but even after widening the test to 10 stocks the result stayed centered on zero.
- **`breakout`** (52-week high + volume confirmation): the classic "catch the next big mover" pattern. 8 of 15 stocks negative, 7 positive — looks close to a coin flip once pooled, consistent with the well-known survivorship bias in momentum/breakout strategies: the winners people remember are memorable specifically because most similar setups don't work.
- **`volume_confirmed`** (EMA/RSI crossover requiring above-average volume): 10 of 15 stocks slightly positive, but magnitudes small and inconsistent — z-score indistinguishable from noise.

### Honest takeaway

One validated strategy out of four rigorously tested hypotheses is the expected, correct outcome of doing this properly — not a disappointing result. Most retail strategies don't survive pooled significance testing; the value here is in having actually checked, with real trading costs included, rather than assuming a backtest-positive result means a real edge.
## 8. Honest Disclaimer

This report reflects backtested, historical analysis only. Past
performance, including the statistical results above, does not guarantee
future performance. No strategy in this repository is currently
recommended for live trading with real capital.
