import { BackendError, backendFetch, ScreenerRow } from "@/lib/api";
import { ScreenerFilters } from "@/components/ScreenerFilters";
import { ScreenerTable } from "@/components/ScreenerTable";

export default async function HomePage({ searchParams }: { searchParams: Promise<Record<string, string>> }) {
  const params = await searchParams;
  const qs = new URLSearchParams(params).toString();

  let rows: ScreenerRow[] = [];
  let error: string | null = null;
  try {
    rows = await backendFetch<ScreenerRow[]>(`/api/screener${qs ? `?${qs}` : ""}`);
  } catch (err) {
    error = err instanceof BackendError ? err.message : "Failed to load the screener — is the backend running?";
  }

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-6">
      <div className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-bold text-text">S&P 500 Screener</h1>
          <p className="text-sm text-text-muted">
            Ranked by composite score: 30% valuation, 25% growth, 20% financial health, 15% technicals, 10% news
            sentiment.
          </p>
        </div>
        <span className="text-sm text-text-muted">{rows.length} results</span>
      </div>
      <ScreenerFilters />
      {error ? <p className="rounded-lg border border-bear/40 bg-bear-dim px-4 py-3 text-sm text-bear">{error}</p> : <ScreenerTable rows={rows} currentParams={params} />}
    </div>
  );
}
