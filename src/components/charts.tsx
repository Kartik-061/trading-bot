import { useEffect, useRef } from "react";

import type { Candle } from "@/lib/api";

type SeriesLike = { setData: (d: unknown[]) => void };
type ChartLike = {
  addSeries: (t: unknown, o?: Record<string, unknown>, p?: number) => SeriesLike;
  applyOptions: (o: Record<string, unknown>) => void;
  timeScale: () => { fitContent: () => void };
  remove: () => void;
  priceScale: (id: string) => { applyOptions: (o: Record<string, unknown>) => void };
};

const GRID = "#1F242C";
const TEXT = "#8A8F98";
const BG = "transparent";

function baseOptions(width: number, height: number) {
  return {
    width,
    height,
    layout: {
      background: { color: BG },
      textColor: TEXT,
      fontFamily: "JetBrains Mono, ui-monospace, monospace",
      fontSize: 10,
      attributionLogo: false,
    },
    grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
    rightPriceScale: { borderColor: GRID },
    timeScale: { borderColor: GRID, timeVisible: true, secondsVisible: false },
    crosshair: { vertLine: { color: TEXT, width: 1 }, horzLine: { color: TEXT, width: 1 } },
  } as Record<string, unknown>;
}

export function AreaChart({
  data,
  positive,
  height = 300,
}: {
  data: { time: string; value: number }[];
  positive: boolean;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let chart: ChartLike | null = null;
    let ro: ResizeObserver | null = null;
    let cancelled = false;

    void (async () => {
      const lc = await import("lightweight-charts");
      if (cancelled || !ref.current) return;
      chart = lc.createChart(
        ref.current,
        baseOptions(ref.current.clientWidth, height),
      ) as unknown as ChartLike;
      const color = positive ? "#00C853" : "#FF3B30";
      const series = chart.addSeries(lc.AreaSeries, {
        lineColor: color,
        lineWidth: 2,
        topColor: positive ? "rgba(0,200,83,0.25)" : "rgba(255,59,48,0.25)",
        bottomColor: "rgba(0,0,0,0)",
        priceLineVisible: false,
      });
      const points = data
        .map((d) => ({ time: Math.floor(new Date(d.time).getTime() / 1000), value: d.value }))
        .filter((d) => Number.isFinite(d.time) && Number.isFinite(d.value))
        .sort((a, b) => a.time - b.time);
      const dedup = points.filter((p, i) => i === 0 || p.time !== points[i - 1]!.time);
      series.setData(dedup);
      chart.timeScale().fitContent();

      ro = new ResizeObserver(() => {
        if (ref.current && chart) chart.applyOptions({ width: ref.current.clientWidth });
      });
      ro.observe(ref.current);
    })();

    return () => {
      cancelled = true;
      ro?.disconnect();
      chart?.remove();
    };
  }, [data, positive, height]);

  return <div ref={ref} style={{ height }} className="w-full" />;
}

export function CandleChart({ data, height = 380 }: { data: Candle[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let chart: ChartLike | null = null;
    let ro: ResizeObserver | null = null;
    let cancelled = false;

    void (async () => {
      const lc = await import("lightweight-charts");
      if (cancelled || !ref.current) return;
      chart = lc.createChart(
        ref.current,
        baseOptions(ref.current.clientWidth, height),
      ) as unknown as ChartLike;

      const candles = chart.addSeries(lc.CandlestickSeries, {
        upColor: "#00C853",
        downColor: "#FF3B30",
        borderUpColor: "#00C853",
        borderDownColor: "#FF3B30",
        wickUpColor: "#00C853",
        wickDownColor: "#FF3B30",
      });
      candles.setData(data);

      const volume = chart.addSeries(lc.HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      volume.setData(
        data.map((c) => ({
          time: c.time,
          value: c.volume,
          color: c.close >= c.open ? "rgba(0,200,83,0.35)" : "rgba(255,59,48,0.35)",
        })),
      );

      chart.timeScale().fitContent();
      ro = new ResizeObserver(() => {
        if (ref.current && chart) chart.applyOptions({ width: ref.current.clientWidth });
      });
      ro.observe(ref.current);
    })();

    return () => {
      cancelled = true;
      ro?.disconnect();
      chart?.remove();
    };
  }, [data, height]);

  return <div ref={ref} style={{ height }} className="w-full" />;
}
