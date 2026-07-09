import { AIAnalysisOut } from "@/lib/api";
import { formatPrice } from "@/lib/format";

function ScoreGauge({ label, value, invert }: { label: string; value: number; invert?: boolean }) {
  const good = invert ? value <= 40 : value >= 60;
  const bad = invert ? value >= 70 : value <= 40;
  const color = good ? "bg-bull" : bad ? "bg-bear" : "bg-warn";
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-text-muted">
        <span>{label}</span>
        <span className="text-text">{value}/100</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-panel-2">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export function AIAnalysisCard({ analysis }: { analysis: AIAnalysisOut }) {
  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <h2 className="mb-3 text-sm font-semibold text-text">AI Trading Assistant</h2>

      <div className="mb-4 grid grid-cols-2 gap-4">
        <ScoreGauge label="Bullish / Bearish" value={analysis.bullish_bearish_score} />
        <ScoreGauge label="Risk" value={analysis.risk_score} invert />
      </div>

      <div className="mb-3">
        <h3 className="mb-1 text-xs font-semibold uppercase text-text-muted">Investment Thesis</h3>
        <p className="text-sm text-text">{analysis.investment_thesis}</p>
      </div>
      <div className="mb-3">
        <h3 className="mb-1 text-xs font-semibold uppercase text-text-muted">Technical Thesis</h3>
        <p className="text-sm text-text">{analysis.technical_thesis}</p>
      </div>
      <div className="mb-4">
        <h3 className="mb-1 text-xs font-semibold uppercase text-text-muted">Key Risks</h3>
        <ul className="list-inside list-disc text-sm text-text-muted">
          {analysis.key_risks.map((risk, i) => (
            <li key={i}>{risk}</li>
          ))}
        </ul>
      </div>

      <div className="grid grid-cols-2 gap-3 rounded-lg bg-panel-2 p-3 text-sm sm:grid-cols-5">
        <Stat label="Entry Zone" value={analysis.entry_zone_low && analysis.entry_zone_high ? `${formatPrice(analysis.entry_zone_low)}–${formatPrice(analysis.entry_zone_high)}` : "—"} />
        <Stat label="Stop Loss" value={formatPrice(analysis.stop_loss)} accent="text-bear" />
        <Stat label="3M Target" value={formatPrice(analysis.target_3m)} accent="text-bull" />
        <Stat label="6M Target" value={formatPrice(analysis.target_6m)} accent="text-bull" />
        <Stat label="1Y Target" value={formatPrice(analysis.target_1y)} accent="text-bull" />
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <div className="text-xs text-text-muted">{label}</div>
      <div className={`font-semibold ${accent ?? "text-text"}`}>{value}</div>
    </div>
  );
}
