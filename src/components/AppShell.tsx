import { Link, useRouterState } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import {
  Activity,
  BarChart3,
  FlaskConical,
  LayoutDashboard,
  ListFilter,
  Receipt,
  Search,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { botStatusQuery } from "@/lib/queries";
import { inr, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/live-bot", label: "Live Bot", icon: Activity },
  { to: "/research", label: "Research", icon: Search },
  { to: "/backtest", label: "Backtest Lab", icon: FlaskConical },
  { to: "/screener", label: "Screener", icon: ListFilter },
  { to: "/trades", label: "Trade History", icon: Receipt },
  { to: "/strategy-stats", label: "Strategy Stats", icon: BarChart3 },
] as const;


export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { data, isError } = useQuery(botStatusQuery());
  const [q, setQ] = useState("");

  const marketOpen = data?.market_open ?? false;
  const dayPnl = data?.day_pnl ?? 0;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="fixed inset-x-0 top-0 z-30 h-12 border-b border-border bg-surface flex items-center gap-4 px-3">
        <div className="flex items-center gap-3 w-[210px] shrink-0">
          <Link to="/" className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-[3px] bg-primary text-[11px] font-bold text-primary-foreground">
              N
            </span>
            <span className="text-[13px] font-semibold tracking-tight">NSE Quant Desk</span>
          </Link>
        </div>

        <div
          className={cn(
            "flex items-center gap-1.5 border rounded-[2px] px-2 py-[3px] text-[10px] font-medium",
            marketOpen ? "border-gain/40 text-gain bg-gain/10" : "border-border text-muted-foreground",
          )}
        >
          <span
            className={cn("h-1.5 w-1.5 rounded-full", marketOpen ? "bg-gain" : "bg-muted-foreground")}
          />
          {isError ? "Status unavailable" : marketOpen ? "Market Open" : "Market Closed"}
        </div>

        <div className="flex-1 flex justify-center">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search symbol (e.g. RELIANCE)"
              className="num h-7 w-full border border-border bg-background rounded-[2px] pl-7 pr-2 text-[12px] placeholder:font-sans placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>
        </div>

        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right">
            <div className="label-xs">Portfolio</div>
            <div className="num text-[15px] font-semibold leading-5">
              {data ? inr(data.portfolio_value, 0) : "—"}
            </div>
          </div>
          <div className="text-right">
            <div className="label-xs">Today</div>
            <div
              className={cn(
                "num flex items-center gap-1 text-[15px] font-semibold leading-5",
                dayPnl >= 0 ? "text-gain" : "text-loss",
              )}
            >
              {dayPnl >= 0 ? (
                <TrendingUp className="h-3.5 w-3.5" />
              ) : (
                <TrendingDown className="h-3.5 w-3.5" />
              )}
              {data ? `${inr(data.day_pnl, 0)} (${pct(data.day_pnl_pct)})` : "—"}
            </div>
          </div>
          <span className="border border-border rounded-[2px] px-1.5 py-[2px] text-[10px] text-muted-foreground">
            PAPER TRADING
          </span>
        </div>
      </header>

      <aside className="fixed left-0 top-12 bottom-0 z-20 w-[210px] border-r border-border bg-sidebar py-2">
        <nav className="flex flex-col">
          {NAV.map((item) => {
            const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 text-[12.5px] border-l-2",
                  active
                    ? "border-primary bg-secondary text-foreground font-medium"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50",
                )}
              >
                <item.icon className="h-3.5 w-3.5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 mx-3 border-t border-border pt-3 text-[10px] leading-4 text-muted-foreground">
          Mean-reversion strategy validated at p=0.0008 across 15 NSE large-cap stocks, 5-year
          backtest. Paper trading only — no live capital is connected.
        </div>
      </aside>

      <main className="pt-12 pl-[210px]">
        <div className="p-3">{children}</div>
      </main>
    </div>
  );
}
