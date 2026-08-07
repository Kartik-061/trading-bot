import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";

import type { ScreenerRow } from "@/lib/api";
import { compactNum, num, pct, toneClass } from "@/lib/format";
import { EmptyRow, SignalBadge, Tag } from "@/components/kit";
import { cn } from "@/lib/utils";

type Key = keyof Pick<
  ScreenerRow,
  "symbol" | "ltp" | "change_pct" | "signal" | "rsi" | "volume" | "backtested_return_pct"
>;

const COLUMNS: { key: Key; label: string; align: "left" | "right" }[] = [
  { key: "symbol", label: "Symbol", align: "left" },
  { key: "ltp", label: "LTP", align: "right" },
  { key: "change_pct", label: "Change %", align: "right" },
  { key: "signal", label: "Signal", align: "left" },
  { key: "rsi", label: "RSI", align: "right" },
  { key: "volume", label: "Volume", align: "right" },
  { key: "backtested_return_pct", label: "Backtested Return %", align: "right" },
];

export function ScreenerTable({ rows }: { rows: ScreenerRow[] }) {
  const [sortKey, setSortKey] = useState<Key>("change_pct");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "string" || typeof bv === "string") {
        return String(av ?? "").localeCompare(String(bv ?? "")) * (dir === "asc" ? 1 : -1);
      }
      const an = av ?? Number.NEGATIVE_INFINITY;
      const bn = bv ?? Number.NEGATIVE_INFINITY;
      return (Number(an) - Number(bn)) * (dir === "asc" ? 1 : -1);
    });
    return copy;
  }, [rows, sortKey, dir]);

  const toggle = (k: Key) => {
    if (k === sortKey) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSortKey(k);
      setDir("desc");
    }
  };

  if (!rows.length) return <EmptyRow>Screener returned no rows.</EmptyRow>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border">
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                onClick={() => toggle(c.key)}
                className={cn(
                  "label-xs px-3 py-1.5 font-medium cursor-pointer select-none hover:text-foreground",
                  c.align === "left" ? "text-left" : "text-right",
                )}
              >
                <span className="inline-flex items-center gap-1">
                  {c.label}
                  {sortKey === c.key &&
                    (dir === "asc" ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : (
                      <ArrowDown className="h-3 w-3" />
                    ))}
                </span>
              </th>
            ))}
            <th className="label-xs px-3 py-1.5 text-right font-medium">Validation</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.symbol} className="border-b border-border/60 hover:bg-secondary/50">
              <td className="px-3 py-1.5 font-medium">{r.symbol}</td>
              <td className="num px-3 py-1.5 text-right">{num(r.ltp)}</td>
              <td className={cn("num px-3 py-1.5 text-right", toneClass(r.change_pct))}>
                {pct(r.change_pct)}
              </td>
              <td className="px-3 py-1.5">
                <SignalBadge signal={r.signal} />
              </td>
              <td className="num px-3 py-1.5 text-right">{r.rsi === null ? "—" : num(r.rsi, 1)}</td>
              <td className="num px-3 py-1.5 text-right text-muted-foreground">
                {compactNum(r.volume)}
              </td>
              <td
                className={cn("num px-3 py-1.5 text-right", toneClass(r.backtested_return_pct))}
              >
                {pct(r.backtested_return_pct)}
              </td>
              <td className="px-3 py-1.5 text-right">
                {r.validated ? (
                  <Tag
                    tone="accent"
                    title={`Statistically significant at p<0.05${
                      r.p_value !== null ? ` (p=${r.p_value.toPrecision(2)})` : ""
                    } — 5-year backtest across 15 NSE large-cap stocks`}
                  >
                    Validated
                    {r.p_value !== null && (
                      <span className="num opacity-70">p={r.p_value.toPrecision(2)}</span>
                    )}
                  </Tag>
                ) : (
                  <span className="text-[10px] text-muted-foreground">not in test set</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
