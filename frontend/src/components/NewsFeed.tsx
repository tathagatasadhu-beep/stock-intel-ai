import { NewsArticleOut } from "@/lib/api";

const IMPACT_COLOR: Record<string, string> = {
  high: "text-bear bg-bear-dim",
  medium: "text-warn bg-[#f59e0b1a]",
  low: "text-text-muted bg-panel-2",
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "text-bull",
  negative: "text-bear",
  neutral: "text-text-muted",
};

export function NewsFeed({ articles }: { articles: NewsArticleOut[] }) {
  if (articles.length === 0) {
    return <p className="text-sm text-text-muted">No recent news for this stock.</p>;
  }
  return (
    <ul className="flex flex-col divide-y divide-border">
      {articles.map((a) => (
        <li key={a.url} className="py-3">
          <a href={a.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-text hover:text-accent">
            {a.headline}
          </a>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-muted">
            <span>{a.source}</span>
            <span>·</span>
            <span>{new Date(a.published_at).toLocaleDateString()}</span>
            {a.sentiment_label && <span className={SENTIMENT_COLOR[a.sentiment_label] ?? ""}>{a.sentiment_label}</span>}
            {a.impact_score && <span className={`rounded px-1.5 py-0.5 ${IMPACT_COLOR[a.impact_score] ?? ""}`}>{a.impact_score} impact</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}
