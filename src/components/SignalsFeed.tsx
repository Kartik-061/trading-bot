import type { ScreenerRow } from "@/lib/api";
import { pct, timeAgo, toneClass } from "@/lib/format";
import { EmptyRow, SignalBadge } from "@/components/kit";
import { cn } from "@/lib/utils";

export function SignalsFeed({ rows }: { rows: ScreenerRow[] }) {
  if (!rows.length) return <EmptyRow>No watchlist symbols returned by the screener.</EmptyRow>;

  return (
    <ul className="max-h-[420px] overflow-y-auto divide-y divide-border/60">
      {rows.map((r) => (
        <li key={r.symbol} className="flex items-center gap-3 px-3 py-2 hover:bg-secondary/50">
          <div className="w-24 shrink-0 text-[12px] font-medium truncate">{r.symbol}</div>
          <div className="w-20 shrink-0">
            <SignalBadge signal={r.signal} />
          </div>
          <div className={cn("num flex-1 text-right text-[12px]", toneClass(r.momentum_pct))}>
            {pct(r.momentum_pct)}
          </div>
          <div className="num w-16 shrink-0 text-right text-[10px] text-muted-foreground">
            {timeAgo(r.updated_at)}
          </div>
        </li>
      ))}
    </ul>
  );
}
