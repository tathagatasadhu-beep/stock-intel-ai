"use client";

import Link from "next/link";
import { Trash2, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { PortfolioHoldingOut, PortfolioSummaryOut } from "@/lib/api";
import { formatPrice, ratingColor } from "@/lib/format";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "text-bear bg-bear-dim border-bear/40",
  warning: "text-warn bg-[#f59e0b1a] border-warn/40",
  info: "text-text-muted bg-panel-2 border-border",
};

function pnlColor(value: number | null): string {
  if (value === null) return "text-text-muted";
  return value >= 0 ? "text-bull" : "text-bear";
}

function formatPct(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function PortfolioManager({ initial }: { initial: PortfolioSummaryOut }) {
  const [portfolio, setPortfolio] = useState(initial);
  const [ticker, setTicker] = useState("");
  const [assetType, setAssetType] = useState<"stock" | "etf">("stock");
  const [quantity, setQuantity] = useState("");
  const [costBasis, setCostBasis] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    const res = await fetch("/api/portfolio");
    if (res.ok) setPortfolio(await res.json());
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const res = await fetch("/api/portfolio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: ticker.trim().toUpperCase(),
        asset_type: assetType,
        quantity: Number(quantity),
        cost_basis_per_share: Number(costBasis),
      }),
    });
    const data = await res.json();
    setSubmitting(false);
    if (!res.ok) {
      setError(data.error || "Failed to add holding.");
      return;
    }
    setTicker("");
    setQuantity("");
    setCostBasis("");
    await refresh();
  }

  async function handleDelete(id: string) {
    setPortfolio((prev) => ({ ...prev, holdings: prev.holdings.filter((h) => h.id !== id) }));
    await fetch(`/api/portfolio/holdings/${id}`, { method: "DELETE" });
    await refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-panel p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-text-muted">Ticker</label>
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="e.g. AAPL or SPY"
            required
            className="w-32 rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-text-muted">Type</label>
          <select value={assetType} onChange={(e) => setAssetType(e.target.value as "stock" | "etf")} className="rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text">
            <option value="stock">Stock</option>
            <option value="etf">ETF</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-text-muted">Shares</label>
          <input
            type="number"
            step="any"
            min="0"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            required
            className="w-28 rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-text-muted">Avg. cost / share</label>
          <input
            type="number"
            step="any"
            min="0"
            value={costBasis}
            onChange={(e) => setCostBasis(e.target.value)}
            placeholder="$"
            required
            className="w-28 rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-text"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Adding..." : "Add Holding"}
        </button>
      </form>
      {error && <p className="text-sm text-bear">{error}</p>}

      {portfolio.holdings.length > 0 && (
        <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-panel p-4 sm:grid-cols-4">
          <div>
            <div className="text-xs text-text-muted">Cost Basis</div>
            <div className="text-lg font-semibold text-text">{formatPrice(portfolio.total_cost_basis)}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted">Market Value</div>
            <div className="text-lg font-semibold text-text">{formatPrice(portfolio.total_market_value)}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted">Unrealized P&amp;L</div>
            <div className={`text-lg font-semibold ${pnlColor(portfolio.total_unrealized_pnl)}`}>{formatPrice(portfolio.total_unrealized_pnl)}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted">Return</div>
            <div className={`text-lg font-semibold ${pnlColor(portfolio.total_unrealized_pnl_pct)}`}>{formatPct(portfolio.total_unrealized_pnl_pct)}</div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {portfolio.holdings.length === 0 && (
          <p className="rounded-xl border border-border bg-panel p-6 text-center text-sm text-text-muted">
            No holdings yet — add your first stock or ETF above.
          </p>
        )}
        {portfolio.holdings.map((h) => (
          <HoldingCard key={h.id} holding={h} onDelete={() => handleDelete(h.id)} />
        ))}
      </div>
    </div>
  );
}

function HoldingCard({ holding, onDelete }: { holding: PortfolioHoldingOut; onDelete: () => void }) {
  const pnlIcon = holding.unrealized_pnl === null ? null : holding.unrealized_pnl >= 0 ? (
    <TrendingUp className="h-4 w-4 text-bull" />
  ) : (
    <TrendingDown className="h-4 w-4 text-bear" />
  );

  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <Link href={`/stock/${holding.ticker}`} className="font-semibold text-text hover:text-accent">
              {holding.ticker}
            </Link>
            <span className="rounded bg-panel-2 px-1.5 py-0.5 text-xs uppercase text-text-muted">{holding.asset_type}</span>
            {holding.rating && <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${ratingColor(holding.rating)}`}>{holding.rating}</span>}
          </div>
          <div className="text-xs text-text-faint">{holding.company_name}{holding.sector ? ` · ${holding.sector}` : ""}</div>
        </div>
        <button onClick={onDelete} className="text-text-faint hover:text-bear">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <div>
          <div className="text-xs text-text-muted">Shares @ Cost</div>
          <div className="text-text">{holding.quantity} @ {formatPrice(holding.cost_basis_per_share)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Current Price</div>
          <div className="text-text">{formatPrice(holding.current_price)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Market Value</div>
          <div className="text-text">{formatPrice(holding.market_value)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Unrealized P&amp;L</div>
          <div className={`flex items-center gap-1 font-medium ${pnlColor(holding.unrealized_pnl)}`}>
            {pnlIcon} {formatPrice(holding.unrealized_pnl)}
          </div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Return</div>
          <div className={`font-medium ${pnlColor(holding.unrealized_pnl_pct)}`}>{formatPct(holding.unrealized_pnl_pct)}</div>
        </div>
      </div>

      {holding.flags.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5 border-t border-border pt-3">
          {holding.flags.map((flag, i) => (
            <div key={i} className={`rounded-md border px-2.5 py-1.5 text-xs ${SEVERITY_STYLE[flag.severity] ?? SEVERITY_STYLE.info}`}>
              <span className="font-semibold uppercase">{flag.severity}</span> — {flag.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
