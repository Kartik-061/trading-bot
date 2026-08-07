import type { Position } from "@/lib/api";
import { inr, num, pct, toneClass } from "@/lib/format";
import { EmptyRow, Sparkline } from "@/components/kit";
import { cn } from "@/lib/utils";

export function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions.length)
    return <EmptyRow>No open positions. The bot holds cash until a signal triggers.</EmptyRow>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border">
            {["Symbol", "Qty", "Avg Price", "LTP", "P&L ₹", "P&L %", "Trend"].map((h, i) => (
              <th
                key={h}
                className={cn("label-xs px-3 py-1.5 font-medium", i === 0 ? "text-left" : "text-right")}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.symbol} className="border-b border-border/60 hover:bg-secondary/50">
              <td className="px-3 py-1.5 font-medium">{p.symbol}</td>
              <td className="num px-3 py-1.5 text-right">{p.quantity}</td>
              <td className="num px-3 py-1.5 text-right">{num(p.avg_price)}</td>
              <td className="num px-3 py-1.5 text-right">{num(p.ltp)}</td>
              <td className={cn("num px-3 py-1.5 text-right font-medium", toneClass(p.pnl))}>
                {inr(p.pnl)}
              </td>
              <td className={cn("num px-3 py-1.5 text-right font-medium", toneClass(p.pnl_pct))}>
                {pct(p.pnl_pct)}
              </td>
              <td className="px-3 py-1.5">
                <div className="flex justify-end">
                  <Sparkline points={p.history ?? []} tone={p.pnl} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
