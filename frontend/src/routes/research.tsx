import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";

import { CandleChart } from "@/components/charts";
import { ErrorState, Panel, StatCard, Tag } from "@/components/kit";
import { liveQuoteQuery, stockChartQuery, stockInfoQuery } from "@/lib/queries";
import { inr, inrCompact, num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/research")({
  head: () => ({
    meta: [
      { title: "Research — NSE Stock Charts & Fundamentals" },
      {
        name: "description",
        content:
          "Search any NSE symbol for daily candlestick charts, live price and fundamentals: sector, market cap, P/E and 52-week range.",
      },
      { property: "og:title", content: "Research — NSE Stock Charts & Fundamentals" },
      {
        property: "og:description",
        content:
          "Daily candlestick charts, live prices and fundamentals for any NSE symbol. Research only — not investment advice.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Research,
});

const PERIODS = ["1mo", "3mo", "1y", "5y"] as const;
type Period = (typeof PERIODS)[number];

function Research() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [input, setInput] = useState("RELIANCE");
  const [period, setPeriod] = useState<Period>("3mo");

  const chart = useQuery(stockChartQuery(symbol, period));
  const quote = useQuery(liveQuoteQuery(symbol));
  const info = useQuery(stockInfoQuery(symbol));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = input.trim().toUpperCase();
    if (v) setSymbol(v);
  };

  const q = quote.data;
  const i = info.data;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-[15px] font-semibold tracking-tight">Research</h1>
        <Tag>Research only — not investment advice.</Tag>
      </div>

      <form onSubmit={submit} className="flex items-center gap-2">
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Search any NSE symbol (e.g. TCS)"
            className="num h-7 w-full border border-border bg-background rounded-[2px] pl-7 pr-2 text-[12px] uppercase placeholder:font-sans placeholder:normal-case placeholder:text-muted-foreground focus:border-primary focus:outline-none"
          />
        </div>
        <button
          type="submit"
          className="h-7 border border-primary/50 bg-primary/10 text-primary rounded-[2px] px-3 text-[11px] font-medium hover:bg-primary/20"
        >
          Load
        </button>
      </form>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatCard
          label={`${symbol} — Last Price`}
          value={inr(q?.price)}
          sub={q?.updated_at ?? "live quote"}
          loading={quote.isLoading}
        />
        <StatCard
          label="Change"
          value={q?.change === null || q?.change === undefined ? "—" : inr(q.change)}
          sub={pct(q?.change_pct)}
          tone={q?.change_pct ?? 0}
          loading={quote.isLoading}
        />
        <StatCard
          label="Previous Close"
          value={inr(q?.previous_close)}
          loading={quote.isLoading}
        />
        <StatCard label="Sector" value={i?.sector ?? "—"} sub={i?.industry ?? undefined} loading={info.isLoading} />
      </div>

      {quote.isError && <ErrorState error={quote.error} compact />}

      <Panel
        title={`${symbol} — Daily Candles`}
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
        {chart.isLoading ? (
          <div className="h-[380px] animate-pulse bg-hairline/40 rounded-[2px]" />
        ) : chart.isError ? (
          <ErrorState error={chart.error} compact />
        ) : (chart.data?.length ?? 0) > 1 ? (
          <CandleChart data={chart.data ?? []} height={380} />
        ) : (
          <div className="h-[380px] grid place-items-center text-[12px] text-muted-foreground">
            No daily OHLC returned for {symbol} over {period}.
          </div>
        )}
      </Panel>

      <Panel title="Fundamentals">
        {info.isLoading ? (
          <div className="p-3 grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, k) => (
              <div key={k} className="h-8 animate-pulse bg-hairline rounded-[2px]" />
            ))}
          </div>
        ) : info.isError ? (
          <ErrorState error={info.error} />
        ) : (
          <div className="p-3 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-3">
            <Field label="Company" value={i?.name ?? symbol} mono={false} />
            <Field label="Sector" value={i?.sector ?? "—"} mono={false} />
            <Field label="Market Cap" value={inrCompact(i?.market_cap)} />
            <Field label="P/E Ratio" value={i?.pe_ratio === null || i?.pe_ratio === undefined ? "—" : num(i.pe_ratio)} />
            <Field label="52-Week High" value={inr(i?.week52_high)} />
            <Field label="52-Week Low" value={inr(i?.week52_low)} />
            <Field
              label="52-Week Range"
              value={
                i?.week52_low !== null && i?.week52_low !== undefined && i?.week52_high
                  ? `${inr(i.week52_low, 0)} – ${inr(i.week52_high, 0)}`
                  : "—"
              }
            />
            <Field label="Industry" value={i?.industry ?? "—"} mono={false} />
          </div>
        )}
        <div className="label-xs border-t border-border px-3 py-2">
          Research only — not investment advice.
        </div>
      </Panel>
    </div>
  );
}

function Field({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="label-xs">{label}</div>
      <div className={cn("mt-0.5 text-[13px] truncate", mono && "num")}>{value}</div>
    </div>
  );
}
