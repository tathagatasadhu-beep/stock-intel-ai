/**
 * Server-only fetch helper for calling the FastAPI backend. Used by Server Components
 * directly and by Route Handlers (frontend/src/app/api/**\/route.ts) that proxy client
 * requests — the browser itself never calls BACKEND_URL (see CLAUDE.md -> Conventions).
 */
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8001";

export class BackendError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function backendFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new BackendError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type StockSummary = {
  ticker: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  price: number | null;
};

export type FundamentalsOut = {
  as_of_date: string;
  price: number;
  pe_ratio: number | null;
  forward_pe: number | null;
  peg_ratio: number | null;
  price_to_book: number | null;
  ev_ebitda: number | null;
  revenue_growth_yoy: number | null;
  eps_growth: number | null;
  fcf_growth: number | null;
  roe: number | null;
  roic: number | null;
  debt_equity: number | null;
  current_ratio: number | null;
  interest_coverage: number | null;
  altman_z_score: number | null;
  week52_high: number | null;
  week52_low: number | null;
  avg_volume: number | null;
};

export type CandleOut = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type TechnicalsOut = {
  as_of_date: string;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  bollinger_upper: number | null;
  bollinger_mid: number | null;
  bollinger_lower: number | null;
  vwap: number | null;
  atr14: number | null;
  obv: number | null;
  stoch_rsi: number | null;
  ma_crossover_signal: string | null;
  volume_breakout: boolean;
  week52_breakout: string | null;
};

export type TechnicalsSeries = {
  dates: string[];
  sma20: (number | null)[];
  sma50: (number | null)[];
  sma200: (number | null)[];
  bollinger_upper: (number | null)[];
  bollinger_mid: (number | null)[];
  bollinger_lower: (number | null)[];
  vwap: (number | null)[];
  rsi14: (number | null)[];
  macd: (number | null)[];
  macd_signal: (number | null)[];
  macd_hist: (number | null)[];
  atr14: (number | null)[];
  obv: (number | null)[];
  stoch_rsi: (number | null)[];
};

export type FibonacciOut = {
  as_of_date: string;
  trend_direction: string;
  swing_high: number;
  swing_low: number;
  level_0: number;
  level_236: number;
  level_382: number;
  level_500: number;
  level_618: number;
  level_786: number;
  level_100: number;
  nearest_support: number | null;
  nearest_resistance: number | null;
  breakout_probability: number | null;
};

export type ValuationMethodResult = {
  method: string;
  intrinsic_value: number | null;
  current_price: number;
  margin_of_safety_pct: number | null;
  notes: string | null;
};

export type ValuationOut = {
  as_of_date: string;
  inputs: { wacc: number; fcf_growth_rate: number; terminal_growth_rate: number; projection_years: number };
  results: ValuationMethodResult[];
  blended_intrinsic_value: number | null;
};

export type NewsArticleOut = {
  source: string;
  headline: string;
  url: string;
  summary: string | null;
  published_at: string;
  sentiment_score: number | null;
  sentiment_label: string | null;
  impact_score: string | null;
};

export type AIAnalysisOut = {
  generated_at: string;
  bullish_bearish_score: number;
  risk_score: number;
  investment_thesis: string;
  technical_thesis: string;
  key_risks: string[];
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  target_3m: number | null;
  target_6m: number | null;
  target_1y: number | null;
};

export type ScreenerRow = {
  ticker: string;
  company_name: string;
  sector: string | null;
  price: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  peg_ratio: number | null;
  margin_of_safety_pct: number | null;
  revenue_growth_yoy: number | null;
  roe: number | null;
  debt_equity: number | null;
  rsi14: number | null;
  macd_hist: number | null;
  valuation_score: number;
  growth_score: number;
  financial_health_score: number;
  technical_score: number;
  news_sentiment_score: number;
  composite_score: number;
  rating: string;
};
