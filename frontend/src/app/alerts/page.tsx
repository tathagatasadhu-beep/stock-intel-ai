import Link from "next/link";
import { BackendError, backendFetch, StockSummary } from "@/lib/api";
import { getAuthToken } from "@/lib/session";
import { AlertsManager, type AlertRow } from "@/components/AlertsManager";

export const metadata = { title: "Alerts" };

export default async function AlertsPage() {
  const token = await getAuthToken();

  if (!token) {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="mb-2 text-xl font-bold text-text">Sign in to manage alerts</h1>
        <p className="mb-6 text-sm text-text-muted">
          Alerts (RSI oversold, MACD crossovers, support/resistance breaks, volume spikes) are tied to your account
          so they can be emailed to you.
        </p>
        <div className="flex justify-center gap-3">
          <Link href="/login" className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-dim">
            Log In
          </Link>
          <Link href="/signup" className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-text hover:bg-panel-2">
            Sign Up
          </Link>
        </div>
      </div>
    );
  }

  let alerts: AlertRow[] = [];
  let loadError: string | null = null;
  try {
    alerts = await backendFetch<AlertRow[]>("/api/alerts", { headers: { Authorization: `Bearer ${token}` } });
  } catch (err) {
    loadError = err instanceof BackendError ? err.message : "Failed to load alerts.";
  }

  let stocks: StockSummary[] = [];
  try {
    stocks = await backendFetch<StockSummary[]>("/api/stocks?limit=500");
  } catch {
    stocks = [];
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-1 text-xl font-bold text-text">Your Alerts</h1>
      <p className="mb-6 text-sm text-text-muted">
        Delivered by email when the daily data refresh detects a trigger (see the ingestion job — alerts aren&apos;t
        checked in real time in this MVP).
      </p>
      {loadError && <p className="mb-4 text-sm text-bear">{loadError}</p>}
      <AlertsManager initialAlerts={alerts} tickers={stocks.map((s) => s.ticker)} />
    </div>
  );
}
