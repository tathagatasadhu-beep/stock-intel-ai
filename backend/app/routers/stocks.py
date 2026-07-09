"""GET /stocks/{ticker} — fundamentals + recent candles for a single stock (spec section 5)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import AIAnalysis, FundamentalSnapshot, PriceCandle, Stock
from app.db.session import get_db
from app.models.schemas import AIAnalysisOut, CandleOut, FundamentalsOut, StockSummary

router = APIRouter()


async def _get_stock_or_404(ticker: str, db: AsyncSession) -> Stock:
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
    return stock


async def _latest_fundamentals(stock_id, db: AsyncSession) -> FundamentalSnapshot | None:
    result = await db.execute(
        select(FundamentalSnapshot)
        .where(FundamentalSnapshot.stock_id == stock_id)
        .order_by(FundamentalSnapshot.as_of_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("", response_model=list[StockSummary])
async def list_stocks(q: str | None = None, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Ticker/company-name search — used by the frontend's search box."""
    stmt = select(Stock).where(Stock.is_sp500.is_(True)).limit(limit)
    if q:
        like = f"%{q.upper()}%"
        stmt = select(Stock).where(Stock.ticker.like(like) | Stock.company_name.ilike(f"%{q}%")).limit(limit)
    result = await db.execute(stmt)
    stocks = result.scalars().all()

    out = []
    for stock in stocks:
        fundamentals = await _latest_fundamentals(stock.id, db)
        out.append(
            StockSummary(
                ticker=stock.ticker,
                company_name=stock.company_name,
                sector=stock.sector,
                industry=stock.industry,
                market_cap=stock.market_cap,
                price=fundamentals.price if fundamentals else None,
            )
        )
    return out


@router.get("/{ticker}", response_model=FundamentalsOut)
async def get_stock_fundamentals(ticker: str, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    fundamentals = await _latest_fundamentals(stock.id, db)
    if fundamentals is None:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {ticker} yet — run the ingestion script.")
    return fundamentals


@router.get("/{ticker}/candles", response_model=list[CandleOut])
async def get_stock_candles(ticker: str, days: int = 400, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(PriceCandle).where(PriceCandle.stock_id == stock.id).order_by(PriceCandle.date.desc()).limit(days)
    )
    candles = list(reversed(result.scalars().all()))
    return candles


@router.get("/{ticker}/ai-analysis", response_model=AIAnalysisOut)
async def get_ai_analysis(ticker: str, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(AIAnalysis).where(AIAnalysis.stock_id == stock.id).order_by(AIAnalysis.generated_at.desc()).limit(1)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No AI analysis for {ticker} yet — run the ingestion script.")
    return AIAnalysisOut(
        generated_at=analysis.generated_at,
        bullish_bearish_score=analysis.bullish_bearish_score,
        risk_score=analysis.risk_score,
        investment_thesis=analysis.investment_thesis,
        technical_thesis=analysis.technical_thesis,
        key_risks=[line for line in analysis.key_risks.split("\n") if line.strip()],
        entry_zone_low=analysis.entry_zone_low,
        entry_zone_high=analysis.entry_zone_high,
        stop_loss=analysis.stop_loss,
        target_3m=analysis.target_3m,
        target_6m=analysis.target_6m,
        target_1y=analysis.target_1y,
    )
