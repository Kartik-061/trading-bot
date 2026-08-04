# Trading Bot — BookIQ-style backend

FastAPI + SQLAlchemy backend for an intraday trading bot. Same shape as
BookIQ: modular app, DB-backed models, REST API, swappable pieces.

![Tests](https://github.com/Kartik-061/trading-bot/actions/workflows/tests.yml/badge.svg)

## Structure

```
app/
  config.py            settings from .env
  database.py           SQLAlchemy engine/session
  models.py              Trade, BotSession tables
  strategies/            swap strategies without touching the runner
    ema_rsi.py
  broker/                paper vs live, same interface
    paper_broker.py
    angel_broker.py
  data_feed/              simulated vs real price feeds
  backtest/               run a strategy over historical prices, get real metrics
  bot_runner.py           background thread that runs the live loop
  api/routes.py           REST endpoints
main.py                   FastAPI app entrypoint
```

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` — full interactive API, same idea as
DRF's browsable API on BookIQ.

## Dashboard

Open `http://127.0.0.1:8000/dashboard/` for the full UI — candlestick chart
(TradingView's Lightweight Charts), a live watchlist screener, and the trade
log. Click a symbol in the sidebar to chart it. Start/stop the bot right
from the page.

## Endpoints

- `POST /api/bot/start?symbols=SBIFUNDS,RELIANCE,TCS&strategy=ema_rsi&tick_seconds=2` — starts paper trading a watchlist in the background. Omit `symbols` for the default 5-stock watchlist.
- `GET /api/bot/status` — cash, positions, portfolio value, running state
- `POST /api/bot/stop`
- `GET /api/watchlist/screener` — ranks the watchlist by recent momentum + shows each symbol's live signal. This is the honest "best stock" finder: not a prediction, just which symbols are moving and what the strategy currently says about them.
- `GET /api/prices/{symbol}/candles?interval_seconds=5&limit=100` — OHLC candles aggregated from raw price ticks, powers the chart
- `GET /api/trades` — full trade history from the DB
- `GET /api/sessions` — every bot run, for comparing strategies over time
- `POST /api/backtest?strategy=ema_rsi&num_ticks=2000` — run a strategy over historical-style data, get win rate / drawdown / return

## What's real vs what's a placeholder right now

**Real and tested:** the full pipeline — strategy decides, broker fills,
trade writes to SQLite, backtest reports honest metrics. I ran this
end-to-end before handing it to you.

**Placeholder, and this is the actual next milestone:** `/api/backtest`
currently runs on simulated random-walk prices, not real market history.
A strategy that looks fine on random data means nothing — the real test
is running it against actual NSE historical candles (Angel One's
historical data API gives you this). That's the next thing to build,
and it's the honest answer to "will this make money" — not something
the architecture can promise on its own.

## Going live

Same as before: fill in Angel One credentials in `.env`, set `BOT_MODE=live`,
add real instrument tokens to `angel_broker.py` calls. Don't do this until
a strategy has backtested well on real historical data — not simulated data.

## Roadmap (good portfolio + good bot, in order)

1. Pull real historical candles from Angel One, backtest against those (this is the big one)
2. Stop-loss / position sizing (risk max X% of capital per trade)
3. A second strategy to compare against EMA/RSI (mean reversion is a natural next test)
4. Simple dashboard (Streamlit or a small React frontend) showing live P&L
5. Multi-symbol watchlist instead of one hardcoded symbol
