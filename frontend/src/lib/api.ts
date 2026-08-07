/**
 * API client for the FastAPI NSE trading bot backend.
 * Base URL and API key come from env, never hardcoded.
 */

const env = import.meta.env as Record<string, string | undefined>;

export const API_BASE_URL = (env["VITE_API_BASE_URL"] ?? "https://trading-bot-s2zl.onrender.com/api").replace(
  /\/$/,
  "",
);
export const API_KEY = env["VITE_API_KEY"] ?? "a34f179df723787a807717940a330d9284b21c0f70031fc2defddd8ac9b4d7dd";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, query?: Query) {
  const url = new URL(
    `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`,
    typeof window === "undefined" ? "http://localhost" : window.location.origin,
  );
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function request<T>(
  path: string,
  opts: {
    method?: string | undefined;
    query?: Query | undefined;
    body?: unknown;
    signal?: AbortSignal | undefined;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      ...(opts.body !== undefined ? { body: JSON.stringify(opts.body) } : {}),
      ...(opts.signal ? { signal: opts.signal } : {}),
    });
  } catch {
    throw new ApiError(
      `Cannot reach the trading API at ${API_BASE_URL}. Check that the backend is running.`,
      0,
    );
  }

  if (res.status === 401 || res.status === 403) {
    throw new ApiError(
      "API key rejected. Set VITE_API_KEY to a valid key for this backend.",
      res.status,
    );
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* keep status text */
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>(path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query) =>
    request<T>(path, { method: "POST", body: body ?? {}, query }),
};

/* ----------------------------- domain types ----------------------------- */

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  ltp: number;
  pnl: number;
  pnl_pct: number;
  history?: number[];
}

export interface BotStatus {
  running: boolean;
  session_id: string | null;
  started_at: string | null;
  uptime_seconds: number;
  strategy: string | null;
  symbols: string[];
  interval_seconds: number | null;
  market_open: boolean;
  portfolio_value: number;
  cash: number;
  day_pnl: number;
  day_pnl_pct: number;
  total_return_pct: number;
  positions: Position[];
  equity_curve: { time: string; value: number }[];
}

export type Signal = "BUY" | "SELL" | "HOLD" | "MARKET_CLOSED";

export interface ScreenerRow {
  symbol: string;
  ltp: number;
  change_pct: number;
  signal: Signal;
  rsi: number | null;
  volume: number | null;
  momentum_pct: number | null;
  backtested_return_pct: number | null;
  p_value: number | null;
  validated: boolean;
  updated_at: string | null;
}

export interface Trade {
  timestamp: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  value: number;
  cash_after: number | null;
  pnl: number | null;
  fees: number | null;
  strategy: string | null;
  mode: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BacktestResult {
  symbol?: string | undefined;
  total_return_pct: number;
  win_rate_pct: number;
  max_drawdown_pct: number;
  total_trades: number;
  total_costs: number;
  equity_curve?: { time: string; value: number }[] | undefined;
  trades?: Trade[] | undefined;
}

export interface SignificanceResult {
  z_score: number | null;
  p_value: number | null;
  significant: boolean;
  sample_size: number | null;
  mean_return_pct: number | null;
  note?: string | null;
}

/* --------------------------- normalisation ------------------------------ */

const n = (v: unknown, fallback = 0): number => {
  const x = typeof v === "string" ? Number(v) : v;
  return typeof x === "number" && Number.isFinite(x) ? x : fallback;
};
const nn = (v: unknown): number | null => {
  const x = typeof v === "string" ? Number(v) : v;
  return typeof x === "number" && Number.isFinite(x) ? x : null;
};
const s = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const rec = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" ? (v as Record<string, unknown>) : {};
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

function pick(o: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) if (o[k] !== undefined && o[k] !== null) return o[k];
  return undefined;
}

export function normalizePosition(raw: unknown): Position {
  const o = rec(raw);
  const qty = n(pick(o, "quantity", "qty", "shares"));
  const avg = n(pick(o, "avg_price", "average_price", "entry_price", "buy_price"));
  const ltp = n(pick(o, "ltp", "last_price", "current_price", "price"), avg);
  const pnl = n(pick(o, "pnl", "unrealized_pnl", "profit"), (ltp - avg) * qty);
  return {
    symbol: String(pick(o, "symbol", "ticker") ?? "—"),
    quantity: qty,
    avg_price: avg,
    ltp,
    pnl,
    pnl_pct: n(pick(o, "pnl_pct", "pnl_percent", "return_pct"), avg ? ((ltp - avg) / avg) * 100 : 0),
    history: arr(pick(o, "history", "sparkline", "recent_prices")).map((x) => n(x)),
  };
}

export function normalizeStatus(raw: unknown): BotStatus {
  const o = rec(raw);
  const p = rec(pick(o, "portfolio", "account", "summary"));
  const get = (...keys: string[]) => pick(o, ...keys) ?? pick(p, ...keys);
  const positionsRaw = pick(o, "positions", "open_positions") ?? pick(p, "positions");
  const positions = Array.isArray(positionsRaw)
    ? positionsRaw.map(normalizePosition)
    : Object.entries(rec(positionsRaw)).map(([symbol, v]) =>
        normalizePosition({ symbol, ...rec(v) }),
      );
  return {
    running: Boolean(pick(o, "running", "is_running", "active")),
    session_id: s(get("session_id", "sessionId", "id")),
    started_at: s(get("started_at", "start_time")),
    uptime_seconds: n(get("uptime_seconds", "uptime")),
    strategy: s(get("strategy", "strategy_name")),
    symbols: arr(get("symbols", "watchlist")).map(String),
    interval_seconds: nn(get("interval_seconds", "tick_interval", "interval")),
    market_open: Boolean(get("market_open", "is_market_open")),
    portfolio_value: n(get("portfolio_value", "total_value", "equity", "net_worth")),
    cash: n(get("cash", "cash_available", "available_cash", "balance")),
    day_pnl: n(get("day_pnl", "today_pnl", "daily_pnl", "todays_pnl")),
    day_pnl_pct: n(get("day_pnl_pct", "today_pnl_pct", "daily_pnl_pct")),
    total_return_pct: n(get("total_return_pct", "total_return", "return_pct")),
    positions,
    equity_curve: arr(get("equity_curve", "equity", "portfolio_history")).map((pt) => {
      const q = rec(pt);
      return {
        time: String(pick(q, "time", "timestamp", "date") ?? ""),
        value: n(pick(q, "value", "equity", "portfolio_value")),
      };
    }),
  };
}

const SIGNALS: Signal[] = ["BUY", "SELL", "HOLD", "MARKET_CLOSED"];
function toSignal(v: unknown): Signal {
  const up = String(v ?? "").toUpperCase().replace(/[\s-]/g, "_");
  return (SIGNALS.find((x) => x === up) ?? "HOLD") as Signal;
}

export function normalizeScreenerRow(raw: unknown, key?: string): ScreenerRow {
  const o = rec(raw);
  const pv = nn(pick(o, "p_value", "pvalue"));
  return {
    symbol: String(pick(o, "symbol", "ticker") ?? key ?? "—"),
    ltp: n(pick(o, "ltp", "last_price", "price", "close")),
    change_pct: n(pick(o, "change_pct", "pct_change", "change_percent", "day_change_pct")),
    signal: toSignal(pick(o, "signal", "action", "recommendation")),
    rsi: nn(pick(o, "rsi", "RSI")),
    volume: nn(pick(o, "volume", "vol")),
    momentum_pct: nn(pick(o, "momentum_pct", "momentum", "momentum_percent")),
    backtested_return_pct: nn(pick(o, "backtested_return_pct", "backtest_return_pct")),
    p_value: pv,
    validated: Boolean(pick(o, "validated", "significant")) || (pv !== null && pv < 0.05),
    updated_at: s(pick(o, "updated_at", "timestamp", "last_updated", "time")),
  };
}

export function normalizeScreener(raw: unknown): ScreenerRow[] {
  const o = rec(raw);
  const list = pick(o, "results", "data", "screener", "symbols", "items") ?? raw;
  if (Array.isArray(list)) return list.map((r) => normalizeScreenerRow(r));
  return Object.entries(rec(list)).map(([k, v]) => normalizeScreenerRow(v, k));
}

export function normalizeTrade(raw: unknown): Trade {
  const o = rec(raw);
  const qty = n(pick(o, "quantity", "qty", "shares"));
  const price = n(pick(o, "price", "fill_price", "executed_price"));
  return {
    timestamp: String(pick(o, "timestamp", "time", "executed_at", "date") ?? ""),
    symbol: String(pick(o, "symbol", "ticker") ?? "—"),
    side: String(pick(o, "side", "action", "type") ?? "—").toUpperCase(),
    quantity: qty,
    price,
    value: n(pick(o, "value", "amount", "total"), qty * price),
    cash_after: nn(pick(o, "cash_after", "balance_after", "cash")),
    pnl: nn(pick(o, "pnl", "profit", "realized_pnl")),
    fees: nn(pick(o, "fees", "costs", "total_costs", "charges")),
    strategy: s(pick(o, "strategy", "strategy_name")),
    mode: String(pick(o, "mode", "trade_mode") ?? (pick(o, "live") ? "LIVE" : "PAPER")).toUpperCase(),
  };
}

export function normalizeTrades(raw: unknown): Trade[] {
  const o = rec(raw);
  const list = pick(o, "trades", "results", "data", "items") ?? raw;
  return arr(list).map(normalizeTrade);
}

export function normalizeCandles(raw: unknown): Candle[] {
  const o = rec(raw);
  const list = pick(o, "candles", "data", "results", "ohlc") ?? raw;
  return arr(list)
    .map((c) => {
      const q = rec(c);
      const t = pick(q, "time", "timestamp", "date", "t");
      let time: number;
      if (typeof t === "number") time = t > 1e11 ? Math.floor(t / 1000) : t;
      else time = Math.floor(new Date(String(t)).getTime() / 1000);
      return {
        time,
        open: n(pick(q, "open", "o")),
        high: n(pick(q, "high", "h")),
        low: n(pick(q, "low", "l")),
        close: n(pick(q, "close", "c")),
        volume: n(pick(q, "volume", "v")),
      };
    })
    .filter((c) => Number.isFinite(c.time))
    .sort((a, b) => a.time - b.time);
}

export function normalizeBacktest(raw: unknown): BacktestResult {
  const o = rec(raw);
  const m = { ...rec(pick(o, "metrics", "stats", "summary", "result")), ...o };
  return {
    symbol: s(pick(m, "symbol", "ticker")) ?? undefined,
    total_return_pct: n(pick(m, "total_return_pct", "total_return", "return_pct")),
    win_rate_pct: n(pick(m, "win_rate_pct", "win_rate", "winrate")),
    max_drawdown_pct: n(pick(m, "max_drawdown_pct", "max_drawdown", "mdd")),
    total_trades: n(pick(m, "total_trades", "num_trades", "trade_count")),
    total_costs: n(pick(m, "total_costs", "costs", "total_fees", "fees")),
    equity_curve: arr(pick(m, "equity_curve", "equity")).map((pt) => {
      const q = rec(pt);
      return {
        time: String(pick(q, "time", "timestamp", "date") ?? ""),
        value: n(pick(q, "value", "equity")),
      };
    }),
    trades: normalizeTrades(pick(m, "trades", "trade_log") ?? []),
  };
}

export function normalizeSignificance(raw: unknown): SignificanceResult {
  const o = { ...rec(pick(rec(raw), "significance", "result")), ...rec(raw) };
  const p = nn(pick(o, "p_value", "pvalue", "p"));
  return {
    z_score: nn(pick(o, "z_score", "zscore", "z", "t_stat", "t_statistic")),
    p_value: p,
    significant: Boolean(pick(o, "significant", "is_significant")) || (p !== null && p < 0.05),
    sample_size: nn(pick(o, "sample_size", "n", "num_symbols", "num_trades")),
    mean_return_pct: nn(pick(o, "mean_return_pct", "mean_return", "avg_return_pct")),
    note: s(pick(o, "note", "interpretation", "message")),
  };
}

/* ------------------------------- fetchers ------------------------------- */

export const fetchBotStatus = async () => normalizeStatus(await api.get("/bot/status"));
export const fetchScreener = async () => normalizeScreener(await api.get("/watchlist/screener"));
export const fetchLivePrices = async (symbols?: string[]) =>
  normalizeScreener(await api.get("/prices/live", symbols?.length ? { symbols: symbols.join(",") } : undefined));
export const fetchCandles = async (symbol: string, interval = "1d", period = "6mo") =>
  normalizeCandles(await api.get(`/prices/${encodeURIComponent(symbol)}/candles`, { interval, period }));
export const fetchTrades = async (query?: Query) => normalizeTrades(await api.get("/trades", query));
export const fetchSessions = async () => {
  const raw = await api.get<unknown>("/sessions");
  const list = pick(rec(raw), "sessions", "results", "data") ?? raw;
  return arr(list).map((x) => rec(x));
};
export const fetchDiscoverLongTerm = async () =>
  normalizeScreener(await api.get("/discover/long-term"));

/* ---------------------- tick candles / research ------------------------- */

export interface LiveQuote {
  symbol: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  previous_close: number | null;
  updated_at: string | null;
}

export interface StockInfo {
  symbol: string;
  name: string | null;
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  pe_ratio: number | null;
  week52_high: number | null;
  week52_low: number | null;
  currency: string | null;
}

export function normalizeLiveQuote(raw: unknown, fallbackSymbol: string): LiveQuote {
  const o = rec(raw);
  const inner = rec(pick(o, "data", "quote", "result") ?? o);
  const g = (...keys: string[]) => pick(o, ...keys) ?? pick(inner, ...keys);
  const price = nn(g("price", "ltp", "last_price", "current_price", "close"));
  const prev = nn(g("previous_close", "prev_close", "previousClose"));
  const change = nn(g("change", "change_abs", "day_change"));
  const pctv = nn(g("change_pct", "pct_change", "change_percent", "changePercent"));
  return {
    symbol: String(g("symbol", "ticker") ?? fallbackSymbol),
    price,
    change: change ?? (price !== null && prev !== null ? price - prev : null),
    change_pct:
      pctv ?? (price !== null && prev ? ((price - prev) / prev) * 100 : null),
    previous_close: prev,
    updated_at: s(g("updated_at", "timestamp", "time", "last_updated")),
  };
}

export function normalizeStockInfo(raw: unknown, fallbackSymbol: string): StockInfo {
  const o = rec(raw);
  const inner = rec(pick(o, "info", "data", "result") ?? o);
  const g = (...keys: string[]) => pick(o, ...keys) ?? pick(inner, ...keys);
  return {
    symbol: String(g("symbol", "ticker") ?? fallbackSymbol),
    name: s(g("name", "long_name", "longName", "company_name", "shortName")),
    sector: s(g("sector", "gics_sector")),
    industry: s(g("industry", "industry_group")),
    market_cap: nn(g("market_cap", "marketCap", "mcap")),
    pe_ratio: nn(g("pe_ratio", "pe", "trailingPE", "trailing_pe", "price_to_earnings")),
    week52_high: nn(g("week52_high", "fifty_two_week_high", "fiftyTwoWeekHigh", "52_week_high", "high_52w")),
    week52_low: nn(g("week52_low", "fifty_two_week_low", "fiftyTwoWeekLow", "52_week_low", "low_52w")),
    currency: s(g("currency")),
  };
}

export const fetchTickCandles = async (symbol: string, intervalSeconds = 60, limit = 100) =>
  normalizeCandles(
    await api.get(`/prices/${encodeURIComponent(symbol)}/candles`, {
      interval_seconds: intervalSeconds,
      limit,
    }),
  );

export const fetchLiveQuote = async (symbol: string) =>
  normalizeLiveQuote(await api.get(`/prices/${encodeURIComponent(symbol)}/live`), symbol);

export const fetchStockChart = async (symbol: string, period = "3mo") =>
  normalizeCandles(
    await api.get(`/discover/stock-chart/${encodeURIComponent(symbol)}`, { period }),
  );

export const fetchStockInfo = async (symbol: string) =>
  normalizeStockInfo(await api.get(`/discover/stock-info/${encodeURIComponent(symbol)}`), symbol);


export const startBot = (body: Record<string, unknown>) => api.post("/bot/start", body);
export const stopBot = () => api.post("/bot/stop", {});
export const runBacktest = async (body: Record<string, unknown>) =>
  normalizeBacktest(await api.post("/backtest/historical", body));
export const runBatchBacktest = async (body: Record<string, unknown>) => {
  const raw = await api.post<unknown>("/backtest/batch", body);
  const list = pick(rec(raw), "results", "data", "backtests") ?? raw;
  if (Array.isArray(list)) return list.map(normalizeBacktest);
  return Object.entries(rec(list)).map(([symbol, v]) => ({
    ...normalizeBacktest(v),
    symbol,
  }));
};
export const runSignificance = async (body: Record<string, unknown>) =>
  normalizeSignificance(await api.post("/backtest/significance", body));
