import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ErrorState, Panel, SkeletonRows, Tag } from "@/components/kit";
import { tradesQuery } from "@/lib/queries";
import { STRATEGIES } from "@/lib/strategies";
import { inr, num, stamp } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/trades")({
  head: () => ({
    meta: [
      { title: "Trade History — NSE Quant Desk" },
      {
        name: "description",
        content:
          "Complete paper-trading execution log with symbol, strategy and date filters for the NSE trading bot.",
      },
      { property: "og:title", content: "Trade History — NSE Quant Desk" },
      {
        property: "og:description",
        content: "Complete paper-trading execution log, filterable by symbol, strategy and date.",
      },
    ],
  }),
  component: TradeHistory,
});

const fieldCls =
  "num h-7 w-full border border-border bg-background rounded-[2px] px-2 text-[12px] focus:border-primary focus:outline-none";
const PAGE_SIZE = 25;

function TradeHistory() {
  const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);

  const query = useQuery(tradesQuery({ limit: 500 }));

  const filtered = useMemo(() => {
    const rows = query.data ?? [];
    return rows.filter((t) => {
      if (symbol && !t.symbol.toUpperCase().includes(symbol.toUpperCase())) return false;
      if (strategy && t.strategy !== strategy) return false;
      const ts = new Date(t.timestamp).getTime();
      if (from && Number.isFinite(ts) && ts < new Date(from).getTime()) return false;
      if (to && Number.isFinite(ts) && ts > new Date(to).getTime() + 86_400_000) return false;
      return true;
    });
  }, [query.data, symbol, strategy, from, to]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const rows = filtered.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold tracking-tight">Trade History</h1>
        <Tag>{filtered.length} executions</Tag>
      </div>

      <Panel title="Filters" bodyClassName="p-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="label-xs block mb-1">Symbol</label>
            <input
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value);
                setPage(0);
              }}
              placeholder="RELIANCE"
              className={fieldCls}
            />
          </div>
          <div>
            <label className="label-xs block mb-1">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => {
                setStrategy(e.target.value);
                setPage(0);
              }}
              className={fieldCls}
            >
              <option value="">All</option>
              {STRATEGIES.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label-xs block mb-1">From</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={fieldCls} />
          </div>
          <div>
            <label className="label-xs block mb-1">To</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={fieldCls} />
          </div>
        </div>
      </Panel>

      <Panel
        title="Executions"
        right={
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <button
              onClick={() => setPage(Math.max(0, current - 1))}
              disabled={current === 0}
              className="px-2 py-[2px] border border-border rounded-[2px] disabled:opacity-40"
            >
              Prev
            </button>
            <span className="num">
              {current + 1}/{pages}
            </span>
            <button
              onClick={() => setPage(Math.min(pages - 1, current + 1))}
              disabled={current >= pages - 1}
              className="px-2 py-[2px] border border-border rounded-[2px] disabled:opacity-40"
            >
              Next
            </button>
          </div>
        }
      >
        {query.isLoading ? (
          <SkeletonRows cols={9} />
        ) : query.isError ? (
          <ErrorState error={query.error} />
        ) : rows.length === 0 ? (
          <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">
            No trades match these filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-border">
                  {["Timestamp", "Symbol", "Side", "Qty", "Price", "Value", "Cash After", "Strategy", "Mode"].map(
                    (h, i) => (
                      <th
                        key={h}
                        className={cn(
                          "label-xs px-3 py-1.5 font-medium",
                          i >= 3 && i <= 6 ? "text-right" : "text-left",
                        )}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((t, i) => (
                  <tr key={`${t.timestamp}-${i}`} className="border-b border-border/60 hover:bg-secondary/50">
                    <td className="num px-3 py-1.5 text-muted-foreground">{stamp(t.timestamp)}</td>
                    <td className="px-3 py-1.5 font-medium">{t.symbol}</td>
                    <td
                      className={cn(
                        "px-3 py-1.5 font-medium",
                        t.side === "BUY" ? "text-gain" : t.side === "SELL" ? "text-loss" : "",
                      )}
                    >
                      {t.side}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{t.quantity}</td>
                    <td className="num px-3 py-1.5 text-right">{num(t.price)}</td>
                    <td className="num px-3 py-1.5 text-right">{inr(t.value, 0)}</td>
                    <td className="num px-3 py-1.5 text-right text-muted-foreground">
                      {t.cash_after === null ? "—" : inr(t.cash_after, 0)}
                    </td>
                    <td className="num px-3 py-1.5 text-muted-foreground">{t.strategy ?? "—"}</td>
                    <td className="px-3 py-1.5">
                      <span
                        className={cn(
                          "border rounded-[2px] px-1.5 py-[1px] text-[10px] font-semibold",
                          t.mode === "LIVE"
                            ? "border-loss/50 text-loss"
                            : "border-border text-muted-foreground",
                        )}
                      >
                        {t.mode}
                      </span>
                    </td>
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
