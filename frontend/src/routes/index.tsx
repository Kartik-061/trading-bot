import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { AreaChart } from "@/components/charts";
import { ErrorState, Panel, SkeletonRows, StatCard, Tag } from "@/components/kit";
import { LivePriceCard } from "@/components/LivePriceCard";
import { PositionsTable } from "@/components/PositionsTable";
import { SignalsFeed } from "@/components/SignalsFeed";
import { ScreenerTable } from "@/components/ScreenerTable";

import { botStatusQuery, screenerQuery } from "@/lib/queries";
import { inr, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard — NSE Quant Desk Trading Terminal" },
      {
        name: "description",
        content:
          "Live portfolio, open positions and signals for a statistically validated NSE mean-reversion paper-trading bot.",
      },
      { property: "og:title", content: "Dashboard — NSE Quant Desk Trading Terminal" },
      {
        property: "og:description",
        content:
          "Live portfolio, open positions and signals for a statistically validated NSE mean-reversion paper-trading bot.",
      },
    ],
  }),
  component: Dashboard,
});

const PERIODS = ["1D", "1W", "1M", "3M", "1Y", "ALL"] as const;
type Period = (typeof PERIODS)[number];
const DAYS: Record<Period, number> = { "1D": 1, "1W": 7, "1M": 30, "3M": 90, "1Y": 365, ALL: 0 };

function Dashboard() {
  const status = useQuery(botStatusQuery());
  const screener = useQuery(screenerQuery());
  const [period, setPeriod] = useState<Period>("1M");

  const curve = useMemo(() => {
    const all = status.data?.equity_curve ?? [];
    const days = DAYS[period];
    if (!days) return all;
    const cutoff = Date.now() - days * 86_400_000;
    const filtered = all.filter((p) => new Date(p.time).getTime() >= cutoff);
    return filtered.length > 1 ? filtered : all;
  }, [status.data, period]);

  const netPositive =
    curve.length > 1 ? (curve.at(-1)?.value ?? 0) >= (curve[0]?.value ?? 0) : true;

  const s = status.data;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold tracking-tight">Dashboard</h1>
        <Tag tone="accent" title="5-year backtest across 15 NSE large-cap stocks">
          p=0.0008 · statistically validated
        </Tag>
      </div>

      {status.isError && <ErrorState error={status.error} compact />}

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-2">
        <StatCard
          label="Portfolio Value"
          value={inr(s?.portfolio_value, 0)}
          loading={status.isLoading}
        />
        <StatCard label="Cash Available" value={inr(s?.cash, 0)} loading={status.isLoading} />
        <StatCard
          label="Today's P&L"
          value={inr(s?.day_pnl, 0)}
          sub={pct(s?.day_pnl_pct)}
          tone={s?.day_pnl ?? 0}
          loading={status.isLoading}
        />
        <StatCard
          label="Total Return"
          value={pct(s?.total_return_pct)}
          sub="since inception"
          tone={s?.total_return_pct ?? 0}
          loading={status.isLoading}
        />
        <StatCard
          label="Active Positions"
          value={s ? String(s.positions.length) : "—"}
          sub={s?.running ? "bot running" : "bot stopped"}
          loading={status.isLoading}
        />
      </div>

      <Panel
        title="Portfolio Equity Curve"
        right={
          <div className="flex items-center gap-0.5">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  "num px-2 py-[2px] text-[10px] rounded-[2px] border",
                  p === period
                    ? "border-primary/50 bg-primary/10 text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {p}
              </button>
            ))}
          </div>
        }
        bodyClassName="p-2"
      >
        {status.isLoading ? (
          <div className="h-[300px] animate-pulse bg-hairline/40 rounded-[2px]" />
        ) : curve.length > 1 ? (
          <AreaChart data={curve} positive={netPositive} height={300} />
        ) : (
          <div className="h-[300px] grid place-items-center text-[12px] text-muted-foreground">
            No equity history yet — the backend has not recorded portfolio snapshots.
          </div>
        )}
      </Panel>

      <LivePriceCard />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">

        <Panel title="Open Positions" className="lg:col-span-3">
          {status.isLoading ? (
            <SkeletonRows cols={7} />
          ) : status.isError ? (
            <ErrorState error={status.error} />
          ) : (
            <PositionsTable positions={s?.positions ?? []} />
          )}
        </Panel>

        <Panel
          title="Live Signals"
          className="lg:col-span-2"
          right={<span className="label-xs">polls every 20s</span>}
        >
          {screener.isLoading ? (
            <SkeletonRows cols={4} />
          ) : screener.isError ? (
            <ErrorState error={screener.error} />
          ) : (
            <SignalsFeed rows={screener.data ?? []} />
          )}
        </Panel>
      </div>

      <Panel title="Screener / Watchlist">
        {screener.isLoading ? (
          <SkeletonRows cols={8} />
        ) : screener.isError ? (
          <ErrorState error={screener.error} />
        ) : (
          <ScreenerTable rows={screener.data ?? []} />
        )}
      </Panel>
    </div>
  );
}
