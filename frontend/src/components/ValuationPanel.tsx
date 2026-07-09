"use client";

import { useEffect, useState } from "react";
import { ValuationOut } from "@/lib/api";
import { formatPercentValue, formatPrice } from "@/lib/format";

const METHOD_LABELS: Record<string, string> = {
  dcf: "Discounted Cash Flow",
  ddm: "Dividend Discount Model",
  owner_earnings: "Owner Earnings",
  comparable: "Comparable (Peer P/E)",
};

export function ValuationPanel({ ticker, initial }: { ticker: string; initial: ValuationOut | null }) {
  const [wacc, setWacc] = useState(initial?.inputs.wacc ?? 0.08);
  const [fcfGrowth, setFcfGrowth] = useState(initial?.inputs.fcf_growth_rate ?? 0.05);
  const [terminalGrowth, setTerminalGrowth] = useState(initial?.inputs.terminal_growth_rate ?? 0.025);
  const [years, setYears] = useState(initial?.inputs.projection_years ?? 5);
  const [data, setData] = useState<ValuationOut | null>(initial);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => {
      setLoading(true);
      const params = new URLSearchParams({
        wacc: String(wacc),
        fcf_growth_rate: String(fcfGrowth),
        terminal_growth_rate: String(terminalGrowth),
        projection_years: String(years),
      });
      fetch(`/api/valuation/${ticker}?${params.toString()}`)
        .then((res) => res.json())
        .then((d) => setData(d))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [ticker, wacc, fcfGrowth, terminalGrowth, years]);

  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <h2 className="mb-3 text-sm font-semibold text-text">Intrinsic Value Engine</h2>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-text-muted">WACC {(wacc * 100).toFixed(1)}%</span>
          <input type="range" min={0.02} max={0.2} step={0.005} value={wacc} onChange={(e) => setWacc(Number(e.target.value))} className="accent-accent" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-text-muted">FCF Growth {(fcfGrowth * 100).toFixed(1)}%</span>
          <input type="range" min={-0.1} max={0.4} step={0.01} value={fcfGrowth} onChange={(e) => setFcfGrowth(Number(e.target.value))} className="accent-accent" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-text-muted">Terminal Growth {(terminalGrowth * 100).toFixed(1)}%</span>
          <input type="range" min={0} max={0.05} step={0.0025} value={terminalGrowth} onChange={(e) => setTerminalGrowth(Number(e.target.value))} className="accent-accent" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-text-muted">Projection Years {years}</span>
          <input type="range" min={1} max={15} step={1} value={years} onChange={(e) => setYears(Number(e.target.value))} className="accent-accent" />
        </label>
      </div>

      {data && (
        <div className={loading ? "opacity-50 transition-opacity" : "transition-opacity"}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-text-muted">
              <tr>
                <th className="py-1">Method</th>
                <th className="py-1">Intrinsic Value</th>
                <th className="py-1">Margin of Safety</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.method} className="border-t border-border">
                  <td className="py-1.5 text-text">{METHOD_LABELS[r.method] ?? r.method}</td>
                  <td className="py-1.5 text-text">{r.intrinsic_value ? formatPrice(r.intrinsic_value) : <span className="text-text-faint">{r.notes ?? "N/A"}</span>}</td>
                  <td className={`py-1.5 ${(r.margin_of_safety_pct ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>
                    {r.margin_of_safety_pct !== null ? formatPercentValue(r.margin_of_safety_pct) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center justify-between rounded-lg bg-panel-2 px-3 py-2">
            <span className="text-sm text-text-muted">Blended intrinsic value vs. current price ({formatPrice(data.results[0]?.current_price)})</span>
            <span className="text-lg font-bold text-text">{data.blended_intrinsic_value ? formatPrice(data.blended_intrinsic_value) : "—"}</span>
          </div>
        </div>
      )}
    </div>
  );
}
