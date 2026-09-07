"""
Portfolio monitoring: evaluates each holding's latest fundamentals/technicals/AI-analysis/
news against the user's own cost basis and raises flags — exit suggestions, risk warnings,
and news-driven upside/downside signals. Run by scripts/refresh_universe.py after each
day's ingestion, for every holding whose stock got refreshed that day (see CLAUDE.md ->
"Portfolio monitoring").

These are heuristic, rule-based flags derived from the same technical/fundamental/AI data
already shown elsewhere in the app (stop-loss/target from the AI analysis, RSI/MA-crossover
from technicals, sentiment from news) — not a licensed advisor's recommendation. Framed in
the UI as "flags to review," not commands, same spirit as the AI Trading Assistant's
existing entry-zone/stop-loss fields it's built on top of.

One flag row per (holding, flag_type, day) — see PortfolioFlag's unique constraint — so a
condition that's still true tomorrow doesn't re-flag (and re-email) every single day; it
only flags again once it's re-evaluated as newly true after having been false.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import (
    AIAnalysis,
    FundamentalSnapshot,
    NewsArticle,
    PortfolioFlag,
    PortfolioHolding,
    Stock,
    TechnicalSnapshot,
)

# Thresholds are intentionally simple/explainable rather than statistically tuned — this
# is a personal tool, not a quant desk. Easy to adjust here if they prove too noisy/quiet.
OVERBOUGHT_RSI = 70
OVERSOLD_RSI = 30
LARGE_GAIN_PCT = 15.0  # paired with overbought RSI for a "consider trimming" flag
LARGE_UNREALIZED_LOSS_PCT = -20.0
LARGE_UNREALIZED_GAIN_PCT = 50.0
NEWS_LOOKBACK_DAYS = 7
NEWS_SENTIMENT_THRESHOLD = 0.3
SECTOR_CONCENTRATION_THRESHOLD_PCT = 40.0


@dataclass
class FlagCandidate:
    flag_type: str
    severity: str  # info | warning | critical
    message: str


def evaluate_holding(
    holding: PortfolioHolding,
    stock: Stock,
    current_price: float,
    technicals: TechnicalSnapshot | None,
    ai_analysis: AIAnalysis | None,
    recent_news: list[NewsArticle],
) -> list[FlagCandidate]:
    flags: list[FlagCandidate] = []
    pnl_pct = (current_price - holding.cost_basis_per_share) / holding.cost_basis_per_share * 100

    if ai_analysis and ai_analysis.stop_loss and current_price <= ai_analysis.stop_loss:
        flags.append(FlagCandidate(
            "stop_loss_hit", "critical",
            f"{stock.ticker} at ${current_price:.2f} has hit its stop-loss level of ${ai_analysis.stop_loss:.2f} "
            f"— you're at {pnl_pct:+.1f}% since your ${holding.cost_basis_per_share:.2f} entry. Consider whether to exit.",
        ))

    nearest_target = None
    for target in (ai_analysis.target_3m, ai_analysis.target_6m, ai_analysis.target_1y) if ai_analysis else ():
        if target and current_price >= target:
            nearest_target = target
            break
    if nearest_target:
        flags.append(FlagCandidate(
            "target_reached", "info",
            f"{stock.ticker} at ${current_price:.2f} has reached a price target (${nearest_target:.2f}) — "
            f"you're at {pnl_pct:+.1f}%. Consider whether to take profits or let it run.",
        ))

    if technicals:
        if technicals.rsi14 is not None and technicals.rsi14 >= OVERBOUGHT_RSI and pnl_pct >= LARGE_GAIN_PCT:
            flags.append(FlagCandidate(
                "overbought_trim", "warning",
                f"{stock.ticker} RSI is {technicals.rsi14:.0f} (overbought) and you're up {pnl_pct:.1f}% — "
                "some investors trim into overbought strength rather than chase it further.",
            ))
        if technicals.rsi14 is not None and technicals.rsi14 <= OVERSOLD_RSI:
            flags.append(FlagCandidate(
                "oversold_watch", "info",
                f"{stock.ticker} RSI is {technicals.rsi14:.0f} (oversold) — worth watching for a bounce or further weakness.",
            ))
        if technicals.ma_crossover_signal == "death_cross":
            severity = "critical" if pnl_pct < 0 else "warning"
            flags.append(FlagCandidate(
                "death_cross_risk", severity,
                f"{stock.ticker} just had a death cross (SMA50 below SMA200) — a bearish technical signal. "
                f"You're at {pnl_pct:+.1f}%.",
            ))
        if technicals.ma_crossover_signal == "golden_cross":
            flags.append(FlagCandidate(
                "golden_cross_positive", "info",
                f"{stock.ticker} just had a golden cross (SMA50 above SMA200) — a bullish technical signal.",
            ))

    if recent_news:
        scored = [a.sentiment_score for a in recent_news if a.sentiment_score is not None]
        if scored:
            avg_sentiment = sum(scored) / len(scored)
            high_impact = any(a.impact_score == "high" for a in recent_news)
            if avg_sentiment <= -NEWS_SENTIMENT_THRESHOLD and high_impact:
                flags.append(FlagCandidate(
                    "negative_news_risk", "warning",
                    f"{stock.ticker} has recent negative, high-impact news (avg sentiment {avg_sentiment:.2f} over "
                    f"the last {NEWS_LOOKBACK_DAYS} days) — worth reading before deciding anything.",
                ))
            elif avg_sentiment >= NEWS_SENTIMENT_THRESHOLD and high_impact:
                flags.append(FlagCandidate(
                    "positive_news_upside", "info",
                    f"{stock.ticker} has recent positive, high-impact news (avg sentiment {avg_sentiment:.2f} over "
                    f"the last {NEWS_LOOKBACK_DAYS} days) — potential upside catalyst.",
                ))

    if pnl_pct <= LARGE_UNREALIZED_LOSS_PCT:
        flags.append(FlagCandidate(
            "large_unrealized_loss", "warning",
            f"{stock.ticker} is down {pnl_pct:.1f}% from your ${holding.cost_basis_per_share:.2f} entry — "
            "a large enough loss that it's worth deliberately deciding to hold vs. cut, not just drifting.",
        ))
    elif pnl_pct >= LARGE_UNREALIZED_GAIN_PCT:
        flags.append(FlagCandidate(
            "large_unrealized_gain", "info",
            f"{stock.ticker} is up {pnl_pct:.1f}% from your ${holding.cost_basis_per_share:.2f} entry — "
            "large enough that some investors would consider rebalancing or taking partial profits.",
        ))

    return flags


def evaluate_sector_concentration(holdings_with_values: list[tuple[Stock, float]]) -> tuple[str, FlagCandidate] | None:
    """Portfolio-level (not per-holding) flag: is any one sector too large a share of the
    total portfolio value? ETFs (sector=None) are excluded from this check — a fund's
    actual sector exposure isn't just its own GICS sector, and we don't have look-through
    holdings data to compute that properly.

    Returns (sector_name, flag) rather than just the flag — PortfolioFlag rows need a
    holding_id (no separate portfolio-level flag table for one flag type), so the caller
    attaches this to whichever holding is the largest position in the flagged sector; the
    sector name is what it needs to find that holding."""
    total_value = sum(value for _, value in holdings_with_values)
    if total_value <= 0:
        return None

    sector_totals: dict[str, float] = {}
    for stock, value in holdings_with_values:
        if not stock.sector:
            continue
        sector_totals[stock.sector] = sector_totals.get(stock.sector, 0.0) + value

    for sector, sector_value in sector_totals.items():
        pct = sector_value / total_value * 100
        if pct >= SECTOR_CONCENTRATION_THRESHOLD_PCT:
            flag = FlagCandidate(
                "sector_concentration", "warning",
                f"{pct:.0f}% of your portfolio value is in {sector} — a single-sector downturn would hit "
                "your whole portfolio disproportionately. Worth considering diversification.",
            )
            return sector, flag
    return None


async def persist_flags_if_new(db: AsyncSession, holding_id, as_of: date, candidates: list[FlagCandidate]) -> list[PortfolioFlag]:
    """Only inserts flags that don't already exist for this (holding, flag_type, day) —
    the unique constraint would reject a duplicate anyway, but checking first lets the
    caller know which ones are genuinely new (and therefore worth emailing)."""
    new_rows = []
    for candidate in candidates:
        existing = (
            await db.execute(
                select(PortfolioFlag).where(
                    PortfolioFlag.holding_id == holding_id,
                    PortfolioFlag.flag_type == candidate.flag_type,
                    PortfolioFlag.as_of_date == as_of,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        row = PortfolioFlag(holding_id=holding_id, as_of_date=as_of, flag_type=candidate.flag_type, severity=candidate.severity, message=candidate.message)
        db.add(row)
        new_rows.append(row)
    if new_rows:
        await db.flush()
    return new_rows


async def get_recent_news(db: AsyncSession, stock_id, as_of: date) -> list[NewsArticle]:
    cutoff_date = as_of - timedelta(days=NEWS_LOOKBACK_DAYS)
    cutoff = datetime.combine(cutoff_date, datetime.min.time(), tzinfo=timezone.utc)
    result = await db.execute(select(NewsArticle).where(NewsArticle.stock_id == stock_id, NewsArticle.published_at >= cutoff))
    return list(result.scalars().all())
