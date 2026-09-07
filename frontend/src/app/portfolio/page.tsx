import Link from "next/link";
import { BackendError, backendFetch, PortfolioSummaryOut } from "@/lib/api";
import { getAuthToken } from "@/lib/session";
import { PortfolioManager } from "@/components/PortfolioManager";

export const metadata = { title: "Portfolio" };

export default async function PortfolioPage() {
  const token = await getAuthToken();

  if (!token) {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="mb-2 text-xl font-bold text-text">Sign in to track your portfolio</h1>
        <p className="mb-6 text-sm text-text-muted">
          Add your actual stock and ETF positions and this app will monitor them daily — unrealized gain/loss,
          exit suggestions when you hit your stop-loss or target, technical risk flags, and news-driven upside/
          downside alerts, emailed to you automatically.
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

  let portfolio: PortfolioSummaryOut | null = null;
  let loadError: string | null = null;
  try {
    portfolio = await backendFetch<PortfolioSummaryOut>("/api/portfolio", { headers: { Authorization: `Bearer ${token}` } });
  } catch (err) {
    loadError = err instanceof BackendError ? err.message : "Failed to load your portfolio.";
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-1 text-xl font-bold text-text">Your Portfolio</h1>
      <p className="mb-6 text-sm text-text-muted">
        Monitored daily — exit suggestions, risk flags, and news-driven alerts are algorithmic signals, not
        financial advice. Review before acting.
      </p>
      {loadError && <p className="mb-4 text-sm text-bear">{loadError}</p>}
      <PortfolioManager initial={portfolio ?? { total_cost_basis: 0, total_market_value: null, total_unrealized_pnl: null, total_unrealized_pnl_pct: null, holdings: [] }} />
    </div>
  );
}
