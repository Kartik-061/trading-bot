# NSE Quant Desk — Project Handoff Summary

Full-stack algorithmic trading system for NSE (Indian stock market) equities, built by Kartikya Motwani (Kartik-061). This document summarizes everything built, tested, fixed, and decided across an extended build session, for handoff to another assistant/collaborator.

**Live links:**
- Frontend: https://strat-guardian-ui.lovable.app
- Backend API: https://trading-bot-s2zl.onrender.com (docs at `/docs`)
- Backend repo: github.com/Kartik-061/trading-bot
- Frontend repo: github.com/Kartik-061/alpha-terminal (merged into backend repo's `frontend/` subfolder via git subtree)

---

## 1. Project origin and goal

Started as a portfolio piece (Python/FastAPI algorithmic trading bot) to demonstrate full-stack + quant skills for internship/freelance applications. Explicit goal throughout: **rigor over hype** — every claim about strategy performance had to survive real statistical testing, not just look good on one backtest.

---

## 2. Core engineering work (chronological)

### 2.1 Real price feed
- Replaced original `SimulatedFeed` (random-walk generator) with `YahooLiveFeed`, using `yfinance`'s `fast_info` for near-real-time (15-20 min delayed) NSE prices.
- New service: `app/services/price_feed.py` — `get_live_price()`, `get_live_prices_bulk()`, with 60-second caching to avoid hammering Yahoo.
- Wired into `bot_runner.py` so both paper and live modes use real data.

### 2.2 Real Indian trading cost model
- New module `app/backtest/costs.py`: brokerage (0.03%, capped ₹20/order), STT (0.025%, sell-side only), exchange transaction charges, GST (18% on brokerage+exchange), stamp duty (buy-side only) — modeled on typical discount-broker (Angel One-style) rates.
- Wired into `app/backtest/engine.py`'s `run_backtest()` — every simulated trade now has real costs subtracted, not just gross P&L.

### 2.3 Real position sizing
- Original engine traded a flat 1 share per signal regardless of capital — meant returns were basically symbolic.
- Fixed: `run_backtest()` now sizes each BUY as 15% of *current* cash (configurable `capital_pct_per_trade`), so position size scales with the account.
- `PaperBroker` (live/paper trading) got a matching `max_concurrent_positions` cap (default 5) to prevent unlimited simultaneous exposure.

### 2.4 Strategy roster — built and rigorously tested
Four strategies, each tested via a custom significance-testing pipeline (`app/backtest/portfolio_stats.py` — pools every individual trade's P&L across all tested symbols, runs a one-sample z-test against zero, reports p-value).

| Strategy | File | Mechanism | Result (15 NSE large-caps, 5yr) |
|---|---|---|---|
| `mean_reversion` | `mean_reversion.py` | RSI oversold/overbought entry, stop-loss + RSI take-profit exit | **p = 0.0008 — statistically significant, deployed** |
| `ema_rsi` | `ema_rsi.py` (pre-existing) | EMA crossover + RSI filter | Original baseline, superseded |
| `trend_following` | `trend_following.py` (new) | EMA crossover + close-price-based trend-strength proxy + ATR-proxy stops (no real intrabar data available, documented as approximation) | p = 0.63 — no edge |
| `breakout` | `breakout.py` (new) | 52-week-high breakout + volume confirmation (classic momentum pattern) | p = 0.66 — no edge |
| `volume_confirmed` | `volume_confirmed.py` (pre-existing, but never correctly tested until a pipeline bug was fixed) | EMA/RSI crossover requiring above-average volume | p = 0.59 — no edge |

**Validation methodology for `mean_reversion`:**
1. Initial 2-year backtest on 5 stocks (RELIANCE, ICICIBANK, ITC, BHARTIARTL, HDFCBANK) showed a promising pattern for the `mean_reversion_swing` variant (`stop_loss_pct=6.0, take_profit_rsi=60`).
2. Out-of-sample confirmation: same params tested on a completely different, previously-untouched set of 5 stocks (LT, MARUTI, ASIANPAINT, ULTRACEMCO, TITAN) — held up (p=0.03).
3. Final large-pool test: all 15 stocks combined, 5-year window → p=0.0008, 363 pooled trades, 13/15 stocks positive.

**Honest framing used throughout:** repeatedly flagged survivorship bias risk (e.g., breakout strategy explicitly designed around "how do people catch RRKabel-style 50%+ movers," then honestly found no statistical edge — a deliberate lesson, not a failed feature).

### 2.5 Statistical significance testing engine
- `app/backtest/portfolio_stats.py::test_significance()` — the core rigor tool. Pools trade-level P&L across symbols, computes z-score and p-value via normal CDF approximation.
- Exposed via `POST /api/backtest/significance`.

---

## 3. Major bugs found and fixed (real, not hypothetical)

1. **Rate limiting silently non-functional** (pre-existing, fixed before this session per user's prior history) — `default_limits` mechanism broken due to router-level auth dependency interaction; fixed with explicit `@limiter.limit()` decorators.
2. **`main.py` crash: dead `/dashboard` static mount** — `app.mount("/dashboard", StaticFiles(directory="frontend", ...))` referenced a folder that got deleted during the frontend repo merge. Removed the dead route.
3. **`slowapi` / other missing dependencies** — local venv missing packages present in `requirements.txt`'s intent but not actually pinned/installed; resolved via `pip install` + explicit pinning.
4. **NaN crash (occurred in THREE separate places)** — Yahoo Finance occasionally returns `NaN` for missing data points; `json.dumps` can't serialize `NaN`, causing silent 500s. Fixed in:
   - `fetch_historical_closes` (historical_data.py)
   - `fetch_historical_ohlcv` (historical_data.py)
   - `fetch_ohlc_for_chart` (historical_data.py) — found last, via a live Render log during Research-page testing on ADANIENT
   - Also added defense-in-depth NaN filtering in `portfolio_stats.py`'s pooled-trade list.
5. **`engine.py` didn't unpack OHLCV dicts** — `run_backtest()`'s main loop only ever passed `price` (a float) to `strategy.decide()`, never `volume`. When fed OHLCV dict data (for `breakout`/`volume_confirmed`), `price` became a dict object, causing type errors. Fixed by branching on `isinstance(tick, dict)` and unpacking `close`/`volume` correctly. This also revealed `volume_confirmed` had never been correctly tested with real volume data until this fix.
6. **`bot_runner.py` self-import** — a stray `from app.bot_runner import bot_runner` line inside `bot_runner.py` itself caused a circular-import `ImportError` on startup after adding the auto-restart hook. Removed.
7. **`PaperBroker` missing `user_id` param + missing BUY logic** — during the multi-tenant refactor (Phase 2), `PaperBroker.__init__` never actually got the `user_id` parameter added (despite `bot_runner.py` calling it with that kwarg), causing a silent `TypeError` that crashed the background thread on every bot start, always manifesting as `running: false` with no visible error. Separately discovered the BUY branch of `place_order()` was missing the actual cash-deduction/position-recording logic entirely (validated and returned success without doing anything). Both fixed.
8. **bcrypt/passlib version incompatibility** — newer `bcrypt` (4.x+) broke `passlib`'s wrapper, manifesting as a confusing "password cannot be longer than 72 bytes" error on any signup attempt regardless of actual password length. Fixed by pinning `bcrypt==4.0.1`.
9. **Swagger OAuth2 login form mismatch** — `get_current_user`'s `OAuth2PasswordBearer` scheme made Swagger's built-in "Authorize" dialog try to POST to `/login` using OAuth2's standard form fields, which didn't match the custom `LoginRequest` JSON schema. Worked around by testing tokens manually rather than switching to `HTTPBearer` (noted as a possible future cleanup, not yet done).
10. **SQLite ephemeral storage on Render** — `DATABASE_URL=sqlite:///./tradebot.db` meant every Render redeploy wiped the entire database (including newly-created user accounts) because Render's free-tier containers don't persist local files across deploys. This was the most significant infrastructure fix of the session.
11. **Duplicate `DATABASE_URL` env var** — a copy-paste error while fixing #10 left two conflicting `DATABASE_URL` entries in Render's environment settings; resolved by identifying and deleting the stale SQLite one.
12. **Missing `psycopg2-binary`** — after switching to Postgres, the driver package was never actually added to `requirements.txt`, causing `ModuleNotFoundError: No module named 'psycopg2'` on deploy. Added and pinned.
13. **`routes.py` half-migrated during Phase 2** — old singleton bot endpoints (`/bot/start`, `/bot/stop`, `/bot/status`, `/watchlist/screener`) were left calling the new `user_bot_manager` (which requires a `user_id` argument) without actually passing one, and without being properly deleted per the "fully replace" decision. Fixed by deleting the four now-redundant functions (and `/trades`, `/sessions`, which had become a privacy leak — returning all users' data unfiltered) from `routes.py` entirely, since `/me/*` equivalents already existed.
14. **Render free-tier cold-start / keep-alive gaps** — free instance spins down after ~15 min inactivity; a cron-job.org ping was set up to keep it warm, initially scoped to weekday market hours only (`*/10 3-10 * * 1-5` in UTC), later widened to all days/hours (`*/10 * * * *`) once it became clear Research/Backtest Lab don't depend on market hours and should work on weekends too.

---

## 4. Architecture (current state)

```
Alpha Terminal (React, built in Lovable, synced to GitHub, deployed via Lovable's own hosting)
        |
        |  REST API — two parallel auth mechanisms:
        |    - X-API-Key header (static, shared) for public pages: Research, Backtest Lab, Screener
        |    - Authorization: Bearer <JWT> for per-user pages: Dashboard, Live Bot, Trade History
        v
FastAPI backend (Render, Docker, auto-deploys on push to main)
        |
        +--> Yahoo Finance (yfinance) — live prices + historical OHLCV
        |
        +--> Neon Postgres (users, trades, bot_sessions, price_ticks, portfolio_snapshots)
        |     (migrated from Render's free-tier SQLite, which doesn't persist across deploys;
        |      Render's own free Postgres also rejected — 30-day expiry limit on free tier,
        |      and account already had one free DB slot used by an unrelated project, BookIQ)
        |
        +--> Per-user BotRunner (via UserBotManager)
             - one BotRunner instance per logged-in user_id
             - each has its own thread, strategy instances, PaperBroker, portfolio
             - shares nothing with other users except the underlying Yahoo Finance calls
             - known scaling limitation (documented in code comments): API call volume
               scales linearly with concurrent active users; fine for a handful of users,
               would need a shared price-cache refactor to scale further
```

**Auto-healing infrastructure:**
- `main.py` startup hook validates config on boot (fails loudly if `BOT_MODE=live` without real Angel One credentials).
- cron-job.org pings `/api/bot/status` every 10 minutes, all days, to prevent Render free-tier spin-down.
- (Note: the *old* single-bot auto-restart-on-boot hook was removed during the Phase 2 multi-tenant refactor, since there's no longer one global bot to auto-start — each user must manually start their own session. This is a known, accepted trade-off, not an oversight.)

---

## 5. Authentication & multi-tenancy (Phase 1 + Phase 2)

Built in two deliberate phases to avoid breaking the live system mid-refactor:

**Phase 1 — real accounts (non-breaking, additive):**
- `User` model (email, hashed password via `passlib`/bcrypt, created_at).
- `app/auth_user.py` — password hashing, JWT creation/validation (`python-jose`), `get_current_user` FastAPI dependency.
- `app/routes_auth.py` — `/api/auth/signup`, `/api/auth/login`, `/api/auth/me`.
- Kept fully separate from the pre-existing `app/auth.py` (static API-key check) so nothing about the already-working public endpoints changed.

**Phase 2 — full per-user portfolios (bigger, coordinated with frontend):**
- Migration script `app/migrate_add_user_id.py` — one-time, adds `user_id` column to `trades`/`bot_sessions` via raw `ALTER TABLE` (SQLite doesn't support this via `create_all`), creates a placeholder `system@tradebot.internal` user, and backfills all pre-existing trade/session data (10,766 trades, 35 sessions) to that user rather than deleting it.
- `BotRunner` refactored to accept a `user_id` at construction; no longer a bare module-level singleton.
- `UserBotManager` — holds a dict of `{user_id: BotRunner}`, lazily creates one per user on first `/me/bot/start` call.
- `app/routes_user_bot.py` — new router: `/api/me/bot/start`, `/me/bot/stop`, `/me/bot/status`, `/me/watchlist/screener`, `/me/trades`, `/me/sessions`, `/me/portfolio/history`.
- Old singleton endpoints in `routes.py` fully deleted per explicit decision ("Option B: build backend + frontend together, replace fully").
- Frontend: Lovable-built login/signup pages, auth context (localStorage token), protected routes (Dashboard/Live Bot/Trade History) vs. public routes (Research/Backtest Lab/Screener), automatic redirect-to-login on 401.

---

## 6. Frontend (Alpha Terminal, built in Lovable)

Design system: dark theme (`#0B0E11` background), monospace numerics, green/red gain/loss coding, minimal decoration — deliberately styled after Trendlyne/Screener.in/AngelOne/Groww rather than generic SaaS templates.

**Pages:**
- **Dashboard** — portfolio KPIs, equity curve (backend piece just added, frontend wiring pending as of last session), open positions, live signals feed, screener table.
- **Live Bot** — start/stop controls, strategy/symbol/interval selection, current status, open positions, live signals.
- **Research** — search any of ~2,000 NSE symbols, live quote, candlestick chart (TradingView lightweight-charts), fundamentals (P/E, market cap, 52-week range, sector).
- **Backtest Lab** — run any strategy/symbol/period combo, view stats, run the significance test with a dedicated pass/fail p-value card.
- **Trade History** — filterable, paginated trade log.
- **Strategy Stats** — cross-strategy comparison table.
- **Login/Signup** — new, Phase 2 addition.

---

## 7. Known open items / not yet done

1. **Equity curve frontend wiring** — backend endpoint (`GET /api/me/portfolio/history`) and the underlying `PortfolioSnapshot` table/write logic are done and deployed; the Lovable prompt to wire the Dashboard chart to this endpoint was written but not yet sent/built (Lovable's daily credits ran out).
2. **Swagger OAuth2 scheme mismatch** — `get_current_user` uses `OAuth2PasswordBearer`, which makes Swagger's UI try (and fail) to call `/login` with OAuth2's form fields. Works fine for the actual frontend (which calls the JSON endpoints directly), but makes manual Swagger testing of protected routes clunky (must copy/paste tokens manually rather than using the Authorize dialog cleanly). A `HTTPBearer` swap was suggested but not implemented.
3. **BookIQ's Render Postgres also has a 30-day free-tier expiry** (~Aug 17, 2026) — separate, unrelated project, but flagged as a real problem needing its own fix at some point.
4. **Custom domain** — investigated; Lovable requires a $25/month Pro plan for custom domain connection. User has no budget for this right now. Alternative path identified (buy just a domain cheaply, host the already-GitHub-synced frontend for free on Vercel/Netlify with their free custom-domain support) but not yet executed — deferred as a "someday" item, not blocking anything.
5. **No true real-time price ticks** — Yahoo Finance data is inherently ~15-20 min delayed at the source, and the bot's own tick writes happen once per `tick_seconds` (typically 60s), so candlestick/line charts built from ticks show one-price-per-minute bars (open=high=low=close), not true intrabar OHLC. This is an accepted, documented limitation, not a bug — a line/area chart was recommended over candlesticks for the live-tick view specifically because of this.
6. **`trend_following` and `breakout` ATR/trend-strength calculations are close-price-only proxies**, not textbook ATR/ADX (which require high/low intrabar data the engine doesn't currently pass through). Explicitly documented in the strategy files' docstrings so nobody later assumes these match a TradingView backtest number.
7. **Angel One live-trading integration** — credentials exist in local `.env` (never committed, `.gitignore`'d correctly) but live trading was never wired in; the bot has only ever run in `BOT_MODE=paper`. A `AngelLiveFeed` class exists as a stub but is unused. Also worth noting: Angel One requires a static outbound IP for API access, which Render's free tier doesn't provide — live trading would need either a paid Render tier or a different hosting approach to ever work.
8. **A security incident occurred earlier in the project's history** (before this session): Angel One credentials (Client ID, MPIN, TOTP secret) were accidentally typed directly into a chat message. The user was immediately advised to rotate the MPIN and API key; this was done. No live capital was ever at risk since the bot has never run in live mode.

---

## 8. Immediate next steps (as of end of this session)

1. Finish Dashboard equity curve frontend wiring once Lovable credits reset.
2. Weekend QA pass — completed, all 8 test scenarios passed clean (unauthenticated routing, signup flow, fresh-user dashboard state, bot start/stop, Research across multiple symbols, Backtest Lab + significance test, Trade History/Strategy Stats empty states, logout/login persistence).
3. **Monday plan:** record a demo video while NSE market is open (bot actively showing live signals/prices), post to LinkedIn (recommended posting Tuesday/Wednesday morning instead of immediately, per better engagement timing) and cross-post to Twitter/X (active #AlgoTrading community) and a technical writeup on dev.to/Hashnode (durable, search-discoverable, unlike a LinkedIn post).
4. Recommended LinkedIn hook, discussed but not yet drafted as final copy: lead with "I tested 4 strategies, 3 failed a statistical significance test" rather than a generic "I built a trading bot" framing — differentiates from the oversaturated trading-bot-post genre via demonstrated rigor.

---

## 9. Things explicitly decided NOT to build (and why)

- **Full NNFX-style Pine Script / TradingView / crypto-exchange toolchain** (inspired by a YouTube trading-bot creator's workflow) — evaluated and rejected as not applicable; the underlying disciplines (drawdown focus, realistic cost modeling, forward-testing before capital) were already being followed more rigorously in the existing Python system, and switching tools would have meant abandoning stronger existing infrastructure to chase an unproven, differently-scoped toolchain.
- **Discord bot integration** — considered as a "distribution" idea, correctly reframed as a feature (real-time trade alerts via webhook) rather than a growth lever; not built, not currently planned as a priority.
- **Chasing a 5th/6th strategy after 3 straight rejections** (trend_following, breakout, volume_confirmed all failed significance) — explicitly decided to stop strategy-hunting once the pattern became clear, rather than keep testing variations hoping for a second lucky p-value.

## Recently Fixed (Aug 9, 2026 session)

- **Screener showing garbage rows** — `/discover/long-term` response shape 
  (`{disclaimer, ranked_by, candidates}`) wasn't being unwrapped correctly. 
  Fixed in `normalizeScreener()` (lib/api.ts) to recognize the `candidates` 
  key, and reverted the earlier incorrect patch in screener.tsx.

- **Strategy Stats / Backtest Lab showing identical numbers across all 
  strategies** — `runBacktest()` and `runSignificance()` were sending 
  `strategy`, `symbol`, `period` etc. as a JSON body, but the backend 
  routes (`/backtest/historical`, `/backtest/significance`) read them as 
  query params. Backend silently fell back to its defaults every time. 
  Fixed by sending params via query string in api.ts, and correcting the 
  `initial_capital` → `starting_capital` key mismatch.

- **Portfolio Equity Curve now wired to real data** — fetches from 
  `GET /me/portfolio/history`, renders as an area chart, falls back to 
  the existing empty state when no snapshots exist yet.

- **Starting Capital is now user-editable** — added an input field next 
  to Tick Interval on the Live Bot page; passed as `starting_capital` 
  when a new bot session starts.

## Known Open Items

- Backtest Lab chart shows "No candle data returned" even when stats 
  calculate correctly — cosmetic display bug, not yet root-caused.
- [any other genuinely open items from your original doc]