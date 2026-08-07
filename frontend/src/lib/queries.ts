import { queryOptions } from "@tanstack/react-query";

import {
  fetchBotStatus,
  fetchCandles,
  fetchLiveQuote,
  fetchScreener,
  fetchSessions,
  fetchStockChart,
  fetchStockInfo,
  fetchTickCandles,
  fetchTrades,
} from "@/lib/api";

export const TICK_POLL_MS = 30_000;

export const tickCandlesQuery = (symbol: string) =>
  queryOptions({
    queryKey: ["prices", "tick-candles", symbol],
    queryFn: () => fetchTickCandles(symbol, 60, 100),
    enabled: Boolean(symbol),
    refetchInterval: TICK_POLL_MS,
    retry: 1,
  });

export const liveQuoteQuery = (symbol: string) =>
  queryOptions({
    queryKey: ["prices", "live", symbol],
    queryFn: () => fetchLiveQuote(symbol),
    enabled: Boolean(symbol),
    refetchInterval: TICK_POLL_MS,
    retry: 1,
  });

export const stockChartQuery = (symbol: string, period: string) =>
  queryOptions({
    queryKey: ["discover", "stock-chart", symbol, period],
    queryFn: () => fetchStockChart(symbol, period),
    enabled: Boolean(symbol),
    retry: 1,
  });

export const stockInfoQuery = (symbol: string) =>
  queryOptions({
    queryKey: ["discover", "stock-info", symbol],
    queryFn: () => fetchStockInfo(symbol),
    enabled: Boolean(symbol),
    retry: 1,
  });


export const POLL_MS = 20_000;

export const botStatusQuery = () =>
  queryOptions({
    queryKey: ["bot", "status"],
    queryFn: () => fetchBotStatus(),
    refetchInterval: POLL_MS,
    retry: 1,
  });

export const screenerQuery = () =>
  queryOptions({
    queryKey: ["watchlist", "screener"],
    queryFn: () => fetchScreener(),
    refetchInterval: POLL_MS,
    retry: 1,
  });

export const tradesQuery = (params: Record<string, string | number | undefined>) =>
  queryOptions({
    queryKey: ["trades", params],
    queryFn: () => fetchTrades(params),
    retry: 1,
  });

export const sessionsQuery = () =>
  queryOptions({ queryKey: ["sessions"], queryFn: () => fetchSessions(), retry: 1 });

export const candlesQuery = (symbol: string, interval: string, period: string) =>
  queryOptions({
    queryKey: ["candles", symbol, interval, period],
    queryFn: () => fetchCandles(symbol, interval, period),
    enabled: Boolean(symbol),
    retry: 1,
  });
