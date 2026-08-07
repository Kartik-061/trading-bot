import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { AreaChart } from "@/components/charts";
import { ErrorState, Panel } from "@/components/kit";
import { botStatusQuery, screenerQuery, tickCandlesQuery } from "@/lib/queries";
import { inr, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

const DEFAULT_SYMBOL = "RELIANCE";

export function LivePriceCard() {
  const screener = useQuery(screenerQuery());
  const status = useQuery(botStatusQuery());
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);

  const symbols = useMemo(() => {
    const list = [
      ...(status.data?.symbols ?? []),
      ...(screener.data ?? []).map((r) => r.symbol),
      DEFAULT_SYMBOL,
    ].filter((x) => x && x !== "—");
    return Array.from(new Set(list)).sort();
  }, [screener.data, status.data]);

  useEffect(() => {
    if (symbols.length && !symbols.includes(symbol)) setSymbol(symbols[0]!);
  }, [symbols, symbol]);

  const candles = useQuery(tickCandlesQuery(symbol));

  const series = useMemo(
    () =>
      (candles.data ?? []).map((c) => ({
        time: new Date(c.time * 1000).toISOString(),
        value: c.close,
      })),
    [candles.data],
  );

  const first = series[0]?.value ?? 0;
  const last = series.at(-1)?.value ?? 0;
  const changePct = first ? ((last - first) / first) * 100 : 0;
  const tick = status.data?.interval_seconds ?? 60;

  return (
    <Panel
      title="Live Price"
      right={
        <div className="flex items-center gap-2">
          {series.length > 1 && (
            <span className="num text-[11px]">
              <span className="text-foreground font-semibold">{inr(last)}</span>{" "}
              <span className={cn(changePct >= 0 ? "text-gain" : "text-loss")}>
                {pct(changePct)}
              </span>
            </span>
          )}
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="num h-6 border border-border bg-background rounded-[2px] px-1.5 text-[11px] focus:border-primary focus:outline-none"
          >
            {symbols.map((sym) => (
              <option key={sym} value={sym}>
                {sym}
              </option>
            ))}
          </select>
        </div>
      }
      bodyClassName="p-2"
    >
      {candles.isLoading ? (
        <div className="h-[240px] animate-pulse bg-hairline/40 rounded-[2px]" />
      ) : candles.isError ? (
        <ErrorState error={candles.error} compact />
      ) : series.length > 1 ? (
        <AreaChart data={series} positive={changePct >= 0} height={240} />
      ) : (
        <div className="h-[240px] grid place-items-center px-4 text-center text-[12px] text-muted-foreground">
          No ticks recorded yet — the bot logs a new price every {tick}s while running.
        </div>
      )}
      <div className="label-xs mt-1.5 px-1">
        Updates every 30s · reflects bot tick interval, not true real-time.
      </div>
    </Panel>
  );
}
