"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

export type AlertRow = {
  id: string;
  ticker: string;
  alert_type: string;
  threshold_value: number | null;
  delivery_method: string;
  is_active: boolean;
  last_triggered_at: string | null;
  created_at: string;
};

const ALERT_TYPES = [
  { value: "rsi_oversold", label: "RSI drops below threshold (oversold)" },
  { value: "rsi_overbought", label: "RSI rises above threshold (overbought)" },
  { value: "macd_bullish_cross", label: "MACD bullish crossover (golden cross)" },
  { value: "volume_spike", label: "Volume breakout" },
  { value: "price_below_support", label: "Price crosses below Fibonacci support" },
  { value: "price_above_resistance", label: "Price crosses above Fibonacci resistance" },
];

export function AlertsManager({ initialAlerts, tickers }: { initialAlerts: AlertRow[]; tickers: string[] }) {
  const [alerts, setAlerts] = useState(initialAlerts);
  const [ticker, setTicker] = useState(tickers[0] ?? "");
  const [alertType, setAlertType] = useState(ALERT_TYPES[0].value);
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const res = await fetch("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker,
        alert_type: alertType,
        threshold_value: threshold ? Number(threshold) : null,
      }),
    });
    const data = await res.json();
    setSubmitting(false);
    if (!res.ok) {
      setError(data.error || "Failed to create alert.");
      return;
    }
    setAlerts((prev) => [data, ...prev]);
    setThreshold("");
  }

  async function handleDelete(id: string) {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    await fetch(`/api/alerts/${id}`, { method: "DELETE" });
  }

  const needsThreshold = alertType === "rsi_oversold" || alertType === "rsi_overbought";

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-panel p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-text-muted">Ticker</label>
          <select value={ticker} onChange={(e) => setTicker(e.target.value)} className="rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text">
            {tickers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-text-muted">Condition</label>
          <select value={alertType} onChange={(e) => setAlertType(e.target.value)} className="rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text">
            {ALERT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        {needsThreshold && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-text-muted">Threshold</label>
            <input
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder={alertType === "rsi_oversold" ? "30" : "70"}
              className="w-24 rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text"
            />
          </div>
        )}
        <button
          type="submit"
          disabled={submitting || !ticker}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Adding..." : "Add Alert"}
        </button>
      </form>
      {error && <p className="text-sm text-bear">{error}</p>}

      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-xs uppercase text-text-muted">
            <tr>
              <th className="px-4 py-2">Ticker</th>
              <th className="px-4 py-2">Condition</th>
              <th className="px-4 py-2">Threshold</th>
              <th className="px-4 py-2">Last Triggered</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-muted">
                  No alerts yet.
                </td>
              </tr>
            )}
            {alerts.map((a) => (
              <tr key={a.id} className="border-t border-border">
                <td className="px-4 py-2 font-medium text-text">{a.ticker}</td>
                <td className="px-4 py-2 text-text-muted">{ALERT_TYPES.find((t) => t.value === a.alert_type)?.label ?? a.alert_type}</td>
                <td className="px-4 py-2 text-text-muted">{a.threshold_value ?? "—"}</td>
                <td className="px-4 py-2 text-text-muted">{a.last_triggered_at ? new Date(a.last_triggered_at).toLocaleString() : "Never"}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => handleDelete(a.id)} className="text-text-faint hover:text-bear">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
