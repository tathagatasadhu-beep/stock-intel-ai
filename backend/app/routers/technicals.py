"""GET /technicals/{ticker} — latest indicator snapshot, full time series for charting, and
auto Fibonacci retracement levels (spec sections 2.3/2.4/5)."""
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import FibonacciLevel, PriceCandle, Stock, TechnicalSnapshot
from app.db.session import get_db
from app.models.schemas import FibonacciOut, TechnicalsOut
from app.services import fibonacci as fib_service
from app.services import technicals as tech_service

router = APIRouter()


async def _get_stock_or_404(ticker: str, db: AsyncSession) -> Stock:
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
    return stock


async def _candles_arrays(stock_id, db: AsyncSession):
    result = await db.execute(select(PriceCandle).where(PriceCandle.stock_id == stock_id).order_by(PriceCandle.date.asc()))
    candles = result.scalars().all()
    if not candles:
        return None
    return {
        "dates": [c.date for c in candles],
        "open": np.array([c.open for c in candles], dtype=float),
        "high": np.array([c.high for c in candles], dtype=float),
        "low": np.array([c.low for c in candles], dtype=float),
        "close": np.array([c.close for c in candles], dtype=float),
        "volume": np.array([c.volume for c in candles], dtype=float),
    }


@router.get("/{ticker}", response_model=TechnicalsOut)
async def get_latest_technicals(ticker: str, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(TechnicalSnapshot).where(TechnicalSnapshot.stock_id == stock.id).order_by(TechnicalSnapshot.as_of_date.desc()).limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No technicals for {ticker} yet — run the ingestion script.")
    return snapshot


@router.get("/{ticker}/series")
async def get_technicals_series(ticker: str, db: AsyncSession = Depends(get_db)):
    """Full time series for chart overlays — computed on demand from stored candles
    rather than persisted, since a chart needs every day's value, not just the latest."""
    stock = await _get_stock_or_404(ticker, db)
    arrays = await _candles_arrays(stock.id, db)
    if arrays is None:
        raise HTTPException(status_code=404, detail=f"No price history for {ticker} yet — run the ingestion script.")

    sma20 = tech_service.sma(arrays["close"], 20)
    sma50 = tech_service.sma(arrays["close"], 50)
    sma200 = tech_service.sma(arrays["close"], 200)
    bb = tech_service.bollinger_bands(arrays["close"], 20)
    vwap = tech_service.rolling_vwap(arrays["high"], arrays["low"], arrays["close"], arrays["volume"])
    rsi = tech_service.rsi(arrays["close"])
    macd = tech_service.macd(arrays["close"])
    atr = tech_service.atr(arrays["high"], arrays["low"], arrays["close"])
    obv = tech_service.obv(arrays["close"], arrays["volume"])
    stoch_rsi = tech_service.stochastic_rsi(arrays["close"])

    def series(values: np.ndarray) -> list[float | None]:
        return [None if np.isnan(v) else round(float(v), 4) for v in values]

    dates = [d.isoformat() for d in arrays["dates"]]
    return {
        "dates": dates,
        "sma20": series(sma20),
        "sma50": series(sma50),
        "sma200": series(sma200),
        "bollinger_upper": series(bb.upper),
        "bollinger_mid": series(bb.mid),
        "bollinger_lower": series(bb.lower),
        "vwap": series(vwap),
        "rsi14": series(rsi),
        "macd": series(macd.macd),
        "macd_signal": series(macd.signal),
        "macd_hist": series(macd.hist),
        "atr14": series(atr),
        "obv": series(obv),
        "stoch_rsi": series(stoch_rsi),
    }


@router.get("/{ticker}/fibonacci", response_model=FibonacciOut)
async def get_fibonacci(ticker: str, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(FibonacciLevel).where(FibonacciLevel.stock_id == stock.id).order_by(FibonacciLevel.as_of_date.desc()).limit(1)
    )
    level = result.scalar_one_or_none()
    if level is None:
        raise HTTPException(status_code=404, detail=f"No Fibonacci levels for {ticker} yet — run the ingestion script.")
    return level
