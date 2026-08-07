import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Play, Square } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, Panel, SkeletonRows, Tag } from "@/components/kit";
import { PositionsTable } from "@/components/PositionsTable";
import { SignalsFeed } from "@/components/SignalsFeed";
import { botStatusQuery, screenerQuery } from "@/lib/queries";
import { startBot, stopBot } from "@/lib/api";
import { duration, stamp } from "@/lib/format";
import { STRATEGIES } from "@/lib/strategies";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/live-bot")({
  head: () => ({
    meta: [
      { title: "Live Bot — NSE Quant Desk" },
      {
        name: "description",
        content:
          "Start, stop and monitor the NSE mean-reversion paper-trading bot with live positions and signals.",
      },
      { property: "og:title", content: "Live Bot — NSE Quant Desk" },
      {
        property: "og:description",
        content: "Start, stop and monitor the NSE paper-trading bot with live positions and signals.",
      },
    ],
  }),
  component: LiveBot,
});

const fieldCls =
  "num h-7 w-full border border-border bg-background rounded-[2px] px-2 text-[12px] focus:border-primary focus:outline-none";

function LiveBot() {
  const qc = useQueryClient();
  const status = useQuery(botStatusQuery());
  const screener = useQuery(screenerQuery());

  const [strategy, setStrategy] = useState<string>("mean_reversion");
  const [symbols, setSymbols] = useState("RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK");
  const [interval, setInterval] = useState("60");

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["bot", "status"] });

  const start = useMutation({
    mutationFn: () =>
      startBot({
        strategy,
        symbols: symbols
          .split(",")
          .map((x) => x.trim().toUpperCase())
          .filter(Boolean),
        interval_seconds: Number(interval) || 60,
      }),
    onSuccess: () => {
      toast.success("Bot start requested");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const stop = useMutation({
    mutationFn: () => stopBot(),
    onSuccess: () => {
      toast.success("Bot stop requested");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const s = status.data;
  const running = s?.running ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold tracking-tight">Live Bot</h1>
        <Tag>Paper trading · no live capital connected</Tag>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <Panel title="Bot Control" className="lg:col-span-3" bodyClassName="p-3 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="label-xs block mb-1">Strategy</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className={fieldCls}
              >
                {STRATEGIES.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="label-xs block mb-1">Symbols (comma separated)</label>
              <input
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
                className={fieldCls}
              />
            </div>
            <div>
              <label className="label-xs block mb-1">Tick Interval (seconds)</label>
              <input
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
                inputMode="numeric"
                className={fieldCls}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => start.mutate()}
              disabled={running || start.isPending}
              className="inline-flex items-center gap-1.5 h-7 px-3 rounded-[2px] bg-primary text-primary-foreground text-[12px] font-medium disabled:opacity-40"
            >
              <Play className="h-3 w-3" /> {start.isPending ? "Starting…" : "Start Bot"}
            </button>
            <button
              onClick={() => stop.mutate()}
              disabled={!running || stop.isPending}
              className="inline-flex items-center gap-1.5 h-7 px-3 rounded-[2px] border border-loss/50 text-loss text-[12px] font-medium disabled:opacity-40"
            >
              <Square className="h-3 w-3" /> {stop.isPending ? "Stopping…" : "Stop Bot"}
            </button>
          </div>
          {(start.error || stop.error) && (
            <ErrorState error={start.error ?? stop.error} compact />
          )}
        </Panel>

        <Panel title="Current Status" className="lg:col-span-2" bodyClassName="p-3">
          {status.isLoading ? (
            <SkeletonRows rows={4} cols={2} />
          ) : status.isError ? (
            <ErrorState error={status.error} compact />
          ) : (
            <dl className="grid grid-cols-2 gap-y-2.5 text-[12px]">
              <dt className="label-xs self-center">State</dt>
              <dd>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 border rounded-[2px] px-1.5 py-[1px] text-[10px] font-semibold",
                    running ? "border-gain/40 text-gain bg-gain/10" : "border-border text-muted-foreground",
                  )}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", running ? "bg-gain" : "bg-muted-foreground")} />
                  {running ? "RUNNING" : "STOPPED"}
                </span>
              </dd>
              <dt className="label-xs self-center">Session ID</dt>
              <dd className="num truncate">{s?.session_id ?? "—"}</dd>
              <dt className="label-xs self-center">Uptime</dt>
              <dd className="num">{duration(s?.uptime_seconds)}</dd>
              <dt className="label-xs self-center">Started</dt>
              <dd className="num">{stamp(s?.started_at)}</dd>
              <dt className="label-xs self-center">Strategy</dt>
              <dd className="num">{s?.strategy ?? "—"}</dd>
              <dt className="label-xs self-center">Market</dt>
              <dd className={cn("num", s?.market_open ? "text-gain" : "text-muted-foreground")}>
                {s?.market_open ? "OPEN" : "CLOSED"}
              </dd>
            </dl>
          )}
        </Panel>
      </div>

      <Panel title="Open Positions">
        {status.isLoading ? (
          <SkeletonRows cols={7} />
        ) : status.isError ? (
          <ErrorState error={status.error} />
        ) : (
          <PositionsTable positions={s?.positions ?? []} />
        )}
      </Panel>

      <Panel title="Live Signals" right={<span className="label-xs">polls every 20s</span>}>
        {screener.isLoading ? (
          <SkeletonRows cols={4} />
        ) : screener.isError ? (
          <ErrorState error={screener.error} />
        ) : (
          <SignalsFeed rows={screener.data ?? []} />
        )}
      </Panel>
    </div>
  );
}
