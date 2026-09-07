"""GET/POST /portfolio, DELETE /portfolio/holdings/{id} — user-owned stock/ETF positions
with live price, unrealized P&L, and monitoring flags (see services/portfolio_monitor.py).
Auth-gated the same way as Alerts (see routers/auth.py::get_or_create_app_user)."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import AppUser, FundamentalSnapshot, PortfolioFlag, PortfolioHolding, ScreenerScore, Stock
from app.db.session import get_db
from app.models.schemas import PortfolioFlagOut, PortfolioHoldingCreate, PortfolioHoldingOut, PortfolioSummaryOut
from app.routers.auth import get_or_create_app_user
from app.services import ingest, market_data
from app.services.sp500_universe import SP500_UNIVERSE

router = APIRouter()

_UNIVERSE_BY_SYMBOL = {row["symbol"]: row for row in SP500_UNIVERSE}


async def _build_holding_out(db: AsyncSession, holding: PortfolioHolding, stock: Stock) -> PortfolioHoldingOut:
    fundamentals = (
        await db.execute(select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id).order_by(FundamentalSnapshot.as_of_date.desc()).limit(1))
    ).scalar_one_or_none()
    score = (
        await db.execute(select(ScreenerScore).where(ScreenerScore.stock_id == stock.id).order_by(ScreenerScore.as_of_date.desc()).limit(1))
    ).scalar_one_or_none()
    flag_rows = (
        await db.execute(select(PortfolioFlag).where(PortfolioFlag.holding_id == holding.id).order_by(PortfolioFlag.created_at.desc()).limit(20))
    ).scalars().all()

    current_price = fundamentals.price if fundamentals else None
    market_value = current_price * holding.quantity if current_price is not None else None
    cost_total = holding.cost_basis_per_share * holding.quantity
    unrealized_pnl = (market_value - cost_total) if market_value is not None else None
    unrealized_pnl_pct = (
        (current_price - holding.cost_basis_per_share) / holding.cost_basis_per_share * 100 if current_price is not None else None
    )

    return PortfolioHoldingOut(
        id=str(holding.id),
        ticker=stock.ticker,
        company_name=stock.company_name,
        sector=stock.sector,
        asset_type=stock.asset_type,
        quantity=holding.quantity,
        cost_basis_per_share=holding.cost_basis_per_share,
        current_price=current_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        composite_score=score.composite_score if score else None,
        rating=score.rating if score else None,
        flags=[
            PortfolioFlagOut(flag_type=f.flag_type, severity=f.severity, message=f.message, as_of_date=f.as_of_date, created_at=f.created_at)
            for f in flag_rows
        ],
        created_at=holding.created_at,
    )


@router.get("", response_model=PortfolioSummaryOut)
async def get_portfolio(user: AppUser = Depends(get_or_create_app_user), db: AsyncSession = Depends(get_db)):
    holdings = (await db.execute(select(PortfolioHolding).where(PortfolioHolding.user_id == user.id))).scalars().all()

    outs: list[PortfolioHoldingOut] = []
    for holding in holdings:
        stock = (await db.execute(select(Stock).where(Stock.id == holding.stock_id))).scalar_one()
        outs.append(await _build_holding_out(db, holding, stock))

    total_cost_basis = sum(o.cost_basis_per_share * o.quantity for o in outs)

    # Totals below are computed only over holdings with a known current price — an
    # unpriced holding (not refreshed yet) is excluded rather than treated as $0, so the
    # total doesn't look like a fake loss for a position that simply hasn't loaded yet.
    priced = [o for o in outs if o.market_value is not None]
    total_market_value = sum(o.market_value for o in priced) if priced else None
    priced_cost_basis = sum(o.cost_basis_per_share * o.quantity for o in priced)
    total_unrealized_pnl = (total_market_value - priced_cost_basis) if total_market_value is not None else None
    total_unrealized_pnl_pct = (total_unrealized_pnl / priced_cost_basis * 100) if (total_unrealized_pnl is not None and priced_cost_basis) else None

    return PortfolioSummaryOut(
        total_cost_basis=total_cost_basis,
        total_market_value=total_market_value,
        total_unrealized_pnl=total_unrealized_pnl,
        total_unrealized_pnl_pct=total_unrealized_pnl_pct,
        holdings=outs,
    )


@router.post("/holdings", response_model=PortfolioHoldingOut, status_code=201)
async def add_holding(body: PortfolioHoldingCreate, user: AppUser = Depends(get_or_create_app_user), db: AsyncSession = Depends(get_db)):
    ticker = body.ticker.upper()

    universe_row = _UNIVERSE_BY_SYMBOL.get(ticker)
    if universe_row:
        name, sector, is_sp500 = universe_row["name"], universe_row["sector"], True
    else:
        # Not in our curated stock universe (an ETF, or a stock outside the ~467 list) —
        # confirm it's a real, quotable ticker via Finnhub before creating anything.
        data = await market_data.get_fundamentals(ticker)
        if data is None:
            raise HTTPException(status_code=400, detail=f"Couldn't find a live quote for {ticker} — check the ticker symbol.")
        name, sector, is_sp500 = ticker, None, False

    stock = await ingest.upsert_stock(db, ticker, name, sector, asset_type=body.asset_type, is_sp500=is_sp500)

    existing = (
        await db.execute(select(PortfolioHolding).where(PortfolioHolding.user_id == user.id, PortfolioHolding.stock_id == stock.id))
    ).scalar_one_or_none()
    if existing is not None:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"You already have a holding for {ticker} — delete it first if you want to change it.")

    holding = PortfolioHolding(user_id=user.id, stock_id=stock.id, quantity=body.quantity, cost_basis_per_share=body.cost_basis_per_share)
    db.add(holding)
    await db.commit()
    await db.refresh(holding)

    # Best-effort immediate ingestion so the holding shows real data right away instead
    # of waiting for tomorrow's batch — same pipeline as POST /api/stocks/{ticker}/refresh,
    # just triggered here too since adding a holding is an equally good moment to ask for
    # it. A provider hiccup here shouldn't block the holding from being created — worst
    # case it just shows null price/P&L until the next refresh.
    already_current = (
        await db.execute(select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id, FundamentalSnapshot.as_of_date == date.today()))
    ).scalar_one_or_none()
    if already_current is None:
        try:
            result = await ingest.ingest_ticker(db, ticker, name, sector, date.today(), asset_type=body.asset_type, is_sp500=is_sp500)
            if result is not None:
                pop = await ingest.build_population_from_db(db, date.today())
                await ingest.score_and_analyze_one(db, result, pop, date.today())
            await db.commit()
        except Exception:  # noqa: BLE001 - holding is already created; this is a nice-to-have, not required
            await db.rollback()

    return await _build_holding_out(db, holding, stock)


@router.delete("/holdings/{holding_id}", status_code=204)
async def delete_holding(holding_id: str, user: AppUser = Depends(get_or_create_app_user), db: AsyncSession = Depends(get_db)):
    holding = (
        await db.execute(select(PortfolioHolding).where(PortfolioHolding.id == uuid.UUID(holding_id), PortfolioHolding.user_id == user.id))
    ).scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found.")
    await db.delete(holding)
    await db.commit()
