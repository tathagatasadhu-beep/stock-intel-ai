"""
Daily universe refresh: pulls S&P 500 constituents + fundamentals + price candles from
Financial Modeling Prep, computes technicals/Fibonacci/valuation/composite scores/AI
analysis/news for every ticker, persists all of it, then checks active alerts and emails
any that just triggered.

Run manually: `python scripts/refresh_universe.py`
In production: scheduled as a Render Cron Job / Background Worker (see DEPLOY.md step 3.6).

The actual fetch/compute/score pipeline for one ticker lives in
app/services/ingest.py — this script is just the batch driver around it (concurrency,
daily rotation, alert-checking). See that module's docstring for why it's shared with
the on-demand `POST /api/stocks/{ticker}/refresh` route instead of living only here.

Needs real FMP_API_KEY / OPENAI_API_KEY / FINNHUB_API_KEY in the environment — this is NOT
the local dev path (see dev_server_sqlite.py for that, which seeds fake data instead of
calling any provider).
"""
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.orm import Alert, AppUser, FibonacciLevel, FundamentalSnapshot, Stock, TechnicalSnapshot  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services import email_alerts, ingest, market_data, scoring  # noqa: E402

CONCURRENCY = 5
TODAY = date.today()


async def process_ticker(symbol: str, name: str, sector: str | None, sem: asyncio.Semaphore) -> ingest.IngestResult | None:
    # Each concurrent ticker gets its OWN AsyncSession — SQLAlchemy's AsyncSession is not
    # safe to share across concurrently-running coroutines/tasks. The semaphore bounds how
    # many of these run (and therefore how many provider requests fire) at once; the
    # session itself is still one-per-task.
    async with sem, SessionLocal() as db:
        try:
            result = await ingest.ingest_ticker(db, symbol, name, sector, TODAY)
            await db.commit()
            return result
        except Exception as exc:  # noqa: BLE001 - one bad ticker shouldn't kill the whole run
            await db.rollback()
            print(f"[refresh_universe] {symbol} failed: {exc}")
            return None


async def score_and_analyze(db: AsyncSession, results: list[ingest.IngestResult]) -> None:
    # Batch run has every result in memory already, so it builds a tighter Population
    # directly from this run's results instead of an extra round-trip to the DB (that's
    # what app.services.ingest.build_population_from_db is for — the on-demand single-
    # ticker route, which doesn't have a batch of results sitting in memory).
    pop = scoring.Population()
    for r in results:
        f, t, v = r.fundamentals, r.technicals, r.valuation
        pop.pe_ratio.append(f.pe_ratio)
        pop.forward_pe.append(f.forward_pe)
        pop.peg_ratio.append(f.peg_ratio)
        pop.price_to_book.append(f.price_to_book)
        pop.ev_ebitda.append(f.ev_ebitda)
        pop.margin_of_safety_pct.append(v.margin_of_safety_pct if v else None)
        pop.revenue_growth_yoy.append(f.revenue_growth_yoy)
        pop.eps_growth.append(f.eps_growth)
        pop.fcf_growth.append(f.fcf_growth)
        pop.roe.append(f.roe)
        pop.roic.append(f.roic)
        pop.debt_equity.append(f.debt_equity)
        pop.current_ratio.append(f.current_ratio)
        pop.interest_coverage.append(f.interest_coverage)
        pop.altman_z_score.append(f.altman_z_score)
        pop.macd_hist.append(t.macd_hist if t else None)

    for r in results:
        await ingest.score_and_analyze_one(db, r, pop, TODAY)
    await db.commit()


async def check_and_send_alerts(db: AsyncSession) -> None:
    result = await db.execute(select(Alert).where(Alert.is_active.is_(True)))
    alerts = result.scalars().all()
    for alert in alerts:
        # Only trigger once per calendar day per alert to avoid duplicate emails on
        # sequential runs.
        if alert.last_triggered_at and alert.last_triggered_at.date() == TODAY:
            continue

        stock_result = await db.execute(select(Stock).where(Stock.id == alert.stock_id))
        stock = stock_result.scalar_one_or_none()
        if stock is None:
            continue

        triggered, message = await _evaluate_alert(db, alert, stock)
        if not triggered:
            continue

        alert.last_triggered_at = datetime.now(timezone.utc)
        db.add(alert)

        if alert.delivery_method == "email":
            user_result = await db.execute(select(AppUser).where(AppUser.id == alert.user_id))
            user = user_result.scalar_one_or_none()
            if user and settings.smtp_host:
                try:
                    email_alerts.send_alert_email(user.email, stock.ticker, alert.alert_type, message)
                except Exception as exc:  # noqa: BLE001
                    print(f"[refresh_universe] failed to email alert {alert.id}: {exc}")
    await db.commit()


async def _evaluate_alert(db: AsyncSession, alert: Alert, stock: Stock) -> tuple[bool, str]:
    tech_result = await db.execute(
        select(TechnicalSnapshot).where(TechnicalSnapshot.stock_id == stock.id).order_by(TechnicalSnapshot.as_of_date.desc()).limit(1)
    )
    t = tech_result.scalar_one_or_none()
    fund_result = await db.execute(
        select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id).order_by(FundamentalSnapshot.as_of_date.desc()).limit(1)
    )
    f = fund_result.scalar_one_or_none()
    fib_result = await db.execute(
        select(FibonacciLevel).where(FibonacciLevel.stock_id == stock.id).order_by(FibonacciLevel.as_of_date.desc()).limit(1)
    )
    fib = fib_result.scalar_one_or_none()

    if t is None or f is None:
        return False, ""

    if alert.alert_type == "rsi_oversold" and t.rsi14 is not None and t.rsi14 < (alert.threshold_value or 30):
        return True, f"{stock.ticker} RSI is {t.rsi14:.1f}, below your threshold of {alert.threshold_value or 30}."
    if alert.alert_type == "rsi_overbought" and t.rsi14 is not None and t.rsi14 > (alert.threshold_value or 70):
        return True, f"{stock.ticker} RSI is {t.rsi14:.1f}, above your threshold of {alert.threshold_value or 70}."
    if alert.alert_type == "macd_bullish_cross" and t.ma_crossover_signal == "golden_cross":
        return True, f"{stock.ticker} just had a golden cross (SMA50 crossed above SMA200)."
    if alert.alert_type == "volume_spike" and t.volume_breakout:
        return True, f"{stock.ticker} volume is a breakout above its 20-day average."
    if alert.alert_type == "price_below_support" and fib and fib.nearest_support and f.price <= fib.nearest_support:
        return True, f"{stock.ticker} price {f.price:.2f} has crossed below its nearest Fibonacci support of {fib.nearest_support:.2f}."
    if alert.alert_type == "price_above_resistance" and fib and fib.nearest_resistance and f.price >= fib.nearest_resistance:
        return True, f"{stock.ticker} price {f.price:.2f} has crossed above its nearest Fibonacci resistance of {fib.nearest_resistance:.2f}."
    return False, ""


async def main():
    async with engine.begin() as conn:
        from app.db.orm import Base

        await conn.run_sync(Base.metadata.create_all)

    constituents = await market_data.get_sp500_constituents()
    print(f"[refresh_universe] {len(constituents)} S&P 500 constituents")

    # Rotate the starting point daily so a quota-limited run (see CLAUDE.md -> FMP
    # quota) makes cumulative progress across the whole universe instead of always
    # succeeding on the same tickers at the front of the list and never reaching the
    # rest. Deterministic on the date, so re-running this script twice in one day
    # (e.g. a manual retry) hits the same order rather than shuffling randomly.
    offset = date.today().toordinal() % len(constituents)
    constituents = constituents[offset:] + constituents[:offset]
    print(f"[refresh_universe] starting from offset {offset} ({constituents[0]['symbol']}) to spread FMP quota usage across the universe over time")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [process_ticker(c["symbol"], c["name"], c["sector"], sem) for c in constituents]
    results = [r for r in await asyncio.gather(*tasks) if r]

    print(f"[refresh_universe] fundamentals/technicals computed for {len(results)} tickers")
    async with SessionLocal() as db:
        await score_and_analyze(db, results)
        await check_and_send_alerts(db)

    print("[refresh_universe] done")


if __name__ == "__main__":
    asyncio.run(main())
