"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

const SECTORS = [
  "Technology", "Financials", "Healthcare", "Energy", "Consumer Staples", "Consumer Discretionary",
  "Industrials", "Utilities", "Materials", "Real Estate", "Communication Services",
];

const RATINGS = ["Strong Buy", "Buy", "Hold", "Weak Hold", "Avoid"];

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-text-muted">{label}</span>
      {children}
    </label>
  );
}

const inputCls = "w-full rounded-md border border-border bg-panel-2 px-2 py-1.5 text-sm text-text focus:border-accent focus:outline-none";

export function ScreenerFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [form, setForm] = useState<Record<string, string>>(() => Object.fromEntries(searchParams.entries()));

  function set(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function apply(e: React.FormEvent) {
    e.preventDefault();
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(form)) {
      if (value !== "" && value !== undefined) params.set(key, value);
    }
    router.push(`/?${params.toString()}`);
  }

  function reset() {
    setForm({});
    router.push("/");
  }

  return (
    <form onSubmit={apply} className="mb-4 grid grid-cols-2 gap-3 rounded-xl border border-border bg-panel p-4 sm:grid-cols-3 md:grid-cols-6">
      <Field label="Sector">
        <select className={inputCls} value={form.sector ?? ""} onChange={(e) => set("sector", e.target.value)}>
          <option value="">Any</option>
          {SECTORS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </Field>
      <Field label="Rating">
        <select className={inputCls} value={form.rating ?? ""} onChange={(e) => set("rating", e.target.value)}>
          <option value="">Any</option>
          {RATINGS.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </Field>
      <Field label="Max P/E">
        <input className={inputCls} type="number" value={form.pe_max ?? ""} onChange={(e) => set("pe_max", e.target.value)} placeholder="e.g. 25" />
      </Field>
      <Field label="Min Margin of Safety %">
        <input className={inputCls} type="number" value={form.margin_of_safety_min ?? ""} onChange={(e) => set("margin_of_safety_min", e.target.value)} placeholder="e.g. 10" />
      </Field>
      <Field label="Min Revenue Growth">
        <input className={inputCls} type="number" step="0.01" value={form.revenue_growth_min ?? ""} onChange={(e) => set("revenue_growth_min", e.target.value)} placeholder="0.10 = 10%" />
      </Field>
      <Field label="Min ROE">
        <input className={inputCls} type="number" step="0.01" value={form.roe_min ?? ""} onChange={(e) => set("roe_min", e.target.value)} placeholder="0.15 = 15%" />
      </Field>
      <Field label="Max Debt/Equity">
        <input className={inputCls} type="number" step="0.1" value={form.debt_equity_max ?? ""} onChange={(e) => set("debt_equity_max", e.target.value)} placeholder="e.g. 1.5" />
      </Field>
      <Field label="RSI min">
        <input className={inputCls} type="number" value={form.rsi_min ?? ""} onChange={(e) => set("rsi_min", e.target.value)} placeholder="0" />
      </Field>
      <Field label="RSI max">
        <input className={inputCls} type="number" value={form.rsi_max ?? ""} onChange={(e) => set("rsi_max", e.target.value)} placeholder="100" />
      </Field>
      <Field label="Min Composite Score">
        <input className={inputCls} type="number" value={form.min_composite_score ?? ""} onChange={(e) => set("min_composite_score", e.target.value)} placeholder="e.g. 60" />
      </Field>

      <div className="col-span-2 flex flex-wrap items-end gap-3 sm:col-span-3 md:col-span-2">
        {[
          ["golden_cross_only", "Golden cross"],
          ["macd_bullish_only", "MACD bullish"],
          ["volume_breakout_only", "Volume breakout"],
          ["near_52w_high", "Near 52w high"],
        ].map(([key, label]) => (
          <label key={key} className="flex items-center gap-1.5 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={form[key] === "true"}
              onChange={(e) => set(key, e.target.checked ? "true" : "")}
              className="accent-accent"
            />
            {label}
          </label>
        ))}
      </div>

      <div className="col-span-2 flex items-end gap-2 sm:col-span-1">
        <button type="submit" className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:bg-accent-dim">
          Apply
        </button>
        <button type="button" onClick={reset} className="rounded-md border border-border px-3 py-1.5 text-sm text-text-muted hover:bg-panel-2">
          Reset
        </button>
      </div>
    </form>
  );
}
