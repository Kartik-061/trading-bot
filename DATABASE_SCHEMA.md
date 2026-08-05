# Database Schema

SQLite by default (`DATABASE_URL` in `.env`), swappable for Postgres by
changing that one connection string - SQLAlchemy handles the rest.

## `trades`

Every executed buy/sell, paper or live.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer, PK | |
| `timestamp` | DateTime | UTC, indexed |
| `symbol` | String | indexed |
| `side` | String | `"BUY"` or `"SELL"` |
| `qty` | Integer | |
| `price` | Float | |
| `value` | Float | `qty * price` |
| `cash_after` | Float | account cash immediately after this trade |
| `is_live` | Boolean | `False` for paper trades, `True` for real Angel One orders |
| `strategy_name` | String | which strategy produced this trade |

## `bot_sessions`

One row per bot run (start → stop), used to compare strategy performance
across separate runs.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer, PK | |
| `started_at` | DateTime | |
| `ended_at` | DateTime | null while still running |
| `symbol` | String | comma-separated symbol list for that run |
| `strategy_name` | String | |
| `starting_capital` | Float | |
| `final_value` | Float | null until the session ends |
| `is_live` | Boolean | |
| `status` | String | `"running"`, `"stopped"`, or `"crashed"` |

## `price_ticks`

Every price observed while the bot is running - powers the live
candlestick chart in the dashboard.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer, PK | |
| `timestamp` | DateTime | indexed |
| `symbol` | String | indexed |
| `price` | Float | |

Grows unbounded during long-running sessions - fine for a demo/portfolio
project, but a production deployment would want a retention policy
(e.g., delete ticks older than N days) or move this to a time-series
store instead of a relational table.

## Relationships

None enforced at the DB level (no foreign keys) - `trades.strategy_name`
and `bot_sessions.strategy_name` are just matching string values, not a
formal relation. Deliberately simple for this project's scale; a larger
system would normalize this into a `strategies` table.
