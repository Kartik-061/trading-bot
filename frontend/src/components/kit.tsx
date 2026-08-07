import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import { toneClass } from "@/lib/format";
import type { Signal } from "@/lib/api";

export function Panel({
  title,
  right,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn("border border-border bg-surface rounded-[3px] flex flex-col min-w-0", className)}
    >
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-3 h-9 shrink-0">
          <h2 className="label-xs text-foreground/80">{title}</h2>
          {right}
        </header>
      )}
      <div className={cn("min-w-0", bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  sub,
  tone,
  loading,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: number | null;
  loading?: boolean;
}) {
  return (
    <div className="border border-border bg-surface rounded-[3px] px-3 py-2.5 min-w-0">
      <div className="label-xs">{label}</div>
      {loading ? (
        <div className="mt-1.5 h-6 w-24 animate-pulse bg-hairline rounded-[2px]" />
      ) : (
        <div className={cn("num mt-1 text-[22px] leading-7 font-semibold truncate", toneClass(tone))}>
          {value}
        </div>
      )}
      {sub !== undefined && !loading && (
        <div className="num mt-0.5 text-[11px] text-muted-foreground truncate">{sub}</div>
      )}
    </div>
  );
}

const signalStyles: Record<Signal, string> = {
  BUY: "text-gain border-gain/40 bg-gain/10",
  SELL: "text-loss border-loss/40 bg-loss/10",
  HOLD: "text-muted-foreground border-border bg-secondary",
  MARKET_CLOSED: "text-muted-foreground border-border bg-transparent",
};

export function SignalBadge({ signal }: { signal: Signal }) {
  return (
    <span
      className={cn(
        "inline-flex items-center border rounded-[2px] px-1.5 py-[1px] text-[10px] font-semibold tracking-wide",
        signalStyles[signal],
      )}
    >
      {signal === "MARKET_CLOSED" ? "CLOSED" : signal}
    </span>
  );
}

export function Tag({
  children,
  tone = "muted",
  title,
}: {
  children: ReactNode;
  tone?: "muted" | "gain" | "loss" | "accent";
  title?: string;
}) {
  const map = {
    muted: "text-muted-foreground border-border",
    gain: "text-gain border-gain/40 bg-gain/10",
    loss: "text-loss border-loss/40 bg-loss/10",
    accent: "text-primary border-primary/40 bg-primary/10",
  } as const;
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 border rounded-[2px] px-1.5 py-[1px] text-[10px] font-medium whitespace-nowrap",
        map[tone],
      )}
    >
      {children}
    </span>
  );
}

export function ErrorState({ error, compact }: { error: unknown; compact?: boolean }) {
  const msg = error instanceof Error ? error.message : "Unexpected error";
  return (
    <div
      className={cn(
        "flex items-start gap-2 border border-loss/40 bg-loss/5 rounded-[3px] text-[12px] text-loss",
        compact ? "px-2.5 py-2" : "px-3 py-3 m-3",
      )}
    >
      <AlertTriangle className="h-3.5 w-3.5 mt-[1px] shrink-0" />
      <span className="min-w-0">{msg}</span>
    </div>
  );
}

export function SkeletonRows({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="p-3 space-y-2">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
          {Array.from({ length: cols }).map((__, c) => (
            <div key={c} className="h-3.5 animate-pulse bg-hairline rounded-[2px]" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyRow({ children }: { children: ReactNode }) {
  return <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">{children}</div>;
}

export function Sparkline({ points, tone }: { points: number[]; tone: number }) {
  const w = 64;
  const h = 18;
  if (!points || points.length < 2) {
    return <div className="h-[18px] w-16 border-b border-dashed border-hairline" />;
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const color = tone >= 0 ? "var(--gain)" : "var(--loss)";
  return (
    <svg width={w} height={h} className="block overflow-visible">
      <path d={d} fill="none" stroke={color} strokeWidth={1.25} />
    </svg>
  );
}
