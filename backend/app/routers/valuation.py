"""GET /valuation/{ticker} — Intrinsic Value Engine (spec section 2.2/5). Computed live from
the latest stored fundamentals so a user can experiment with WACC/growth-rate inputs without
waiting for the next ingestion run."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.orm import FundamentalSnapshot, Stock
from app.db.session import get_db
from app.models.schemas import ValuationInputs, ValuationMethodResult, ValuationOut
from app.services import valuation as valuation_service

router = APIRouter()


async def _get_stock_or_404(ticker: str, db: AsyncSession) -> Stock:
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
    return stock


async def _peer_avg_pe(sector: str | None, exclude_stock_id, db: AsyncSession) -> float | None:
    if not sector:
        return None
    result = await db.execute(
        select(FundamentalSnapshot.pe_ratio)
        .join(Stock, Stock.id == FundamentalSnapshot.stock_id)
        .where(Stock.sector == sector, Stock.id != exclude_stock_id, FundamentalSnapshot.pe_ratio.is_not(None))
    )
    pes = [row[0] for row in result.all() if row[0] and row[0] > 0]
    return round(sum(pes) / len(pes), 2) if pes else None


@router.get("/{ticker}", response_model=ValuationOut)
async def get_valuation(
    ticker: str,
    wacc: float = Query(default=settings.default_wacc, ge=0.01, le=0.5),
    fcf_growth_rate: float = Query(default=settings.default_fcf_growth_rate, ge=-0.5, le=1.0),
    terminal_growth_rate: float = Query(default=settings.default_terminal_growth_rate, ge=0.0, le=0.10),
    projection_years: int = Query(default=settings.default_projection_years, ge=1, le=15),
    db: AsyncSession = Depends(get_db),
):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id).order_by(FundamentalSnapshot.as_of_date.desc()).limit(1)
    )
    f = result.scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail=f"No fundamentals for {ticker} yet — run the ingestion script.")

    peer_avg_pe = await _peer_avg_pe(stock.sector, stock.id, db)

    dcf = valuation_service.dcf_valuation(
        f.free_cash_flow, f.shares_outstanding, f.total_debt, f.cash_and_equivalents,
        wacc, fcf_growth_rate, terminal_growth_rate, projection_years,
    )
    ddm = valuation_service.ddm_valuation(f.dividend_per_share, wacc, fcf_growth_rate)
    owner_earnings = valuation_service.owner_earnings_valuation(f.eps, wacc, fcf_growth_rate)
    comparable = valuation_service.comparable_valuation(f.eps, peer_avg_pe)

    method_results = [dcf, ddm, owner_earnings, comparable]
    blended = valuation_service.blended_intrinsic_value(method_results)

    results = [
        ValuationMethodResult(
            method=r.method,
            intrinsic_value=r.intrinsic_value,
            current_price=f.price,
            margin_of_safety_pct=valuation_service.margin_of_safety_pct(r.intrinsic_value, f.price),
            notes=r.notes,
        )
        for r in method_results
    ]

    return ValuationOut(
        as_of_date=date.today(),
        inputs=ValuationInputs(
            wacc=wacc, fcf_growth_rate=fcf_growth_rate, terminal_growth_rate=terminal_growth_rate, projection_years=projection_years
        ),
        results=results,
        blended_intrinsic_value=blended,
    )
