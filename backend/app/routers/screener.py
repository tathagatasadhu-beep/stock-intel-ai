"""GET /screener — ranked, filterable S&P 500 stock list (spec sections 2.1/5)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import FundamentalSnapshot, ScreenerScore, Stock, TechnicalSnapshot, ValuationResult
from app.db.session import get_db
from app.models.schemas import ScreenerFilters, ScreenerRow

router = APIRouter()


@router.get("", response_model=list[ScreenerRow])
async def run_screener(filters: ScreenerFilters = Depends(), db: AsyncSession = Depends(get_db)):
    # Latest snapshot per stock via a correlated subquery would be more efficient at scale,
    # but S&P 500-sized data (~500 stocks) makes an in-process join-and-filter simple and fast
    # enough — avoids a more complex "latest row per group" SQL pattern for an MVP.
    stmt = select(Stock).where(Stock.is_sp500.is_(True))
    if filters.sector:
        stmt = stmt.where(Stock.sector == filters.sector)
    stocks = (await db.execute(stmt)).scalars().all()

    rows: list[ScreenerRow] = []
    for stock in stocks:
        fundamentals = await _latest(db, FundamentalSnapshot, stock.id, FundamentalSnapshot.as_of_date)
        technicals = await _latest(db, TechnicalSnapshot, stock.id, TechnicalSnapshot.as_of_date)
        score = await _latest(db, ScreenerScore, stock.id, ScreenerScore.as_of_date)
        valuation = await _latest(db, ValuationResult, stock.id, ValuationResult.as_of_date, extra_filter=(ValuationResult.method == "blended"))

        if fundamentals is None or score is None:
            continue
        if not _passes_filters(filters, fundamentals, technicals, valuation, score):
            continue

        rows.append(
            ScreenerRow(
                ticker=stock.ticker,
                company_name=stock.company_name,
                sector=stock.sector,
                price=fundamentals.price,
                market_cap=stock.market_cap,
                pe_ratio=fundamentals.pe_ratio,
                peg_ratio=fundamentals.peg_ratio,
                margin_of_safety_pct=valuation.margin_of_safety_pct if valuation else None,
                revenue_growth_yoy=fundamentals.revenue_growth_yoy,
                roe=fundamentals.roe,
                debt_equity=fundamentals.debt_equity,
                rsi14=technicals.rsi14 if technicals else None,
                macd_hist=technicals.macd_hist if technicals else None,
                valuation_score=score.valuation_score,
                growth_score=score.growth_score,
                financial_health_score=score.financial_health_score,
                technical_score=score.technical_score,
                news_sentiment_score=score.news_sentiment_score,
                composite_score=score.composite_score,
                rating=score.rating,
            )
        )

    reverse = filters.sort_desc
    sort_key = filters.sort_by if hasattr(ScreenerRow, filters.sort_by) else "composite_score"
    rows.sort(key=lambda r: (getattr(r, sort_key) if getattr(r, sort_key) is not None else float("-inf")), reverse=reverse)
    return rows[filters.offset : filters.offset + filters.limit]


async def _latest(db: AsyncSession, model, stock_id, date_col, extra_filter=None):
    stmt = select(model).where(model.stock_id == stock_id).order_by(date_col.desc()).limit(1)
    if extra_filter is not None:
        stmt = select(model).where(model.stock_id == stock_id, extra_filter).order_by(date_col.desc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


def _passes_filters(filters: ScreenerFilters, f: FundamentalSnapshot, t: TechnicalSnapshot | None, v: ValuationResult | None, s: ScreenerScore) -> bool:
    checks = [
        filters.pe_max is None or (f.pe_ratio is not None and f.pe_ratio <= filters.pe_max),
        filters.forward_pe_max is None or (f.forward_pe is not None and f.forward_pe <= filters.forward_pe_max),
        filters.peg_max is None or (f.peg_ratio is not None and f.peg_ratio <= filters.peg_max),
        filters.price_to_book_max is None or (f.price_to_book is not None and f.price_to_book <= filters.price_to_book_max),
        filters.ev_ebitda_max is None or (f.ev_ebitda is not None and f.ev_ebitda <= filters.ev_ebitda_max),
        filters.margin_of_safety_min is None or (v is not None and v.margin_of_safety_pct >= filters.margin_of_safety_min),
        filters.revenue_growth_min is None or (f.revenue_growth_yoy is not None and f.revenue_growth_yoy >= filters.revenue_growth_min),
        filters.eps_growth_min is None or (f.eps_growth is not None and f.eps_growth >= filters.eps_growth_min),
        filters.fcf_growth_min is None or (f.fcf_growth is not None and f.fcf_growth >= filters.fcf_growth_min),
        filters.roe_min is None or (f.roe is not None and f.roe >= filters.roe_min),
        filters.roic_min is None or (f.roic is not None and f.roic >= filters.roic_min),
        filters.debt_equity_max is None or (f.debt_equity is not None and f.debt_equity <= filters.debt_equity_max),
        filters.current_ratio_min is None or (f.current_ratio is not None and f.current_ratio >= filters.current_ratio_min),
        filters.interest_coverage_min is None or (f.interest_coverage is not None and f.interest_coverage >= filters.interest_coverage_min),
        filters.altman_z_min is None or (f.altman_z_score is not None and f.altman_z_score >= filters.altman_z_min),
        filters.rsi_min is None or (t is not None and t.rsi14 is not None and t.rsi14 >= filters.rsi_min),
        filters.rsi_max is None or (t is not None and t.rsi14 is not None and t.rsi14 <= filters.rsi_max),
        not filters.macd_bullish_only or (t is not None and (t.macd_hist or 0) > 0),
        not filters.golden_cross_only or (t is not None and t.ma_crossover_signal == "golden_cross"),
        not filters.near_52w_high or (t is not None and t.week52_breakout == "high"),
        not filters.near_52w_low or (t is not None and t.week52_breakout == "low"),
        not filters.volume_breakout_only or (t is not None and t.volume_breakout),
        filters.min_composite_score is None or s.composite_score >= filters.min_composite_score,
        filters.rating is None or s.rating == filters.rating,
    ]
    return all(checks)
