![Tests](https://github.com/Kartik-061/trading-bot/actions/workflows/tests.yml/badge.svg)

# Trading Bot — NSE Paper Trading, Backtesting & Research Platform

A full-stack trading research platform for Indian equities: a paper-trading
bot, a rigorous backtesting engine with real cost modeling and statistical
significance testing, and a research screener covering the entire ~2,000-stock
NSE universe.

**Live demo:** https://trading-bot-s2zl.onrender.com/dashboard/
*(free-tier hosting — first load after inactivity may take ~30-60s to wake up.
Public demo API key is shown in the dashboard banner.)*

**Full findings write-up:** [STRATEGY_EVALUATION.md](./STRATEGY_EVALUATION.md)
— the honest result of testing whether simple technical strategies actually
have edge on NSE stocks, backed by real statistical significance testing,
not eyeballed backtests.

---

## What this actually is

Most "AI trading bot" projects show a backtest that looks good and stop
there. This one goes further: every strategy here was tested with real
Indian trading costs (brokerage, STT, GST, stamp duty), proper
capital-percentage position sizing, and a statistical significance test
that pools every trade and asks "is this actually distinguishable from
random chance?" — not just "did the numbers look positive on one run."

The honest result: the intraday strategies tested here do **not** show
statistically significant edge once real costs are included (p=0.0016,
proven negative — see the evaluation report). That's a real finding, not
a failure to hide. The engineering discipline that produced that answer
is the actual point of this project.

## Features

- **Paper trading bot** — runs a live watchlist against a simulated or real
  price feed, executes signals automatically, tracks a full DB-backed trade
  history. Market-hours aware (won't trade at 2am on a Saturday).
- **Backtesting engine** — runs any strategy over real historical NSE data
  (via Yahoo Finance), with:
  - Real Indian intraday cost modeling (brokerage cap, STT, exchange
    charges, GST, stamp duty)
  - Capital-percentage position sizing (not a fixed share count)
  - Statistical significance testing (pooled trade z-test)
- **Three strategies**: EMA/RSI crossover, RSI mean-reversion (with
  stop-loss/take-profit exit variants), and volume-confirmed crossover
- **Research screener** covering the full official NSE stock list
  (~2,000 symbols), with multi-period trailing returns (3mo/6mo/1y/2y),
  relative strength vs Nifty 50, volatility, and P/E — paginated, sortable,
  filterable
- **Interactive dashboard** — candlestick charts, live watchlist, stock
  detail modal with its own chart, trade log
- **17-test automated suite**, run on every push via GitHub Actions CI
- **Dockerized**, deployed live on Render
- API key auth + rate limiting

## Structure

```
app/
  config.py            settings from .env
  database.py           SQLAlchemy engine/session
  models.py              Trade, BotSession, PriceTick tables
  auth.py                 API key authentication
  strategies/             swap strategies without touching the runner
    ema_rsi.py
    mean_reversion.py
    volume_confirmed.py
  broker/                 paper vs live, same interface
    paper_broker.py
    angel_broker.py
  data_feed/               simulated vs real price feeds
  backtest/
    engine.py               core backtest simulation loop
    costs.py                 real Indian intraday trading cost model
    portfolio_stats.py       statistical significance testing
    historical_data.py       Yahoo Finance data fetching
  screener/
    candidates.py             momentum/valuation research screener
    long_term.py               multi-period trailing return screener
    nse_universe.py            full NSE master list loader
  bot_runner.py            background thread running the live loop
  api/routes.py            REST endpoints
frontend/index.html        dashboard (candlestick charts, screener, modal)
tests/                      17 automated tests
main.py                     FastAPI app entrypoint
STRATEGY_EVALUATION.md      full findings write-up
```

## Setup

### Option A: Docker (recommended)

```bash
cp .env.example .env    # fill in values, see below
docker-compose up --build
```

### Option B: Local Python

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Either way, open `http://127.0.0.1:8000/dashboard/`.

### Required setup for the full stock screener

Download NSE's official equity list and save it as `data/EQUITY_L.csv`:
```
https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
```

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

17 tests covering cost math, position sizing, and strategy signal logic.
Runs automatically on every push via GitHub Actions.

## API

Full interactive docs at `/docs` once running. Key endpoints:

- `POST /api/bot/start` / `POST /api/bot/stop` — control the paper trading loop
- `GET /api/watchlist/screener` — live momentum screener on the active watchlist
- `POST /api/backtest/historical` — backtest a strategy on real historical data
- `POST /api/backtest/significance` — pooled statistical significance test
- `GET /api/discover/long-term` — multi-period trailing return screener
- `GET /api/discover/universe-batch` — paginated scan of the full NSE universe

## Going live (real money) — not currently recommended

`app/broker/angel_broker.py` implements the real Angel One Smart API for
when/if a strategy passes rigorous validation. As of this write-up, none
has — see [STRATEGY_EVALUATION.md](./STRATEGY_EVALUATION.md) for the full
statistical case. Don't flip `BOT_MODE=live` without running the
significance test framework against your specific strategy and getting a
real, statistically significant positive result first.

## Disclaimer

This project is for educational and portfolio purposes. Nothing here is
investment advice. Past backtested performance does not predict future
results. No strategy in this repository is currently validated for live
trading with real capital.
