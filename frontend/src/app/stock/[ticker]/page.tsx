import { notFound } from "next/navigation";
import {
  AIAnalysisOut,
  CandleOut,
  FibonacciOut,
  FundamentalsOut,
  NewsArticleOut,
  TechnicalsOut,
  TechnicalsSeries,
  ValuationOut,
  backendFetch,
} from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { FundamentalsGrid } from "@/components/FundamentalsGrid";
import { CandlestickChart } from "@/components/CandlestickChart";
import { IndicatorPanel } from "@/components/IndicatorPanel";
import { ValuationPanel } from "@/components/ValuationPanel";
import { AIAnalysisCard } from "@/components/AIAnalysisCard";
import { NewsFeed } from "@/components/NewsFeed";

async function safe<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch {
    return null;
  }
}

export default async function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase();

  const [fundamentals, candles, technicals, technicalsSeries, fibonacci, valuation, news, aiAnalysis] = await Promise.all([
    safe(backendFetch<FundamentalsOut>(`/api/stocks/${ticker}`)),
    safe(backendFetch<CandleOut[]>(`/api/stocks/${ticker}/candles?days=400`)),
    safe(backendFetch<TechnicalsOut>(`/api/technicals/${ticker}`)),
    safe(backendFetch<TechnicalsSeries>(`/api/technicals/${ticker}/series`)),
    safe(backendFetch<FibonacciOut>(`/api/technicals/${ticker}/fibonacci`)),
    safe(backendFetch<ValuationOut>(`/api/valuation/${ticker}`)),
    safe(backendFetch<NewsArticleOut[]>(`/api/news/${ticker}`)),
    safe(backendFetch<AIAnalysisOut>(`/api/stocks/${ticker}/ai-analysis`)),
  ]);

  if (!fundamentals) notFound();

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-text">{ticker}</h1>
          <p className="text-sm text-text-muted">As of {fundamentals.as_of_date}</p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold text-text">{formatPrice(fundamentals.price)}</div>
          {technicals?.week52_breakout && technicals.week52_breakout !== "none" && (
            <div className={`text-xs ${technicals.week52_breakout === "high" ? "text-bull" : "text-bear"}`}>
              52-week {technicals.week52_breakout}
            </div>
          )}
        </div>
      </div>

      <div className="mb-6">
        <FundamentalsGrid f={fundamentals} />
      </div>

      <div className="mb-6 rounded-xl border border-border bg-panel p-4">
        {candles && candles.length > 0 ? (
          <CandlestickChart candles={candles} series={technicalsSeries} fibonacci={fibonacci} />
        ) : (
          <p className="text-sm text-text-muted">No price history available yet.</p>
        )}
      </div>

      {technicalsSeries && (
        <div className="mb-6 rounded-xl border border-border bg-panel p-4">
          <IndicatorPanel series={technicalsSeries} />
          {technicals && (
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <MiniStat label="ATR (14)" value={technicals.atr14?.toFixed(2) ?? "—"} />
              <MiniStat label="Stochastic RSI" value={technicals.stoch_rsi ? technicals.stoch_rsi.toFixed(1) : "—"} />
              <MiniStat label="OBV" value={technicals.obv ? Math.round(technicals.obv).toLocaleString() : "—"} />
              <MiniStat label="MA Crossover" value={technicals.ma_crossover_signal ?? "none"} />
            </div>
          )}
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ValuationPanel ticker={ticker} initial={valuation} />
        {aiAnalysis ? (
          <AIAnalysisCard analysis={aiAnalysis} />
        ) : (
          <div className="rounded-xl border border-border bg-panel p-4 text-sm text-text-muted">
            No AI analysis yet — run the ingestion script to generate one.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-panel p-4">
        <h2 className="mb-3 text-sm font-semibold text-text">News</h2>
        <NewsFeed articles={news ?? []} />
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-panel-2 px-3 py-2">
      <div className="text-xs text-text-muted">{label}</div>
      <div className="font-semibold text-text">{value}</div>
    </div>
  );
}
