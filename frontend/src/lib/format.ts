export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${value.toFixed(2)}`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

/** For values already stored as a percent (e.g. margin_of_safety_pct = 18, not 0.18). */
export function formatPercentValue(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toFixed(2);
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function ratingColor(rating: string): string {
  switch (rating) {
    case "Strong Buy":
      return "text-bull bg-bull-dim";
    case "Buy":
      return "text-bull bg-bull-dim";
    case "Hold":
      return "text-warn bg-[#f59e0b1a]";
    case "Weak Hold":
      return "text-warn bg-[#f59e0b1a]";
    case "Avoid":
      return "text-bear bg-bear-dim";
    default:
      return "text-text-muted bg-panel-2";
  }
}

export function scoreColor(score: number): string {
  if (score >= 75) return "text-bull";
  if (score >= 50) return "text-warn";
  return "text-bear";
}
