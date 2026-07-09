import { FundamentalsOut } from "@/lib/api";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-panel-2 px-3 py-2">
      <div className="text-xs text-text-muted">{label}</div>
      <div className="text-sm font-semibold text-text">{value}</div>
    </div>
  );
}

function pct(v: number | null, digits = 1) {
  return v === null ? "—" : `${(v * 100).toFixed(digits)}%`;
}
function num(v: number | null, digits = 2) {
  return v === null ? "—" : v.toFixed(digits);
}

export function FundamentalsGrid({ f }: { f: FundamentalsOut }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
      <Stat label="P/E" value={num(f.pe_ratio)} />
      <Stat label="Forward P/E" value={num(f.forward_pe)} />
      <Stat label="PEG" value={num(f.peg_ratio)} />
      <Stat label="Price/Book" value={num(f.price_to_book)} />
      <Stat label="EV/EBITDA" value={num(f.ev_ebitda)} />
      <Stat label="Avg Volume" value={f.avg_volume ? Math.round(f.avg_volume).toLocaleString() : "—"} />
      <Stat label="Revenue Growth" value={pct(f.revenue_growth_yoy)} />
      <Stat label="EPS Growth" value={pct(f.eps_growth)} />
      <Stat label="FCF Growth" value={pct(f.fcf_growth)} />
      <Stat label="ROE" value={pct(f.roe)} />
      <Stat label="ROIC" value={pct(f.roic)} />
      <Stat label="Debt/Equity" value={num(f.debt_equity)} />
      <Stat label="Current Ratio" value={num(f.current_ratio)} />
      <Stat label="Interest Coverage" value={num(f.interest_coverage, 1)} />
      <Stat label="Altman Z-Score" value={num(f.altman_z_score)} />
      <Stat label="52W High" value={f.week52_high ? `$${f.week52_high.toFixed(2)}` : "—"} />
      <Stat label="52W Low" value={f.week52_low ? `$${f.week52_low.toFixed(2)}` : "—"} />
    </div>
  );
}
