"use client";

import { useEffect, useRef } from "react";
import type { IChartApi, UTCTimestamp } from "lightweight-charts";
import { TechnicalsSeries } from "@/lib/api";

function toPoints(dates: string[], values: (number | null)[]) {
  return dates
    .map((d, i) => ({ time: (new Date(d).getTime() / 1000) as UTCTimestamp, value: values[i] }))
    .filter((p): p is { time: UTCTimestamp; value: number } => p.value !== null);
}

export function IndicatorPanel({ series }: { series: TechnicalsSeries }) {
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const chartsRef = useRef<IChartApi[]>([]);

  useEffect(() => {
    if (!rsiRef.current || !macdRef.current) return;
    let disposed = false;

    import("lightweight-charts").then(({ createChart, ColorType, LineSeries, HistogramSeries }) => {
      if (disposed || !rsiRef.current || !macdRef.current) return;

      const baseOptions = {
        layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8b93a7" },
        grid: { vertLines: { color: "#1c202c" }, horzLines: { color: "#1c202c" } },
        rightPriceScale: { borderColor: "#262b3a" },
        timeScale: { borderColor: "#262b3a" },
        height: 140,
      };

      const rsiChart = createChart(rsiRef.current, { ...baseOptions, width: rsiRef.current.clientWidth });
      const rsiLine = rsiChart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 2, priceLineVisible: false });
      rsiLine.setData(toPoints(series.dates, series.rsi14));
      rsiLine.createPriceLine({ price: 70, color: "#ef444488", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "70" });
      rsiLine.createPriceLine({ price: 30, color: "#22c55e88", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "30" });

      const macdChart = createChart(macdRef.current, { ...baseOptions, width: macdRef.current.clientWidth });
      const histSeries = macdChart.addSeries(HistogramSeries, { priceLineVisible: false });
      histSeries.setData(
        series.dates
          .map((d, i) => ({
            time: (new Date(d).getTime() / 1000) as UTCTimestamp,
            value: series.macd_hist[i],
            color: (series.macd_hist[i] ?? 0) >= 0 ? "#22c55e" : "#ef4444",
          }))
          .filter((p): p is { time: UTCTimestamp; value: number; color: string } => p.value !== null)
      );
      const macdLine = macdChart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 1, priceLineVisible: false });
      macdLine.setData(toPoints(series.dates, series.macd));
      const signalLine = macdChart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 1, priceLineVisible: false });
      signalLine.setData(toPoints(series.dates, series.macd_signal));

      rsiChart.timeScale().fitContent();
      macdChart.timeScale().fitContent();
      chartsRef.current = [rsiChart, macdChart];

      const handleResize = () => {
        if (rsiRef.current) rsiChart.applyOptions({ width: rsiRef.current.clientWidth });
        if (macdRef.current) macdChart.applyOptions({ width: macdRef.current.clientWidth });
      };
      window.addEventListener("resize", handleResize);
      return () => window.removeEventListener("resize", handleResize);
    });

    return () => {
      disposed = true;
      chartsRef.current.forEach((c) => c.remove());
      chartsRef.current = [];
    };
  }, [series]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="mb-1 text-xs font-medium text-text-muted">RSI (14)</div>
        <div ref={rsiRef} className="w-full" />
      </div>
      <div>
        <div className="mb-1 text-xs font-medium text-text-muted">MACD (12, 26, 9)</div>
        <div ref={macdRef} className="w-full" />
      </div>
    </div>
  );
}
