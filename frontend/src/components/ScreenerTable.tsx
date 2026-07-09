import Link from "next/link";
import { ScreenerRow } from "@/lib/api";
import { formatCompact, formatPercentValue, formatPrice, ratingColor, scoreColor } from "@/lib/format";

const COLUMNS: { key: keyof ScreenerRow | "actions"; label: string; sortable?: boolean }[] = [
  { key: "ticker", label: "Ticker", sortable: true },
  { key: "sector", label: "Sector" },
  { key: "price", label: "Price", sortable: true },
  { key: "market_cap", label: "Mkt Cap", sortable: true },
  { key: "pe_ratio", label: "P/E", sortable: true },
  { key: "margin_of_safety_pct", label: "Margin of Safety", sortable: true },
  { key: "revenue_growth_yoy", label: "Rev Growth", sortable: true },
  { key: "roe", label: "ROE", sortable: true },
  { key: "rsi14", label: "RSI", sortable: true },
  { key: "composite_score", label: "Score", sortable: true },
  { key: "rating", label: "Rating" },
];

export function ScreenerTable({
  rows,
  currentParams,
}: {
  rows: ScreenerRow[];
  currentParams: Record<string, string>;
}) {
  const sortBy = currentParams.sort_by ?? "composite_score";
  const sortDesc = currentParams.sort_desc !== "false";

  function sortHref(key: string) {
    const params = new URLSearchParams(currentParams);
    params.set("sort_by", key);
    params.set("sort_desc", sortBy === key && sortDesc ? "false" : "true");
    return `/?${params.toString()}`;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[900px] text-sm">
        <thead className="bg-panel-2 text-left text-xs uppercase text-text-muted">
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.key} className="whitespace-nowrap px-3 py-2">
                {col.sortable ? (
                  <Link href={sortHref(col.key)} className="hover:text-text">
                    {col.label} {sortBy === col.key ? (sortDesc ? "▼" : "▲") : ""}
                  </Link>
                ) : (
                  col.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-text-muted">
                No stocks match these filters.
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.ticker} className="border-t border-border hover:bg-panel-2/60">
              <td className="whitespace-nowrap px-3 py-2 font-semibold text-text">
                <Link href={`/stock/${r.ticker}`} className="hover:text-accent">
                  {r.ticker}
                </Link>
                <div className="text-xs font-normal text-text-faint">{r.company_name}</div>
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-text-muted">{r.sector ?? "—"}</td>
              <td className="whitespace-nowrap px-3 py-2 text-text">{formatPrice(r.price)}</td>
              <td className="whitespace-nowrap px-3 py-2 text-text-muted">{formatCompact(r.market_cap)}</td>
              <td className="whitespace-nowrap px-3 py-2 text-text-muted">{r.pe_ratio?.toFixed(1) ?? "—"}</td>
              <td className={`whitespace-nowrap px-3 py-2 ${(r.margin_of_safety_pct ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>
                {formatPercentValue(r.margin_of_safety_pct)}
              </td>
              <td className={`whitespace-nowrap px-3 py-2 ${(r.revenue_growth_yoy ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>
                {formatPercentValue(r.revenue_growth_yoy ? r.revenue_growth_yoy * 100 : null)}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-text-muted">{r.roe ? `${(r.roe * 100).toFixed(1)}%` : "—"}</td>
              <td className="whitespace-nowrap px-3 py-2 text-text-muted">{r.rsi14?.toFixed(0) ?? "—"}</td>
              <td className={`whitespace-nowrap px-3 py-2 font-semibold ${scoreColor(r.composite_score)}`}>{r.composite_score.toFixed(1)}</td>
              <td className="whitespace-nowrap px-3 py-2">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${ratingColor(r.rating)}`}>{r.rating}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
