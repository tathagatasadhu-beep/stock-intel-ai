"""
Composite Investment Score (spec section 6):
    30% Valuation + 25% Growth + 20% Financial Health + 15% Technicals + 10% News Sentiment
    90-100 Strong Buy | 75-89 Buy | 60-74 Hold | 40-59 Weak Hold | <40 Avoid

Each category sub-score is a 0-100 **percentile rank within the current S&P 500 universe**
being screened, not an absolute threshold — this is standard screener behavior (Finviz/
TradingView rank stocks relative to their peer set) and avoids having to hand-pick "a P/E of
X is good" cutoffs that would go stale as the market re-rates. scripts/refresh_universe.py
builds the `Population` below once per run from every stock's latest fundamentals/technicals,
then calls these functions once per stock.
"""
from dataclasses import dataclass, field


@dataclass
class Population:
    """All-stocks-in-universe values for each metric, gathered once per refresh run."""

    pe_ratio: list[float | None] = field(default_factory=list)
    forward_pe: list[float | None] = field(default_factory=list)
    peg_ratio: list[float | None] = field(default_factory=list)
    price_to_book: list[float | None] = field(default_factory=list)
    ev_ebitda: list[float | None] = field(default_factory=list)
    margin_of_safety_pct: list[float | None] = field(default_factory=list)

    revenue_growth_yoy: list[float | None] = field(default_factory=list)
    eps_growth: list[float | None] = field(default_factory=list)
    fcf_growth: list[float | None] = field(default_factory=list)
    roe: list[float | None] = field(default_factory=list)
    roic: list[float | None] = field(default_factory=list)

    debt_equity: list[float | None] = field(default_factory=list)
    current_ratio: list[float | None] = field(default_factory=list)
    interest_coverage: list[float | None] = field(default_factory=list)
    altman_z_score: list[float | None] = field(default_factory=list)

    macd_hist: list[float | None] = field(default_factory=list)


def percentile_rank(value: float | None, population: list[float | None], higher_is_better: bool) -> float | None:
    if value is None:
        return None
    pop = [p for p in population if p is not None]
    if not pop:
        return 50.0
    rank = sum(1 for p in pop if (p <= value if higher_is_better else p >= value)) / len(pop)
    return round(rank * 100, 1)


def _avg(scores: list[float | None], default: float = 50.0) -> float:
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals), 1) if vals else default


def compute_valuation_score(
    pe_ratio: float | None,
    forward_pe: float | None,
    peg_ratio: float | None,
    price_to_book: float | None,
    ev_ebitda: float | None,
    margin_of_safety_pct: float | None,
    pop: Population,
) -> float:
    scores = [
        percentile_rank(pe_ratio, pop.pe_ratio, higher_is_better=False),
        percentile_rank(forward_pe, pop.forward_pe, higher_is_better=False),
        percentile_rank(peg_ratio, pop.peg_ratio, higher_is_better=False),
        percentile_rank(price_to_book, pop.price_to_book, higher_is_better=False),
        percentile_rank(ev_ebitda, pop.ev_ebitda, higher_is_better=False),
        percentile_rank(margin_of_safety_pct, pop.margin_of_safety_pct, higher_is_better=True),
    ]
    return _avg(scores)


def compute_growth_score(
    revenue_growth_yoy: float | None,
    eps_growth: float | None,
    fcf_growth: float | None,
    roe: float | None,
    roic: float | None,
    pop: Population,
) -> float:
    scores = [
        percentile_rank(revenue_growth_yoy, pop.revenue_growth_yoy, higher_is_better=True),
        percentile_rank(eps_growth, pop.eps_growth, higher_is_better=True),
        percentile_rank(fcf_growth, pop.fcf_growth, higher_is_better=True),
        percentile_rank(roe, pop.roe, higher_is_better=True),
        percentile_rank(roic, pop.roic, higher_is_better=True),
    ]
    return _avg(scores)


def compute_financial_health_score(
    debt_equity: float | None,
    current_ratio: float | None,
    interest_coverage: float | None,
    altman_z_score: float | None,
    pop: Population,
) -> float:
    scores = [
        percentile_rank(debt_equity, pop.debt_equity, higher_is_better=False),
        percentile_rank(current_ratio, pop.current_ratio, higher_is_better=True),
        percentile_rank(interest_coverage, pop.interest_coverage, higher_is_better=True),
        percentile_rank(altman_z_score, pop.altman_z_score, higher_is_better=True),
    ]
    return _avg(scores)


def compute_technical_score(
    rsi14: float | None,
    macd_hist: float | None,
    ma_crossover_signal: str | None,
    volume_breakout: bool,
    week52_breakout: str | None,
    pop: Population,
) -> float:
    # RSI: score peaks in the 40-65 "neutral-to-bullish, not yet overbought" zone and
    # decays toward the extremes (deeply oversold or overbought). Heuristic, not a
    # percentile rank, since "good RSI" isn't population-relative the way a P/E is.
    rsi_score = None
    if rsi14 is not None:
        if 40 <= rsi14 <= 65:
            rsi_score = 100.0
        elif rsi14 < 40:
            rsi_score = max(0.0, 100 - (40 - rsi14) * 2.5)  # oversold territory below 40
        else:
            rsi_score = max(0.0, 100 - (rsi14 - 65) * 2.5)  # overbought territory above 65

    macd_score = percentile_rank(macd_hist, pop.macd_hist, higher_is_better=True)
    crossover_score = {"golden_cross": 100.0, "none": 50.0, "death_cross": 0.0}.get(ma_crossover_signal or "none", 50.0)
    breakout_score = 70.0 if volume_breakout else 50.0
    week52_score = {"high": 80.0, "none": 50.0, "low": 20.0}.get(week52_breakout or "none", 50.0)

    return _avg([rsi_score, macd_score, crossover_score, breakout_score, week52_score])


def compute_news_sentiment_score(sentiment_scores: list[float], impact_scores: list[str]) -> float:
    """Average recent article sentiment (-1..1 -> 0..100), weighted by impact."""
    if not sentiment_scores:
        return 50.0
    weight_map = {"high": 3, "medium": 2, "low": 1}
    total_weight = 0.0
    weighted_sum = 0.0
    for sentiment, impact in zip(sentiment_scores, impact_scores or ["medium"] * len(sentiment_scores)):
        w = weight_map.get(impact, 2)
        weighted_sum += ((sentiment + 1) / 2 * 100) * w
        total_weight += w
    return round(weighted_sum / total_weight, 1) if total_weight else 50.0


def compute_composite_score(
    valuation_score: float, growth_score: float, financial_health_score: float, technical_score: float, news_sentiment_score: float
) -> float:
    return round(
        0.30 * valuation_score
        + 0.25 * growth_score
        + 0.20 * financial_health_score
        + 0.15 * technical_score
        + 0.10 * news_sentiment_score,
        1,
    )


def rating_for_score(composite_score: float) -> str:
    if composite_score >= 90:
        return "Strong Buy"
    if composite_score >= 75:
        return "Buy"
    if composite_score >= 60:
        return "Hold"
    if composite_score >= 40:
        return "Weak Hold"
    return "Avoid"
