"""
Daily universe refresh: pulls S&P 500 constituents + fundamentals (Finnhub) + price
candles (FMP) + computes technicals/Fibonacci/valuation/composite scores/AI analysis/
news for every ticker, persists all of it, then checks active alerts and emails any
that just triggered.

Processes services/sp500_universe.py::CORE_TICKERS (a small always-fresh set) first, as
its own fully-awaited batch, before spending any remaining FMP quota rotating through
the rest of the ~467-ticker universe — see that list's comment for why. The screener is
built around this: most days it'll mainly show the core set plus whatever else users
have on-demand-refreshed (POST /api/stocks/{ticker}/refresh) rather than the full index.

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
from app.db.migrate import ensure_schema  # noqa: E402
from app.db.orm import (  # noqa: E402
    AIAnalysis,
    Alert,
    AppUser,
    FibonacciLevel,
    FundamentalSnapshot,
    PortfolioHolding,
    Stock,
    TechnicalSnapshot,
)
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services import email_alerts, ingest, market_data, portfolio_monitor, scoring  # noqa: E402
from app.services.sp500_universe import CORE_TICKERS  # noqa: E402

CONCURRENCY = 5
TODAY = date.today()
# FMP's free tier caps out around 250 calls/day (1 call/ticker for candles). The priority
# tier (CORE_TICKERS + portfolio holdings) already claims its share first and is small
# (~10-20 tickers), but the long-tail pass used to attempt all ~450+ remaining tickers
# unconditionally every run — burning the ENTIRE day's remaining quota on the batch job
# itself, so even a same-day on-demand refresh for an already-core ticker could land after
# quota was gone. Capping the long tail leaves real headroom for on-demand fetches; the
# daily rotation offset (below) still guarantees cumulative progress through the full
# universe over multiple days.
MAX_LONG_TAIL_PER_RUN = 150


async def process_ticker(
    symbol: str, name: str, sector: str | None, sem: asyncio.Semaphore, asset_type: str = "stock", is_sp500: bool = True,
) -> ingest.IngestResult | None:
    # Each concurrent ticker gets its OWN AsyncSession — SQLAlchemy's AsyncSession is not
    # safe to share across concurrently-running coroutines/tasks. The semaphore bounds how
    # many of these run (and therefore how many provider requests fire) at once; the
    # session itself is still one-per-task.
    async with sem, SessionLocal() as db:
        try:
            result = await ingest.ingest_ticker(db, symbol, name, sector, TODAY, asset_type=asset_type, is_sp500=is_sp500)
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
    # Same schema-repair helper the web service runs on its own startup (app/main.py) —
    # see app/db/migrate.py for why both need to run it independently.
    await ensure_schema(engine)

    constituents = await market_data.get_sp500_constituents()
    print(f"[refresh_universe] {len(constituents)} S&P 500 constituents")

    async with SessionLocal() as db:
        portfolio_symbols = await ingest.get_portfolio_ticker_symbols(db)
        universe_symbols = {c["symbol"] for c in constituents}
        non_universe_portfolio_stocks = await ingest.get_non_universe_portfolio_stocks(db, universe_symbols)

    # Priority tier = CORE_TICKERS (services/sp500_universe.py) UNION every distinct
    # ticker any user actually holds in their portfolio (services/ingest.py ->
    # get_portfolio_ticker_symbols) — processed as its own sequential-then-awaited batch,
    # fully completing before the broader universe pass even starts. This guarantees them
    # first claim on today's FMP quota rather than just a statistical edge from list order
    # under concurrency. Real positions get the same always-fresh guarantee as the fixed
    # core set (see CLAUDE.md -> "Portfolio holdings join the priority tier").
    priority_symbols = set(CORE_TICKERS) | portfolio_symbols
    priority_constituents = [
        {"symbol": c["symbol"], "name": c["name"], "sector": c["sector"], "asset_type": "stock", "is_sp500": True}
        for c in constituents
        if c["symbol"] in priority_symbols
    ]
    # Portfolio tickers outside the static universe entirely (ETFs, or a stock outside
    # the curated ~467) — their name/sector/asset_type were already set when the holding
    # was created (routers/portfolio.py), so no extra provider call is needed to list them.
    priority_constituents += [
        {"symbol": s.ticker, "name": s.company_name, "sector": s.sector, "asset_type": s.asset_type, "is_sp500": False}
        for s in non_universe_portfolio_stocks
    ]

    rest_constituents = [
        {"symbol": c["symbol"], "name": c["name"], "sector": c["sector"], "asset_type": "stock", "is_sp500": True}
        for c in constituents
        if c["symbol"] not in priority_symbols
    ]

    # Rotate the starting point of the REST of the universe daily so any quota left over
    # after the priority tier makes cumulative progress across the long tail instead of
    # always succeeding on the same tickers at the front of the list. Deterministic on
    # the date, so re-running this script twice in one day (e.g. a manual retry) hits the
    # same order rather than shuffling randomly.
    offset = date.today().toordinal() % len(rest_constituents)
    rest_constituents = rest_constituents[offset:] + rest_constituents[:offset]
    rest_constituents = rest_constituents[:MAX_LONG_TAIL_PER_RUN]
    print(f"[refresh_universe] {len(priority_constituents)} priority tickers (core + portfolio) first, then long-tail offset {offset} ({rest_constituents[0]['symbol']}), capped at {MAX_LONG_TAIL_PER_RUN}")

    sem = asyncio.Semaphore(CONCURRENCY)
    priority_tasks = [process_ticker(c["symbol"], c["name"], c["sector"], sem, c["asset_type"], c["is_sp500"]) for c in priority_constituents]
    priority_results = [r for r in await asyncio.gather(*priority_tasks) if r]
    print(f"[refresh_universe] priority tier: {len(priority_results)}/{len(priority_constituents)} refreshed")

    rest_tasks = [process_ticker(c["symbol"], c["name"], c["sector"], sem, c["asset_type"], c["is_sp500"]) for c in rest_constituents]
    rest_results = [r for r in await asyncio.gather(*rest_tasks) if r]

    results = priority_results + rest_results
    print(f"[refresh_universe] fundamentals/technicals computed for {len(results)} tickers total")
    refreshed_stock_ids = {r.stock.id for r in results}
    async with SessionLocal() as db:
        await score_and_analyze(db, results)
        await check_and_send_alerts(db)
        await monitor_portfolios(db, refreshed_stock_ids)

    print("[refresh_universe] done")


async def monitor_portfolios(db: AsyncSession, refreshed_stock_ids: set) -> None:
    """Evaluates flags for every holding whose stock was refreshed in this run, plus a
    portfolio-level sector-concentration check across each user's full holdings (not
    just today's refreshed subset — concentration doesn't care whether a position's
    price is from today or a few days ago). Emails one digest per user for whatever's
    newly flagged today. See services/portfolio_monitor.py for the flag rules."""
    user_ids = {r[0] for r in (await db.execute(select(PortfolioHolding.user_id).distinct())).all()}

    for user_id in user_ids:
        holdings = (await db.execute(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id))).scalars().all()
        if not holdings:
            continue

        holdings_with_values: list[tuple[PortfolioHolding, Stock, float]] = []
        new_flags_for_email: list[tuple[str, str, str]] = []  # (ticker, severity, message)

        for holding in holdings:
            stock = (await db.execute(select(Stock).where(Stock.id == holding.stock_id))).scalar_one_or_none()
            if stock is None:
                continue
            fundamentals = (
                await db.execute(select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id).order_by(FundamentalSnapshot.as_of_date.desc()).limit(1))
            ).scalar_one_or_none()
            if fundamentals is None:
                continue
            holdings_with_values.append((holding, stock, fundamentals.price * holding.quantity))

            if stock.id not in refreshed_stock_ids:
                continue  # stale price — don't re-evaluate technical/news flags off old data

            technicals = (
                await db.execute(select(TechnicalSnapshot).where(TechnicalSnapshot.stock_id == stock.id).order_by(TechnicalSnapshot.as_of_date.desc()).limit(1))
            ).scalar_one_or_none()
            ai_analysis = (
                await db.execute(select(AIAnalysis).where(AIAnalysis.stock_id == stock.id).order_by(AIAnalysis.generated_at.desc()).limit(1))
            ).scalar_one_or_none()
            recent_news = await portfolio_monitor.get_recent_news(db, stock.id, TODAY)

            candidates = portfolio_monitor.evaluate_holding(holding, stock, fundamentals.price, technicals, ai_analysis, recent_news)
            new_rows = await portfolio_monitor.persist_flags_if_new(db, holding.id, TODAY, candidates)
            for row in new_rows:
                new_flags_for_email.append((stock.ticker, row.severity, row.message))

        concentration = portfolio_monitor.evaluate_sector_concentration([(s, v) for _, s, v in holdings_with_values])
        if concentration:
            sector, flag = concentration
            # Attach to the largest holding in the over-concentrated sector — PortfolioFlag
            # rows need a holding_id, and this is the most intuitive one to show it on.
            sector_matches = [(h, s, v) for h, s, v in holdings_with_values if s.sector == sector]
            if sector_matches:
                largest_holding, largest_stock, _ = max(sector_matches, key=lambda row: row[2])
                new_rows = await portfolio_monitor.persist_flags_if_new(db, largest_holding.id, TODAY, [flag])
                for row in new_rows:
                    new_flags_for_email.append((largest_stock.ticker, row.severity, row.message))

        await db.commit()

        if new_flags_for_email and settings.smtp_host:
            user = (await db.execute(select(AppUser).where(AppUser.id == user_id))).scalar_one_or_none()
            if user:
                try:
                    email_alerts.send_portfolio_digest_email(user.email, new_flags_for_email)
                except Exception as exc:  # noqa: BLE001
                    print(f"[refresh_universe] failed to email portfolio digest to {user.email}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
