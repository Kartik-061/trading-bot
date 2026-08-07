import { createFileRoute } from "@tanstack/react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorState, Panel, SkeletonRows, StatCard, Tag } from "@/components/kit";
import { STRATEGIES } from "@/lib/strategies";
import { runBacktest, runSignificance } from "@/lib/api";
import type { BacktestResult, SignificanceResult } from "@/lib/api";
import { sessionsQuery } from "@/lib/queries";
import { inr, pct, toneClass } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/strategy-stats")({
  head: () => ({
    meta: [
      { title: "Strategy Stats — NSE Quant Desk" },
      {
        name: "description",
        content:
          "Side-by-side comparison of mean-reversion, EMA/RSI, trend-following and volume-confirmed NSE strategies.",
      },
      { property: "og:title", content: "Strategy Stats — NSE Quant Desk" },
      {
        property: "og:description",
        content:
          "Compare mean-reversion, EMA/RSI, trend-following and volume-confirmed NSE strategy backtests.",
      },
    ],
  }),
  component: StrategyStats,
});

const fieldCls =
  "num h-7 border border-border bg-background rounded-[2px] px-2 text-[12px] focus:border-primary focus:outline-none";

function StrategyStats() {
  const [symbols, setSymbols] = useState("RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK");
  const [period, setPeriod] = useState("5y");
  const [enabled, setEnabled] = useState(false);

  const symbolList = symbols
    .split(",")
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);

  const sessions = useQuery(sessionsQuery());

  const backtests = useQueries({
    queries: STRATEGIES.map((strategy) => ({
      queryKey: ["strategy-stats", "backtest", strategy, symbolList.join(","), period],
      queryFn: (): Promise<BacktestResult> =>
        runBacktest({
          strategy,
          symbol: symbolList[0],
          symbols: symbolList,
          interval: "1d",
          period,
          initial_capital: 100000,
        }),
      enabled,
      retry: 0,
      staleTime: 5 * 60_000,
    })),
  });

  const significances = useQueries({
    queries: STRATEGIES.map((strategy) => ({
      queryKey: ["strategy-stats", "significance", strategy, symbolList.join(","), period],
      queryFn: (): Promise<SignificanceResult> =>
        runSignificance({ strategy, symbols: symbolList, interval: "1d", period }),
      enabled,
      retry: 0,
      staleTime: 5 * 60_000,
    })),
  });

  const completed = backtests.filter((q) => q.data).length;
  const best = backtests.reduce<number | null>(
    (acc, q) => (q.data ? Math.max(acc ?? -Infinity, q.data.total_return_pct) : acc),
    null,
  );
  const avgWin =
    completed > 0
      ? backtests.reduce((a, q) => a + (q.data?.win_rate_pct ?? 0), 0) / completed
      : null;
  const anySignificant = significances.some((q) => q.data?.significant);
  const firstError = backtests.find((q) => q.error)?.error;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold tracking-tight">Strategy Stats</h1>
        <Tag>Backtested results only — not a forecast of future returns</Tag>
      </div>

      <Panel title="Comparison Run" bodyClassName="p-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[260px]">
            <label className="label-xs block mb-1">Symbols</label>
            <input
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              className={cn(fieldCls, "w-full")}
            />
          </div>
          <div>
            <label className="label-xs block mb-1">Period</label>
            <select value={period} onChange={(e) => setPeriod(e.target.value)} className={fieldCls}>
              {["1y", "2y", "5y"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() => setEnabled(true)}
            className="h-7 px-3 rounded-[2px] bg-primary text-primary-foreground text-[12px] font-medium"
          >
            Run all 4 strategies
          </button>
        </div>
        {firstError && <div className="mt-3"><ErrorState error={firstError} compact /></div>}
      </Panel>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatCard label="Backtests Run" value={`${completed}/${STRATEGIES.length}`} />
        <StatCard label="Best Return" value={pct(best)} tone={best ?? 0} />
        <StatCard label="Avg Win Rate" value={pct(avgWin)} />
        <StatCard
          label="Significance"
          value={anySignificant ? "p<0.05" : enabled ? "not shown" : "—"}
          sub={anySignificant ? "at least one variant passes" : "run the comparison"}
          tone={anySignificant ? 1 : 0}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        {STRATEGIES.map((strategy, i) => {
          const bt = backtests[i];
          const sig = significances[i];
          return (
            <Panel key={strategy} title={strategy} bodyClassName="p-3">
              {!enabled ? (
                <p className="text-[12px] text-muted-foreground">Not run yet.</p>
              ) : bt?.isLoading ? (
                <SkeletonRows rows={4} cols={2} />
              ) : bt?.error ? (
                <ErrorState error={bt.error} compact />
              ) : (
                <dl className="grid grid-cols-2 gap-y-2 text-[12px]">
                  <dt className="label-xs self-center">Return</dt>
                  <dd className={cn("num text-right", toneClass(bt?.data?.total_return_pct))}>
                    {pct(bt?.data?.total_return_pct)}
                  </dd>
                  <dt className="label-xs self-center">Win Rate</dt>
                  <dd className="num text-right">{pct(bt?.data?.win_rate_pct)}</dd>
                  <dt className="label-xs self-center">Max DD</dt>
                  <dd className="num text-right text-loss">{pct(bt?.data?.max_drawdown_pct)}</dd>
                  <dt className="label-xs self-center">Trades</dt>
                  <dd className="num text-right">{bt?.data?.total_trades ?? "—"}</dd>
                  <dt className="label-xs self-center">Costs</dt>
                  <dd className="num text-right text-muted-foreground">
                    {inr(bt?.data?.total_costs, 0)}
                  </dd>
                  <dt className="label-xs self-center">Significance</dt>
                  <dd className="text-right">
                    <span
                      className={cn(
                        "num border rounded-[2px] px-1.5 py-[1px] text-[10px] font-semibold",
                        sig?.data?.significant
                          ? "border-gain/50 text-gain bg-gain/10"
                          : "border-border text-muted-foreground",
                      )}
                    >
                      {sig?.isLoading
                        ? "…"
                        : sig?.data?.p_value !== null && sig?.data?.p_value !== undefined
                          ? `p=${sig.data.p_value.toPrecision(2)}`
                          : "n/a"}
                    </span>
                  </dd>
                </dl>
              )}
            </Panel>
          );
        })}
      </div>

      <Panel title="Strategy Comparison">
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-border">
                {["Strategy", "Return %", "Win Rate %", "Max DD %", "Trades", "Costs ₹", "Z-Score", "P-Value", "Verdict"].map(
                  (h, i) => (
                    <th
                      key={h}
                      className={cn(
                        "label-xs px-3 py-1.5 font-medium",
                        i === 0 || i === 8 ? "text-left" : "text-right",
                      )}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {STRATEGIES.map((strategy, i) => {
                const d = backtests[i]?.data;
                const sg = significances[i]?.data;
                return (
                  <tr key={strategy} className="border-b border-border/60">
                    <td className="px-3 py-1.5 font-medium">{strategy}</td>
                    <td className={cn("num px-3 py-1.5 text-right", toneClass(d?.total_return_pct))}>
                      {pct(d?.total_return_pct)}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{pct(d?.win_rate_pct)}</td>
                    <td className="num px-3 py-1.5 text-right text-loss">
                      {pct(d?.max_drawdown_pct)}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{d?.total_trades ?? "—"}</td>
                    <td className="num px-3 py-1.5 text-right text-muted-foreground">
                      {inr(d?.total_costs, 0)}
                    </td>
                    <td className="num px-3 py-1.5 text-right">
                      {sg?.z_score === null || sg?.z_score === undefined
                        ? "—"
                        : sg.z_score.toFixed(3)}
                    </td>
                    <td className="num px-3 py-1.5 text-right">
                      {sg?.p_value === null || sg?.p_value === undefined
                        ? "—"
                        : sg.p_value.toPrecision(3)}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-1.5 text-[11px]",
                        sg?.significant ? "text-gain" : "text-muted-foreground",
                      )}
                    >
                      {sg
                        ? sg.significant
                          ? "Significant at p<0.05"
                          : "Not significant"
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Bot Sessions">
        {sessions.isLoading ? (
          <SkeletonRows rows={3} cols={3} />
        ) : sessions.isError ? (
          <ErrorState error={sessions.error} />
        ) : (sessions.data?.length ?? 0) === 0 ? (
          <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">
            No bot sessions recorded yet.
          </div>
        ) : (
          <ul className="divide-y divide-border/60 text-[12px]">
            {(sessions.data ?? []).slice(0, 10).map((s, i) => (
              <li key={i} className="num px-3 py-1.5 text-muted-foreground truncate">
                {JSON.stringify(s)}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
