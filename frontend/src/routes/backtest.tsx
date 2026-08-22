import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { CandleChart } from "@/components/charts";
import { ErrorState, Panel, SkeletonRows, StatCard, Tag } from "@/components/kit";
import { stockChartQuery } from "@/lib/queries";
import { runBacktest, runBatchBacktest, runSignificance } from "@/lib/api";
import type { BacktestResult, SignificanceResult, Trade } from "@/lib/api";
import { INTERVALS, PERIODS, STRATEGIES } from "@/lib/strategies";
import { inr, num, pct, stamp, toneClass } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/backtest")({
  head: () => ({
    meta: [
      { title: "Backtest Lab — NSE Quant Desk" },
      {
        name: "description",
        content:
          "Run historical and batch backtests on NSE stocks with brokerage/tax cost modeling and a statistical significance test.",
      },
      { property: "og:title", content: "Backtest Lab — NSE Quant Desk" },
      {
        property: "og:description",
        content:
          "Historical and batch NSE backtests with Indian cost modeling and statistical significance testing.",
      },
    ],
  }),
  component: BacktestLab,
});

const fieldCls =
  "num h-7 w-full border border-border bg-background rounded-[2px] px-2 text-[12px] focus:border-primary focus:outline-none";

function BacktestLab() {
  const [strategy, setStrategy] = useState<string>("mean_reversion");
  const [symbols, setSymbols] = useState("RELIANCE,TCS,HDFCBANK");
  const [interval, setInterval] = useState<string>("1d");
  const [period, setPeriod] = useState<string>("2y");
  const [capital, setCapital] = useState("100000");

  const symbolList = symbols
    .split(",")
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);
  const primary = symbolList[0] ?? "";

  const body = () => ({
    strategy,
    symbols: symbolList,
    symbol: primary,
    interval,
    period,
    initial_capital: Number(capital) || 100000,
  });

  const single = useMutation<BacktestResult, Error>({ mutationFn: () => runBacktest(body()) });
  const batch = useMutation<BacktestResult[], Error>({ mutationFn: () => runBatchBacktest(body()) });
  const sig = useMutation<SignificanceResult, Error>({ mutationFn: () => runSignificance(body()) });

  const candles = useQuery(stockChartQuery(primary, period));

  const result = single.data;
  const trades: Trade[] = result?.trades ?? [];

  const runAll = () => {
    single.mutate();
    if (symbolList.length > 1) batch.mutate();
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold tracking-tight">Backtest Lab</h1>
        <Tag>Costs include Indian brokerage, STT, GST and stamp duty</Tag>
      </div>

      <Panel title="Backtest Configuration" bodyClassName="p-3 space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div>
            <label className="label-xs block mb-1">Strategy</label>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className={fieldCls}>
              {STRATEGIES.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className="label-xs block mb-1">Symbols</label>
            <input value={symbols} onChange={(e) => setSymbols(e.target.value)} className={fieldCls} />
          </div>
          <div>
            <label className="label-xs block mb-1">Interval</label>
            <select value={interval} onChange={(e) => setInterval(e.target.value)} className={fieldCls}>
              {INTERVALS.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label-xs block mb-1">Period</label>
            <select value={period} onChange={(e) => setPeriod(e.target.value)} className={fieldCls}>
              {PERIODS.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label-xs block mb-1">Starting Capital ₹</label>
            <input
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              inputMode="numeric"
              className={fieldCls}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={runAll}
            disabled={single.isPending || !primary}
            className="h-7 px-3 rounded-[2px] bg-primary text-primary-foreground text-[12px] font-medium disabled:opacity-40"
          >
            {single.isPending ? "Running…" : "Run Backtest"}
          </button>
          <button
            onClick={() => sig.mutate()}
            disabled={sig.isPending || !symbolList.length}
            className="h-7 px-3 rounded-[2px] border border-primary/50 text-primary text-[12px] font-medium disabled:opacity-40"
          >
            {sig.isPending ? "Testing…" : "Run Significance Test"}
          </button>
        </div>
        {single.error && <ErrorState error={single.error} compact />}
      </Panel>

      {(sig.data || sig.isPending || sig.error) && (
        <Panel
          title="Statistical Significance"
          right={
            sig.data ? (
              <span
                className={cn(
                  "border rounded-[2px] px-1.5 py-[1px] text-[10px] font-semibold",
                  sig.data.significant
                    ? "border-gain/50 text-gain bg-gain/10"
                    : "border-border text-muted-foreground",
                )}
              >
                {sig.data.significant ? "STATISTICALLY SIGNIFICANT" : "NOT SIGNIFICANT"}
              </span>
            ) : null
          }
          bodyClassName="p-3"
          className="border-primary/40"
        >
          {sig.isPending ? (
            <SkeletonRows rows={2} cols={4} />
          ) : sig.error ? (
            <ErrorState error={sig.error} compact />
          ) : sig.data ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <StatCard label="Z-Score" value={num(sig.data.z_score, 3)} />
                <StatCard
                  label="P-Value"
                  value={sig.data.p_value === null ? "—" : sig.data.p_value.toPrecision(3)}
                  tone={sig.data.significant ? 1 : 0}
                />
                <StatCard label="Sample Size" value={sig.data.sample_size ?? "—"} />
                <StatCard
                  label="Mean Return"
                  value={pct(sig.data.mean_return_pct)}
                  tone={sig.data.mean_return_pct ?? 0}
                />
              </div>
              <p className="text-[11px] leading-4 text-muted-foreground">
                {sig.data.note ??
                  (sig.data.significant
                    ? "Statistically significant at p<0.05 across the tested NSE large-cap universe. Past backtest results describe historical behaviour only and are not a forecast of future returns."
                    : "Result is not statistically significant at p<0.05 for this configuration. Treat the returns as indistinguishable from noise.")}
              </p>
            </div>
          ) : null}
        </Panel>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-3">
        <Panel
          title={`Price — ${primary || "select a symbol"}`}
          className="xl:col-span-3"
          bodyClassName="p-2"
        >
          {candles.isLoading ? (
            <div className="h-[380px] animate-pulse bg-hairline/40 rounded-[2px]" />
          ) : candles.isError ? (
            <ErrorState error={candles.error} />
          ) : (candles.data?.length ?? 0) > 0 ? (
            <CandleChart data={candles.data ?? []} height={380} />
          ) : (
            <div className="h-[380px] grid place-items-center text-[12px] text-muted-foreground">
              No candle data returned for {primary}.
            </div>
          )}
        </Panel>

        <div className="xl:col-span-2 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <StatCard
              label="Total Return"
              value={pct(result?.total_return_pct)}
              tone={result?.total_return_pct ?? 0}
              loading={single.isPending}
            />
            <StatCard
              label="Win Rate"
              value={pct(result?.win_rate_pct)}
              loading={single.isPending}
            />
            <StatCard
              label="Max Drawdown"
              value={pct(result?.max_drawdown_pct)}
              tone={result ? -1 : 0}
              loading={single.isPending}
            />
            <StatCard
              label="Total Trades"
              value={result ? String(result.total_trades) : "—"}
              loading={single.isPending}
            />
            <StatCard
              label="Total Costs"
              value={inr(result?.total_costs, 0)}
              sub="brokerage + taxes"
              loading={single.isPending}
            />
            <StatCard
              label="Symbols Tested"
              value={String(symbolList.length)}
              sub={period + " · " + interval}
            />
          </div>

          {batch.data && batch.data.length > 0 && (
            <Panel title="Batch Results">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-border">
                    <th className="label-xs px-3 py-1.5 text-left font-medium">Symbol</th>
                    <th className="label-xs px-3 py-1.5 text-right font-medium">Return %</th>
                    <th className="label-xs px-3 py-1.5 text-right font-medium">Win %</th>
                    <th className="label-xs px-3 py-1.5 text-right font-medium">Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.data.map((r, i) => (
                    <tr key={`${r.symbol}-${i}`} className="border-b border-border/60">
                      <td className="px-3 py-1.5">{r.symbol ?? "—"}</td>
                      <td className={cn("num px-3 py-1.5 text-right", toneClass(r.total_return_pct))}>
                        {pct(r.total_return_pct)}
                      </td>
                      <td className="num px-3 py-1.5 text-right">{pct(r.win_rate_pct)}</td>
                      <td className="num px-3 py-1.5 text-right">{r.total_trades}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>
      </div>

      <Panel title="Trade Log">
        {single.isPending ? (
          <SkeletonRows cols={6} />
        ) : trades.length === 0 ? (
          <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">
            Run a backtest to see its trade log.
          </div>
        ) : (
          <div className="max-h-[420px] overflow-auto">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-surface">
                <tr className="border-b border-border">
                  {["Side", "Price", "Qty", "P&L", "Fees", "Timestamp"].map((h, i) => (
                    <th
                      key={h}
                      className={cn(
                        "label-xs px-3 py-1.5 font-medium",
                        i === 0 || i === 5 ? "text-left" : "text-right",
                      )}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i} className="border-b border-border/60">
                    <td
                      className={cn(
                        "px-3 py-1.5 font-medium",
                        t.side === "BUY" ? "text-gain" : t.side === "SELL" ? "text-loss" : "",
                      )}
                    >
                      {t.side}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{num(t.price)}</td>
                    <td className="num px-3 py-1.5 text-right">{t.quantity}</td>
                    <td className={cn("num px-3 py-1.5 text-right", toneClass(t.pnl))}>
                      {t.pnl === null ? "—" : inr(t.pnl)}
                    </td>
                    <td className="num px-3 py-1.5 text-right text-muted-foreground">
                      {t.fees === null ? "—" : inr(t.fees)}
                    </td>
                    <td className="num px-3 py-1.5 text-muted-foreground">{stamp(t.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
