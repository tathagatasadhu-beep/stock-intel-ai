"""POST/GET/DELETE /alerts — user-owned alert rules (spec section 3). Delivery is checked
by scripts/refresh_universe.py after each data refresh (see that script's final step);
only email delivery is wired up in this MVP (see CLAUDE.md -> deferred scope)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import Alert, AppUser, Stock
from app.db.session import get_db
from app.models.schemas import AlertCreate, AlertOut
from app.routers.auth import get_or_create_app_user

router = APIRouter()

_VALID_ALERT_TYPES = {
    "price_below_support", "price_above_resistance", "macd_bullish_cross", "macd_bearish_cross",
    "rsi_oversold", "rsi_overbought", "volume_spike", "breaking_news", "analyst_upgrade", "analyst_downgrade",
}


def _to_out(alert: Alert, ticker: str) -> AlertOut:
    return AlertOut(
        id=str(alert.id),
        ticker=ticker,
        alert_type=alert.alert_type,
        threshold_value=alert.threshold_value,
        delivery_method=alert.delivery_method,
        is_active=alert.is_active,
        last_triggered_at=alert.last_triggered_at,
        created_at=alert.created_at,
    )


@router.get("", response_model=list[AlertOut])
async def list_alerts(user: AppUser = Depends(get_or_create_app_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert, Stock.ticker).join(Stock, Stock.id == Alert.stock_id).where(Alert.user_id == user.id))
    return [_to_out(alert, ticker) for alert, ticker in result.all()]


@router.post("", response_model=AlertOut, status_code=201)
async def create_alert(body: AlertCreate, user: AppUser = Depends(get_or_create_app_user), db: AsyncSession = Depends(get_db)):
    if body.alert_type not in _VALID_ALERT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown alert_type. Must be one of: {sorted(_VALID_ALERT_TYPES)}")

    result = await db.execute(select(Stock).where(Stock.ticker == body.ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {body.ticker}")

    alert = Alert(
        user_id=user.id,
        stock_id=stock.id,
        alert_type=body.alert_type,
        threshold_value=body.threshold_value,
        delivery_method=body.delivery_method,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return _to_out(alert, stock.ticker)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(alert_id: str, user: AppUser = Depends(get_or_create_app_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == uuid.UUID(alert_id), Alert.user_id == user.id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    await db.delete(alert)
    await db.commit()
