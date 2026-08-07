# Alpha Terminal

Lovable Prompt — NSE Trading Bot Dashboard

Paste everything below into Lovable as your build prompt.

Project brief

Build a professional trading dashboard for an NSE (Indian stock market) algorithmic trading bot. The aesthetic reference is Trendlyne, Screener.in, AngelOne, and Groww — not a generic SaaS admin template. This should look like a serious retail/prosumer trading terminal: dark, dense, data-heavy, monospaced numbers, zero decorative fluff (no gradients, no illustrations, no big rounded soft-shadow cards).

The backend is a real FastAPI service with live NSE price data, a statistically validated trading strategy (mean-reversion, backtested with p=0.0008 significance across 15 large-cap stocks), real position sizing, and real Indian brokerage/tax cost modeling. The frontend should reflect that this is a serious, rigorously-tested system — not a toy demo.

Design system

Colors

Background: near-black, #0B0E11 (not dark-gray — true dark)

Surface/card background: #12161C, barely lighter than base

Borders/dividers: #1F242C, 1px, low contrast — density comes from spacing, not boxes

Gains: #00C853

Losses: #FF3B30

Primary accent (buttons, active states, links): one restrained teal/blue, e.g. #2E7CF6

Text primary: #F5F5F7

Text muted/labels: #8A8F98

Typography

All numeric data (prices, %, ₹ values, quantities) in a monospace font — JetBrains Mono or IBM Plex Mono

UI labels/text in a clean sans-serif — Inter or similar

Numbers should be visually dominant: larger and bolder than their labels, which sit small and muted above/beside them

General rules

No gradients, no drop shadows beyond a 1px border, no illustrations, no empty-state mascots

High information density — more real data per screen than typical dashboards, organized with tight spacing and clear grid alignment

Green/red color-coding must be 100% consistent everywhere (gains always green, losses always red, no exceptions)

Small credibility badges throughout (e.g. "p=0.0008 · statistically validated") instead of decorative empty visual elements

Page structure

1. Top bar (persistent)

Left: bot name/logo + market status pill — green dot "Market Open" or gray dot "Market Closed" (driven by a market-hours check from the API)

Center: symbol search/quick-jump

Right: total portfolio value (large, bold, monospace) + today's P&L with up/down arrow, color-coded

2. Left sidebar (persistent nav)

Dashboard

Live Bot

Backtest Lab

Screener / Watchlist

Trade History

Strategy Stats

3. Dashboard page (main/home screen)

Row 1 — KPI strip: 5 compact stat cards in a row: Portfolio Value, Cash Available, Today's P&L (₹ and %), Total Return % (since start), Active Positions count. Big monospace number, tiny muted label above it, no icons needed.

Row 2 — Portfolio equity curve: largest visual element on the page. Line chart, area-filled below the line (green fill if net positive, red if negative). Period toggle above it: 1D / 1W / 1M / 3M / 1Y / ALL.

Row 3 — two-column split:

Left (60%): Open Positions table — columns: Symbol, Qty, Avg Price, LTP, P&L ₹, P&L %, and a small inline sparkline per row showing recent price movement for that symbol.

Right (40%): Live Signals feed — scrollable list, one row per watchlist symbol: Symbol, current Signal (BUY/SELL/HOLD/MARKET_CLOSED as a colored badge), momentum %, last updated timestamp.

Row 4 — Screener/Watchlist data grid: full-width, sortable table. Columns: Symbol, LTP, Change %, Signal, RSI, Volume, Backtested Return % (from the significance-tested strategy), and a small "Validated" badge with the p-value on hover/tooltip for symbols that were part of the significance test.

4. Live Bot page

Bot control panel: Start/Stop button, strategy selector dropdown, symbol multi-select (comma-separated watchlist), tick interval input

Current status card: running/stopped, session ID, uptime, current strategy

Same open-positions table and live-signals feed as dashboard, but full width and this is their dedicated home

5. Backtest Lab page

Controls: strategy selector, symbol multi-select, interval (5m/1d etc.), period (60d/2y/5y), starting capital input

Run button → results panel:

Candlestick chart with volume subpanel for the tested symbol(s)

Stat cards: Total Return %, Win Rate %, Max Drawdown %, Total Trades, Total Costs ₹

If running the significance endpoint: a dedicated "Statistical Significance" card showing Z-score, P-value, and a clear pass/fail badge ("Statistically Significant" in green if p<0.05, muted gray otherwise) — this is the standout differentiator feature, make it visually prominent, not buried

Trade log table below (Side, Price, Qty, P&L, Fees, Timestamp)

6. Trade History page

Full trade log table, filterable by symbol/strategy/date range, paginated

Columns: Timestamp, Symbol, Side, Qty, Price, Value, Cash After, Strategy, Live/Paper badge

7. Strategy Stats page

Summary cards per strategy variant: Total Backtests Run, Best Return %, Avg Win Rate, Significance status

A comparison table across strategies (mean_reversion vs ema_rsi vs trend_following vs volume_confirmed) showing their most recent backtest stats side by side

Charts

Use TradingView's lightweight-charts library (free, open-source, npm-installable) for:

Candlestick + volume charts (Backtest Lab, any stock detail view)

Line/area charts for the portfolio equity curve

This is the same charting library actual trading platforms use — it will look immediately authentic rather than like a generic chart library.

API integration

Base URL: configurable env variable (e.g. VITE_API_BASE_URL), defaulting to http://127.0.0.1:8000/api for local dev.

All requests need an X-API-Key header (or whatever header verify_api_key expects) — pull the key from an env variable, never hardcode it.

Key endpoints to wire up (fetch real data, do not use mock/placeholder data):

Endpoint Method Used for /bot/status GET Dashboard KPIs, positions table, portfolio value /bot/start POST Live Bot page controls /bot/stop POST Live Bot page controls /watchlist/screener GET Live signals feed, screener table /prices/live GET Real-time price ticker/refresh /prices/{symbol}/candles GET Candlestick chart data /trades GET Trade History page /sessions GET Session history/uptime tracking /backtest/historical POST Backtest Lab single-symbol runs /backtest/batch POST Backtest Lab multi-symbol grid runs /backtest/significance POST Backtest Lab statistical significance card /discover/long-term GET Screener page additional ranking data

Poll /bot/status and /watchlist/screener every 15-30 seconds when the Live Bot or Dashboard page is active, not more frequently (avoid hammering the backend/Yahoo Finance rate limits).

Handle loading and error states explicitly for every fetch — skeleton loaders for cards/tables while loading, a clear inline error message (not a silent blank screen) if a call fails (e.g. bot not running, market closed, API key missing).

Tone/copy guidance

Never claim guaranteed returns or use hype language ("guaranteed profits," "get rich," etc.)

Where the significance test result is shown, use precise, honest framing: "Statistically significant at p<0.05 across 15 NSE large-cap stocks, 5-year backtest" rather than vague claims like "proven winning strategy"

Market-closed and paper-trading states should be clearly labeled, not hidden — this is a paper-trading/backtesting tool right now, not connected to live capital, and the UI shouldn't imply otherwise

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/0fcf35d5-143d-4abf-84dd-fcfbed6531c5).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
