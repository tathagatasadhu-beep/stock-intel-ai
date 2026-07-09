"use client";

import { useEffect, useRef, useState } from "react";
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import { CandleOut, FibonacciOut, TechnicalsSeries } from "@/lib/api";

type Props = {
  candles: CandleOut[];
  series: TechnicalsSeries | null;
  fibonacci: FibonacciOut | null;
};

const FIB_COLORS: Record<string, string> = {
  level_0: "#5b6272",
  level_236: "#f59e0b",
  level_382: "#eab308",
  level_500: "#3b82f6",
  level_618: "#22c55e",
  level_786: "#ef4444",
  level_100: "#5b6272",
};

export function CandlestickChart({ candles, series, fibonacci }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [overlays, setOverlays] = useState({ sma20: true, sma50: true, sma200: false, bollinger: false, fibonacci: true, volume: true });

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    let disposed = false;
    let chart: IChartApi | null = null;

    import("lightweight-charts").then(({ createChart, ColorType, CandlestickSeries, HistogramSeries, LineSeries }) => {
      if (disposed || !containerRef.current) return;

      chart = createChart(containerRef.current, {
        layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8b93a7" },
        grid: { vertLines: { color: "#1c202c" }, horzLines: { color: "#1c202c" } },
        rightPriceScale: { borderColor: "#262b3a" },
        timeScale: { borderColor: "#262b3a" },
        width: containerRef.current.clientWidth,
        height: 480,
      });
      chartRef.current = chart;

      const candleSeries: ISeriesApi<"Candlestick"> = chart.addSeries(CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });
      const candleData = candles.map((c) => ({
        time: (new Date(c.date).getTime() / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      candleSeries.setData(candleData);

      if (overlays.volume) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "volume" },
          priceScaleId: "volume",
        });
        chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
        volumeSeries.setData(
          candles.map((c) => ({
            time: (new Date(c.date).getTime() / 1000) as UTCTimestamp,
            value: c.volume,
            color: c.close >= c.open ? "#22c55e55" : "#ef444455",
          }))
        );
      }

      if (series) {
        const lineFor = (values: (number | null)[], color: string, title: string) => {
          const line = chart!.addSeries(LineSeries, { color, lineWidth: 1, title, priceLineVisible: false, lastValueVisible: false });
          line.setData(
            series.dates
              .map((d, i) => ({ time: (new Date(d).getTime() / 1000) as UTCTimestamp, value: values[i] }))
              .filter((p): p is { time: UTCTimestamp; value: number } => p.value !== null)
          );
          return line;
        };

        if (overlays.sma20) lineFor(series.sma20, "#3b82f6", "SMA20");
        if (overlays.sma50) lineFor(series.sma50, "#f59e0b", "SMA50");
        if (overlays.sma200) lineFor(series.sma200, "#a855f7", "SMA200");
        if (overlays.bollinger) {
          lineFor(series.bollinger_upper, "#5b627299", "BB Upper");
          lineFor(series.bollinger_lower, "#5b627299", "BB Lower");
        }
      }

      if (overlays.fibonacci && fibonacci) {
        (Object.keys(FIB_COLORS) as (keyof FibonacciOut)[]).forEach((key) => {
          const value = fibonacci[key];
          if (typeof value !== "number") return;
          candleSeries.createPriceLine({
            price: value,
            color: FIB_COLORS[key],
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: key.replace("level_", "") + "%",
          });
        });
      }

      chart.timeScale().fitContent();

      const handleResize = () => {
        if (containerRef.current && chart) chart.applyOptions({ width: containerRef.current.clientWidth });
      };
      window.addEventListener("resize", handleResize);
      return () => window.removeEventListener("resize", handleResize);
    });

    return () => {
      disposed = true;
      chart?.remove();
      chartRef.current = null;
    };
  }, [candles, series, fibonacci, overlays]);

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-3 text-xs text-text-muted">
        {([
          ["sma20", "SMA 20", "#3b82f6"],
          ["sma50", "SMA 50", "#f59e0b"],
          ["sma200", "SMA 200", "#a855f7"],
          ["bollinger", "Bollinger Bands", "#5b6272"],
          ["fibonacci", "Fibonacci", "#22c55e"],
          ["volume", "Volume", "#8b93a7"],
        ] as const).map(([key, label, color]) => (
          <label key={key} className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={overlays[key]}
              onChange={(e) => setOverlays((prev) => ({ ...prev, [key]: e.target.checked }))}
              className="accent-accent"
            />
            <span style={{ color }}>{label}</span>
          </label>
        ))}
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
