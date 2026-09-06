# NSE Quant Desk — Algorithmic Trading Bot

A full-stack algorithmic trading system for NSE (Indian stock market) equities, built end-to-end: real price data, honest cost modeling, statistically validated strategy selection, and a live paper-trading engine with per-user accounts.

**Live app:** https://strat-guardian-ui.lovable.app
**API:** https://trading-bot-s2zl.onrender.com (docs at `/docs`)

> Paper trading only. No real capital is connected. Research and educational project — not investment advice.

## The headline result

Of four strategies backtested with equal statistical rigor across 15 NSE large-cap stocks over 5 years, **one showed a real, statistically significant edge**:

| Strategy | p-value | Verdict |
|---|---|---|
| **Mean reversion** | **0.0008** | **Statistically significant — deployed** |
| Trend following | 0.63 | No edge detected |
| Breakout (52-week high + volume) | 0.66 | No edge detected |
| Volume-confirmed EMA/RSI | 0.59 | No edge detected |

The significance test pools every individual trade's P&L across all symbols and runs a one-sample z-test against zero — the rigorous version of "does this strategy actually work," instead of eyeballing which backtests happened to look positive. Full methodology and results in [`STRATEGY_EVALUATION.md`](./STRATEGY_EVALUATION.md).

**Watchlist expansion:** the deployed watchlist was later grown from 15 to a curated **43 NSE large-cap stocks**. Re-run at this larger scale, mean-reversion held up at **p=0.0344** — still statistically significant, though weaker than the original 15-stock result. Reported here honestly rather than reverting to the stronger-looking smaller sample.

## What makes this "real," not a demo

- **Real price data** — near-real-time NSE prices via Angel One's SmartAPI (data-only integration, no orders ever placed through it), with yfinance kept for fundamentals (P/E, market cap, sector) since Angel's API has no fundamentals endpoint
- **Real trading costs** — brokerage, STT, exchange transaction charges, GST, and stamp duty modeled per Indian discount-broker rates, subtracted from every simulated trade
- **Real position sizing** — 10% of capital per trade, capped at 5 concurrent positions (not a fixed 1-share toy) — matches exactly what the backtest that produced the p-values above actually used
- **Real decision cadence** — the strategy makes its one BUY/SELL/HOLD call per symbol per day in a short window near market close, matching the daily-close granularity it was validated on, instead of re-deciding on every incoming tick
- **Real statistical rigor** — every strategy is pooled-tested for significance before being trusted, not judged on a single backtest run
- **Real infrastructure** — self-healing (auto-restarts on deploy), rate-limited, deployed on Render + Neon Postgres, kept alive via scheduled health checks, portfolio state (cash/positions) persists across restarts instead of resetting

## Architecture

Alpha Terminal (React, deployed via Lovable)
        |
        |  REST API (JWT + API-key auth)
        v
FastAPI backend (Render, Docker)
        |
        +--> 
        Angel One SmartAPI (live prices, data-only) + yfinance (fundamentals, historical backtests)
        |
        +--> 
        Neon Postgres (users, trades, sessions)
        |
        +--> 
        Per-user BotRunner
             (isolated portfolio, strategy instance,
              paper broker - one per logged-in user)

**Backend:** FastAPI, SQLAlchemy, JWT auth (passlib + python-jose)
**Database:** PostgreSQL (Neon), migrated from SQLite for deploy-persistent storage
**Frontend:** React, TradingView lightweight-charts, deployed via Lovable
**Data:** Angel One SmartAPI (live prices), yfinance (historical OHLCV for backtests + fundamentals), NSE official equity master list

## Features

- **Live paper trading** — per-user isolated bot sessions, real-time price ticks, real position/cash tracking, resumes cleanly across restarts instead of resetting
- **Research page** — search any of ~2,000 NSE stocks: live quote, historical candlestick chart, basic fundamentals (P/E, market cap, 52-week range)
- **Backtest Lab** — run any strategy against any symbol/period, with full statistical significance testing
- **Trade history & strategy stats** — per-user trade log, cross-strategy performance comparison
- **User accounts** — email/password signup, JWT-authenticated sessions, fully isolated per-user portfolios
- **Account reset** — wipe your own trade/session history for a clean-slate restart, with a two-step confirmation to avoid accidental resets

## Running locally

```bash
git clone <repo>
cd tradebot
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL (sqlite:///./tradebot.db works for local dev), JWT_SECRET
uvicorn main:app --reload
```

API docs: `http://127.0.0.1:8000/docs`

## Strategy detail

The deployed strategy (`mean_reversion`) trades RSI oversold/overbought signals with a fixed stop-loss and RSI-based take-profit exit, computed on **daily closes** — the same granularity the backtest was validated on. Live, it makes its one decision per symbol in a short window near market close each trading day, rather than re-evaluating on every price tick, so the live signal genuinely matches the timeframe that was statistically tested instead of quietly becoming a different, untested strategy at a finer timescale.

Params were selected from a 2-year backtest, then validated out-of-sample on a completely different set of stocks (LT, MARUTI, ASIANPAINT, ULTRACEMCO, TITAN) and over a longer 5-year window — both confirmations held. The watchlist was later expanded from the original 15 stocks to 43, and re-validated at p=0.0344 (see above). Full breakdown, including the three rejected strategies and why they didn't survive testing, is in [`STRATEGY_EVALUATION.md`](./STRATEGY_EVALUATION.md).

This is a **daily mean-reversion strategy, not a day-trading system** — expect roughly ~5 trades per stock per year (≈200 trades/year pooled across the full watchlist), not daily activity.

## Author

Kartikya Motwani — [GitHub](https://github.com/Kartik-061)
