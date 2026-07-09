"""
Daily universe refresh: pulls S&P 500 constituents + fundamentals + price candles from
Financial Modeling Prep, computes technicals/Fibonacci/valuation/composite scores/AI
analysis/news for every ticker, persists all of it, then checks active alerts and emails
any that just triggered.

Run manually: `python scripts/refresh_universe.py`
In production: scheduled as a Render Cron Job / Background Worker (see DEPLOY.md step 3.6).
This is the ONLY place that calls the market-data/news/AI providers — routers only ever
read what this script already persisted (see CLAUDE.md -> Conventions), so API usage is
bounded to "once per ticker per run" regardless of how much screener/dashboard traffic
the app gets.

Needs real FMP_API_KEY / OPENAI_API_KEY / FINNHUB_API_KEY in the environment — this is NOT
the local dev path (see dev_server_sqlite.py for that, which seeds fake data instead of
calling any provider).
"""
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.orm import (  # noqa: E402
    Alert,
    AppUser,
    FibonacciLevel,
    FundamentalSnapshot,
    NewsArticle,
    PriceCandle,
    ScreenerScore,
    Stock,
    TechnicalSnapshot,
    ValuationResult,
    AIAnalysis,
)
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services import ai_engine, email_alerts, fibonacci as fib_service, market_data, news as news_service  # noqa: E402
from app.services import scoring, technicals as tech_service, valuation as valuation_service  # noqa: E402
from app.core.config import settings  # noqa: E402

CONCURRENCY = 5
TODAY = date.today()


async def upsert_stock(db: AsyncSession, symbol: str, name: str, sector: str | None) -> Stock:
    result = await db.execute(select(Stock).where(Stock.ticker == symbol))
    stock = result.scalar_one_or_none()
    if stock is None:
        stock = Stock(ticker=symbol, company_name=name, sector=sector, is_sp500=True)
        db.add(stock)
    else:
        stock.company_name = name
        stock.sector = sector
    stock.last_refreshed_at = datetime.now(timezone.utc)
    await db.flush()
    return stock


async def refresh_fundamentals(db: AsyncSession, stock: Stock) -> FundamentalSnapshot | None:
    data = await market_data.get_fundamentals(stock.ticker)
    if data is None:
        return None
    stock.market_cap = data.market_cap
    stock.exchange = data.exchange

    result = await db.execute(
        select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id, FundamentalSnapshot.as_of_date == TODAY)
    )
    snapshot = result.scalar_one_or_none() or FundamentalSnapshot(stock_id=stock.id, as_of_date=TODAY)
    for field in (
        "price", "pe_ratio", "forward_pe", "peg_ratio", "price_to_book", "ev_ebitda", "revenue_growth_yoy",
        "eps_growth", "fcf_growth", "roe", "roic", "debt_equity", "current_ratio", "interest_coverage",
        "altman_z_score", "free_cash_flow", "shares_outstanding", "total_debt", "cash_and_equivalents",
        "dividend_per_share", "eps", "book_value_per_share", "week52_high", "week52_low", "avg_volume",
    ):
        setattr(snapshot, field, getattr(data, field))
    db.add(snapshot)
    await db.flush()
    return snapshot


async def refresh_candles(db: AsyncSession, stock: Stock) -> dict | None:
    rows = await market_data.get_historical_candles(stock.ticker)
    if not rows:
        return None

    existing = await db.execute(select(PriceCandle.date).where(PriceCandle.stock_id == stock.id))
    existing_dates = {r[0] for r in existing.all()}
    for row in rows:
        if row["date"] in existing_dates:
            continue
        db.add(PriceCandle(stock_id=stock.id, **row))
    await db.flush()

    return {
        "dates": [r["date"] for r in rows],
        "open": np.array([r["open"] for r in rows], dtype=float),
        "high": np.array([r["high"] for r in rows], dtype=float),
        "low": np.array([r["low"] for r in rows], dtype=float),
        "close": np.array([r["close"] for r in rows], dtype=float),
        "volume": np.array([r["volume"] for r in rows], dtype=float),
    }


async def compute_technicals(db: AsyncSession, stock: Stock, candles: dict) -> TechnicalSnapshot | None:
    closes, highs, lows, volumes = candles["close"], candles["high"], candles["low"], candles["volume"]
    if len(closes) < 20:
        return None

    sma20, sma50, sma200 = tech_service.sma(closes, 20), tech_service.sma(closes, 50), tech_service.sma(closes, 200)
    bb = tech_service.bollinger_bands(closes, 20)
    vwap = tech_service.rolling_vwap(highs, lows, closes, volumes)
    rsi = tech_service.rsi(closes)
    macd = tech_service.macd(closes)
    atr = tech_service.atr(highs, lows, closes)
    obv = tech_service.obv(closes, volumes)
    stoch_rsi = tech_service.stochastic_rsi(closes)

    def last(arr: np.ndarray) -> float | None:
        v = arr[-1]
        return None if np.isnan(v) else round(float(v), 4)

    result = await db.execute(
        select(TechnicalSnapshot).where(TechnicalSnapshot.stock_id == stock.id, TechnicalSnapshot.as_of_date == TODAY)
    )
    snapshot = result.scalar_one_or_none() or TechnicalSnapshot(stock_id=stock.id, as_of_date=TODAY)
    snapshot.rsi14 = last(rsi)
    snapshot.macd, snapshot.macd_signal, snapshot.macd_hist = last(macd.macd), last(macd.signal), last(macd.hist)
    snapshot.sma20, snapshot.sma50, snapshot.sma200 = last(sma20), last(sma50), last(sma200)
    snapshot.bollinger_upper, snapshot.bollinger_mid, snapshot.bollinger_lower = last(bb.upper), last(bb.mid), last(bb.lower)
    snapshot.vwap = last(vwap)
    snapshot.atr14 = last(atr)
    snapshot.obv = last(obv)
    snapshot.stoch_rsi = last(stoch_rsi)
    snapshot.ma_crossover_signal = tech_service.ma_crossover_signal(sma50, sma200)
    snapshot.volume_breakout = tech_service.volume_breakout(volumes)
    snapshot.week52_breakout = tech_service.week52_breakout(closes, highs, lows)
    db.add(snapshot)
    await db.flush()
    return snapshot


async def compute_fibonacci(db: AsyncSession, stock: Stock, candles: dict) -> FibonacciLevel | None:
    result = fib_service.compute_fibonacci(candles["high"], candles["low"], candles["close"], candles["volume"])
    if result is None:
        return None
    row = FibonacciLevel(
        stock_id=stock.id,
        as_of_date=TODAY,
        trend_direction=result.trend_direction,
        swing_high=result.swing_high,
        swing_low=result.swing_low,
        level_0=result.levels["0"],
        level_236=result.levels["236"],
        level_382=result.levels["382"],
        level_500=result.levels["500"],
        level_618=result.levels["618"],
        level_786=result.levels["786"],
        level_100=result.levels["100"],
        nearest_support=result.nearest_support,
        nearest_resistance=result.nearest_resistance,
        breakout_probability=result.breakout_probability,
    )
    db.add(row)
    await db.flush()
    return row


async def compute_valuation(db: AsyncSession, stock: Stock, fundamentals: FundamentalSnapshot) -> ValuationResult | None:
    # Best-effort peer average: tickers run concurrently in their own sessions/commits, so
    # depending on scheduling this may only see whichever sector peers have committed their
    # FundamentalSnapshot so far this run, not the full sector. Acceptable for the
    # comparable-valuation method (one of four, averaged into the blended value) — not
    # worth serializing the whole run to fix for an MVP.
    peer_result = await db.execute(
        select(FundamentalSnapshot.pe_ratio)
        .join(Stock, Stock.id == FundamentalSnapshot.stock_id)
        .where(Stock.sector == stock.sector, Stock.id != stock.id, FundamentalSnapshot.pe_ratio.is_not(None))
    )
    pes = [r[0] for r in peer_result.all() if r[0] and r[0] > 0]
    peer_avg_pe = round(sum(pes) / len(pes), 2) if pes else None

    methods = [
        valuation_service.dcf_valuation(
            fundamentals.free_cash_flow, fundamentals.shares_outstanding, fundamentals.total_debt,
            fundamentals.cash_and_equivalents, settings.default_wacc, settings.default_fcf_growth_rate,
            settings.default_terminal_growth_rate, settings.default_projection_years,
        ),
        valuation_service.ddm_valuation(fundamentals.dividend_per_share, settings.default_wacc, settings.default_fcf_growth_rate),
        valuation_service.owner_earnings_valuation(fundamentals.eps, settings.default_wacc, settings.default_fcf_growth_rate),
        valuation_service.comparable_valuation(fundamentals.eps, peer_avg_pe),
    ]
    for m in methods:
        db.add(
            ValuationResult(
                stock_id=stock.id, as_of_date=TODAY, method=m.method,
                wacc=settings.default_wacc, fcf_growth_rate=settings.default_fcf_growth_rate,
                terminal_growth_rate=settings.default_terminal_growth_rate, projection_years=settings.default_projection_years,
                intrinsic_value=m.intrinsic_value or 0.0, current_price=fundamentals.price,
                margin_of_safety_pct=valuation_service.margin_of_safety_pct(m.intrinsic_value, fundamentals.price) or 0.0,
            )
        )

    blended_value = valuation_service.blended_intrinsic_value(methods)
    blended = ValuationResult(
        stock_id=stock.id, as_of_date=TODAY, method="blended",
        wacc=settings.default_wacc, fcf_growth_rate=settings.default_fcf_growth_rate,
        terminal_growth_rate=settings.default_terminal_growth_rate, projection_years=settings.default_projection_years,
        intrinsic_value=blended_value or 0.0, current_price=fundamentals.price,
        margin_of_safety_pct=valuation_service.margin_of_safety_pct(blended_value, fundamentals.price) or 0.0,
    )
    db.add(blended)
    await db.flush()
    return blended


async def refresh_news(db: AsyncSession, stock: Stock) -> list[NewsArticle]:
    articles = await news_service.fetch_news_for_ticker(stock.ticker, stock.company_name)
    existing = await db.execute(select(NewsArticle.url).where(NewsArticle.stock_id == stock.id))
    existing_urls = {r[0] for r in existing.all()}
    persisted = []
    for a in articles:
        if a["url"] in existing_urls:
            continue
        row = NewsArticle(stock_id=stock.id, **a)
        db.add(row)
        persisted.append(row)
    await db.flush()
    return persisted


async def process_ticker(symbol: str, name: str, sector: str | None, sem: asyncio.Semaphore) -> dict | None:
    # Each concurrent ticker gets its OWN AsyncSession — SQLAlchemy's AsyncSession is not
    # safe to share across concurrently-running coroutines/tasks. The semaphore bounds how
    # many of these run (and therefore how many provider requests fire) at once; the
    # session itself is still one-per-task.
    async with sem, SessionLocal() as db:
        try:
            stock = await upsert_stock(db, symbol, name, sector)
            fundamentals = await refresh_fundamentals(db, stock)
            candles = await refresh_candles(db, stock)
            if fundamentals is None or candles is None:
                await db.commit()
                return None

            technicals = await compute_technicals(db, stock, candles)
            fib = await compute_fibonacci(db, stock, candles)
            blended_valuation = await compute_valuation(db, stock, fundamentals)
            news_articles = await refresh_news(db, stock)
            await db.commit()

            return {
                "stock": stock, "fundamentals": fundamentals, "technicals": technicals,
                "fibonacci": fib, "valuation": blended_valuation, "news": news_articles,
            }
        except Exception as exc:  # noqa: BLE001 - one bad ticker shouldn't kill the whole run
            await db.rollback()
            print(f"[refresh_universe] {symbol} failed: {exc}")
            return None


async def score_and_analyze(db: AsyncSession, results: list[dict]) -> None:
    pop = scoring.Population()
    for r in results:
        f, t, v = r["fundamentals"], r["technicals"], r["valuation"]
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
        stock, f, t, v, fib, articles = r["stock"], r["fundamentals"], r["technicals"], r["valuation"], r["fibonacci"], r["news"]

        valuation_score = scoring.compute_valuation_score(
            f.pe_ratio, f.forward_pe, f.peg_ratio, f.price_to_book, f.ev_ebitda,
            v.margin_of_safety_pct if v else None, pop,
        )
        growth_score = scoring.compute_growth_score(f.revenue_growth_yoy, f.eps_growth, f.fcf_growth, f.roe, f.roic, pop)
        health_score = scoring.compute_financial_health_score(f.debt_equity, f.current_ratio, f.interest_coverage, f.altman_z_score, pop)
        technical_score = scoring.compute_technical_score(
            t.rsi14 if t else None, t.macd_hist if t else None, t.ma_crossover_signal if t else None,
            t.volume_breakout if t else False, t.week52_breakout if t else None, pop,
        )
        news_score = scoring.compute_news_sentiment_score(
            [a.sentiment_score for a in articles if a.sentiment_score is not None],
            [a.impact_score for a in articles if a.impact_score],
        )
        composite = scoring.compute_composite_score(valuation_score, growth_score, health_score, technical_score, news_score)
        rating = scoring.rating_for_score(composite)

        db.add(
            ScreenerScore(
                stock_id=stock.id, as_of_date=TODAY, valuation_score=valuation_score, growth_score=growth_score,
                financial_health_score=health_score, technical_score=technical_score, news_sentiment_score=news_score,
                composite_score=composite, rating=rating,
            )
        )

        context = {
            "ticker": stock.ticker, "company_name": stock.company_name, "sector": stock.sector,
            "price": f.price, "pe_ratio": f.pe_ratio, "peg_ratio": f.peg_ratio, "roe": f.roe,
            "revenue_growth_yoy": f.revenue_growth_yoy, "debt_equity": f.debt_equity, "altman_z_score": f.altman_z_score,
            "margin_of_safety_pct": v.margin_of_safety_pct if v else None,
            "rsi14": t.rsi14 if t else None, "macd_hist": t.macd_hist if t else None,
            "nearest_support": fib.nearest_support if fib else None, "nearest_resistance": fib.nearest_resistance if fib else None,
            "composite_score": composite, "rating": rating,
        }
        ai_result = await ai_engine.generate_ai_analysis(context)
        db.add(
            AIAnalysis(
                stock_id=stock.id, bullish_bearish_score=ai_result.bullish_bearish_score, risk_score=ai_result.risk_score,
                investment_thesis=ai_result.investment_thesis, technical_thesis=ai_result.technical_thesis,
                key_risks="\n".join(ai_result.key_risks), entry_zone_low=ai_result.entry_zone_low,
                entry_zone_high=ai_result.entry_zone_high, stop_loss=ai_result.stop_loss, target_3m=ai_result.target_3m,
                target_6m=ai_result.target_6m, target_1y=ai_result.target_1y, raw_model_output=ai_result.raw_model_output,
            )
        )
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
