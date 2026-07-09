"""GET /news/{ticker} — stored news feed with AI-scored sentiment (spec sections 2.6/5)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import NewsArticle, Stock
from app.db.session import get_db
from app.models.schemas import NewsArticleOut

router = APIRouter()


@router.get("/{ticker}", response_model=list[NewsArticleOut])
async def get_news_for_ticker(ticker: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")

    articles = await db.execute(
        select(NewsArticle).where(NewsArticle.stock_id == stock.id).order_by(NewsArticle.published_at.desc()).limit(limit)
    )
    return articles.scalars().all()
