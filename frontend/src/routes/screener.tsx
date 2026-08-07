import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { ErrorState, Panel, SkeletonRows, Tag } from "@/components/kit";
import { ScreenerTable } from "@/components/ScreenerTable";
import { screenerQuery } from "@/lib/queries";
import { fetchDiscoverLongTerm } from "@/lib/api";

export const Route = createFileRoute("/screener")({
  head: () => ({
    meta: [
      { title: "Screener & Watchlist — NSE Quant Desk" },
      {
        name: "description",
        content:
          "Sortable NSE screener with live LTP, RSI, volume, signals and backtested strategy returns.",
      },
      { property: "og:title", content: "Screener & Watchlist — NSE Quant Desk" },
      {
        property: "og:description",
        content: "Sortable NSE screener with live prices, RSI, signals and backtested returns.",
      },
    ],
  }),
  component: Screener,
});

function Screener() {
  const screener = useQuery(screenerQuery());
  const longTerm = useQuery({
    queryKey: ["discover", "long-term"],
    queryFn: () => fetchDiscoverLongTerm(),
    retry: 1,
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold tracking-tight">Screener / Watchlist</h1>
        <Tag tone="accent" title="5-year backtest across 15 NSE large-cap stocks">
          p=0.0008 · statistically validated
        </Tag>
      </div>

      <Panel title="Live Watchlist" right={<span className="label-xs">polls every 20s</span>}>
        {screener.isLoading ? (
          <SkeletonRows cols={8} />
        ) : screener.isError ? (
          <ErrorState error={screener.error} />
        ) : (
          <ScreenerTable rows={screener.data ?? []} />
        )}
      </Panel>

      <Panel title="Long-Term Discovery Ranking">
        {longTerm.isLoading ? (
          <SkeletonRows cols={8} />
        ) : longTerm.isError ? (
          <ErrorState error={longTerm.error} />
        ) : (
          <ScreenerTable rows={longTerm.data ?? []} />
        )}
      </Panel>
    </div>
  );
}
