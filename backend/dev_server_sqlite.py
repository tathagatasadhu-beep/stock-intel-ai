"""
Local-dev-only entrypoint for this ARM64 Windows machine, where `asyncpg` has no
prebuilt wheel (same limitation as EduQuestAI — see that repo's CLAUDE.md). Swaps
DATABASE_URL to a file-based SQLite DB *before* app.db.session creates its engine,
creates the schema, and seeds a handful of demo stocks with realistic-shaped
fundamentals/candles/technicals/Fibonacci/valuation/news/AI-analysis/scores — all
computed with the SAME services/* code the real ingestion script uses, just fed
synthetic price data instead of a live FMP pull, so the frontend has real numbers
to render without spending API quota.

This is NOT how the app runs in production (Render uses real Postgres + FMP/OpenAI/
NewsAPI via scripts/refresh_universe.py) — it exists purely so this workstation can
preview the frontend end-to-end.
"""
import asyncio
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "dev_sqlite.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"  # re-assert after load_dotenv

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.orm import (  # noqa: E402
    AIAnalysis,
    Base,
    FibonacciLevel,
    FundamentalSnapshot,
    NewsArticle,
    PriceCandle,
    ScreenerScore,
    Stock,
    TechnicalSnapshot,
    ValuationResult,
)
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services import ai_engine, fibonacci as fib_service, scoring, technicals as tech_service, valuation as valuation_service  # noqa: E402

random.seed(42)
np.random.seed(42)

DEMO_STOCKS = [
    # ticker, name, sector, start_price, annual_drift, annual_vol, dividend_per_share, has_dividend
    ("AAPL", "Apple Inc.", "Technology", 180.0, 0.14, 0.28, 0.96),
    ("MSFT", "Microsoft Corporation", "Technology", 340.0, 0.16, 0.26, 3.00),
    ("NVDA", "NVIDIA Corporation", "Technology", 450.0, 0.35, 0.55, 0.16),
    ("JPM", "JPMorgan Chase & Co.", "Financials", 150.0, 0.09, 0.24, 4.60),
    ("XOM", "Exxon Mobil Corporation", "Energy", 105.0, 0.05, 0.30, 3.80),
    ("JNJ", "Johnson & Johnson", "Healthcare", 160.0, 0.04, 0.18, 4.76),
    ("PG", "Procter & Gamble Co.", "Consumer Staples", 150.0, 0.06, 0.16, 3.65),
    ("TSLA", "Tesla, Inc.", "Consumer Discretionary", 240.0, 0.10, 0.60, 0.0),
]

CANDLE_DAYS = 260


def _generate_candles(start_price: float, annual_drift: float, annual_vol: float, days: int) -> dict:
    daily_drift = annual_drift / 252
    daily_vol = annual_vol / (252 ** 0.5)
    closes = [start_price]
    for _ in range(days - 1):
        shock = np.random.normal(daily_drift, daily_vol)
        closes.append(max(closes[-1] * (1 + shock), 0.5))
    closes = np.array(closes)

    highs = closes * (1 + np.abs(np.random.normal(0, 0.006, days)))
    lows = closes * (1 - np.abs(np.random.normal(0, 0.006, days)))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    volumes = np.random.uniform(2_000_000, 20_000_000, days)
    # occasional volume spikes so volume_breakout has something to detect
    for i in random.sample(range(days - 10, days), 2):
        volumes[i] *= random.uniform(1.8, 2.5)

    today = date.today()
    dates = [today - timedelta(days=(days - 1 - i)) for i in range(days)]
    return {"dates": dates, "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}


async def seed_if_empty():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        existing = (await db.execute(select(Stock))).scalars().first()
        if existing is not None:
            print(f"Dev SQLite DB already seeded at {DB_PATH}")
            return

        today = date.today()
        results = []
        for ticker, name, sector, start_price, drift, vol, dps in DEMO_STOCKS:
            candles = _generate_candles(start_price, drift, vol, CANDLE_DAYS)
            closes, highs, lows, volumes = candles["close"], candles["high"], candles["low"], candles["volume"]
            price = float(closes[-1])

            stock = Stock(ticker=ticker, company_name=name, sector=sector, exchange="NASDAQ", market_cap=price * 1_500_000_000, is_sp500=True)
            db.add(stock)
            await db.flush()

            for i, d in enumerate(candles["dates"]):
                db.add(PriceCandle(stock_id=stock.id, date=d, open=float(candles["open"][i]), high=float(highs[i]), low=float(lows[i]), close=float(closes[i]), volume=float(volumes[i])))

            eps = round(price / random.uniform(12, 30), 2)
            fundamentals = FundamentalSnapshot(
                stock_id=stock.id, as_of_date=today, price=price,
                pe_ratio=round(price / eps, 2) if eps else None,
                forward_pe=round(price / eps * 0.9, 2) if eps else None,
                peg_ratio=round(random.uniform(0.8, 2.5), 2),
                price_to_book=round(random.uniform(2, 15), 2),
                ev_ebitda=round(random.uniform(8, 25), 2),
                revenue_growth_yoy=round(random.uniform(-0.05, 0.30), 3),
                eps_growth=round(random.uniform(-0.05, 0.35), 3),
                fcf_growth=round(random.uniform(-0.05, 0.30), 3),
                roe=round(random.uniform(0.10, 0.45), 3),
                roic=round(random.uniform(0.08, 0.35), 3),
                debt_equity=round(random.uniform(0.2, 2.0), 2),
                current_ratio=round(random.uniform(0.8, 2.5), 2),
                interest_coverage=round(random.uniform(3, 25), 1),
                altman_z_score=round(random.uniform(1.5, 6.0), 2),
                free_cash_flow=price * 1_500_000_000 * random.uniform(0.03, 0.08),
                shares_outstanding=1_500_000_000,
                total_debt=price * 1_500_000_000 * random.uniform(0.1, 0.4),
                cash_and_equivalents=price * 1_500_000_000 * random.uniform(0.05, 0.2),
                dividend_per_share=dps or None,
                eps=eps,
                book_value_per_share=round(price / random.uniform(3, 10), 2),
                week52_high=float(highs.max()),
                week52_low=float(lows.min()),
                avg_volume=float(volumes.mean()),
            )
            db.add(fundamentals)
            await db.flush()

            sma20, sma50, sma200 = tech_service.sma(closes, 20), tech_service.sma(closes, 50), tech_service.sma(closes, 200)
            bb = tech_service.bollinger_bands(closes, 20)
            vwap = tech_service.rolling_vwap(highs, lows, closes, volumes)
            rsi = tech_service.rsi(closes)
            macd = tech_service.macd(closes)
            atr = tech_service.atr(highs, lows, closes)
            obv = tech_service.obv(closes, volumes)
            stoch_rsi = tech_service.stochastic_rsi(closes)

            def last(arr):
                v = arr[-1]
                return None if np.isnan(v) else round(float(v), 4)

            technicals = TechnicalSnapshot(
                stock_id=stock.id, as_of_date=today,
                rsi14=last(rsi), macd=last(macd.macd), macd_signal=last(macd.signal), macd_hist=last(macd.hist),
                sma20=last(sma20), sma50=last(sma50), sma200=last(sma200),
                bollinger_upper=last(bb.upper), bollinger_mid=last(bb.mid), bollinger_lower=last(bb.lower),
                vwap=last(vwap), atr14=last(atr), obv=last(obv), stoch_rsi=last(stoch_rsi),
                ma_crossover_signal=tech_service.ma_crossover_signal(sma50, sma200),
                volume_breakout=tech_service.volume_breakout(volumes),
                week52_breakout=tech_service.week52_breakout(closes, highs, lows),
            )
            db.add(technicals)
            await db.flush()

            fib_raw = fib_service.compute_fibonacci(highs, lows, closes, volumes)
            fib = None
            if fib_raw:
                fib = FibonacciLevel(
                    stock_id=stock.id, as_of_date=today, trend_direction=fib_raw.trend_direction,
                    swing_high=fib_raw.swing_high, swing_low=fib_raw.swing_low,
                    level_0=fib_raw.levels["0"], level_236=fib_raw.levels["236"], level_382=fib_raw.levels["382"],
                    level_500=fib_raw.levels["500"], level_618=fib_raw.levels["618"], level_786=fib_raw.levels["786"],
                    level_100=fib_raw.levels["100"], nearest_support=fib_raw.nearest_support,
                    nearest_resistance=fib_raw.nearest_resistance, breakout_probability=fib_raw.breakout_probability,
                )
                db.add(fib)
                await db.flush()

            methods = [
                valuation_service.dcf_valuation(fundamentals.free_cash_flow, fundamentals.shares_outstanding, fundamentals.total_debt, fundamentals.cash_and_equivalents, 0.08, 0.05, 0.025, 5),
                valuation_service.ddm_valuation(fundamentals.dividend_per_share, 0.08, 0.05),
                valuation_service.owner_earnings_valuation(fundamentals.eps, 0.08, 0.05),
                valuation_service.comparable_valuation(fundamentals.eps, fundamentals.pe_ratio * 1.05 if fundamentals.pe_ratio else None),
            ]
            blended_value = valuation_service.blended_intrinsic_value(methods)
            for m in methods:
                db.add(ValuationResult(stock_id=stock.id, as_of_date=today, method=m.method, wacc=0.08, fcf_growth_rate=0.05, terminal_growth_rate=0.025, projection_years=5, intrinsic_value=m.intrinsic_value or 0.0, current_price=price, margin_of_safety_pct=valuation_service.margin_of_safety_pct(m.intrinsic_value, price) or 0.0))
            blended = ValuationResult(stock_id=stock.id, as_of_date=today, method="blended", wacc=0.08, fcf_growth_rate=0.05, terminal_growth_rate=0.025, projection_years=5, intrinsic_value=blended_value or 0.0, current_price=price, margin_of_safety_pct=valuation_service.margin_of_safety_pct(blended_value, price) or 0.0)
            db.add(blended)
            await db.flush()

            headlines = [
                (f"{name} beats quarterly earnings estimates, raises full-year guidance", 0.7, "positive", "high"),
                (f"Analysts remain mixed on {name} amid sector rotation", 0.0, "neutral", "medium"),
                (f"{name} announces new product roadmap at investor day", 0.3, "positive", "medium"),
            ]
            news_rows = []
            for i, (headline, sentiment, label, impact) in enumerate(headlines):
                row = NewsArticle(
                    stock_id=stock.id, source="Demo Wire", headline=headline, url=f"https://example.com/{ticker.lower()}-news-{i}",
                    summary=None, published_at=datetime.now(timezone.utc) - timedelta(hours=i * 6),
                    sentiment_score=sentiment, sentiment_label=label, impact_score=impact,
                )
                db.add(row)
                news_rows.append(row)
            await db.flush()

            results.append({"stock": stock, "fundamentals": fundamentals, "technicals": technicals, "fibonacci": fib, "valuation": blended, "news": news_rows})

        pop = scoring.Population()
        for r in results:
            f, t, v = r["fundamentals"], r["technicals"], r["valuation"]
            pop.pe_ratio.append(f.pe_ratio); pop.forward_pe.append(f.forward_pe); pop.peg_ratio.append(f.peg_ratio)
            pop.price_to_book.append(f.price_to_book); pop.ev_ebitda.append(f.ev_ebitda)
            pop.margin_of_safety_pct.append(v.margin_of_safety_pct if v else None)
            pop.revenue_growth_yoy.append(f.revenue_growth_yoy); pop.eps_growth.append(f.eps_growth); pop.fcf_growth.append(f.fcf_growth)
            pop.roe.append(f.roe); pop.roic.append(f.roic)
            pop.debt_equity.append(f.debt_equity); pop.current_ratio.append(f.current_ratio)
            pop.interest_coverage.append(f.interest_coverage); pop.altman_z_score.append(f.altman_z_score)
            pop.macd_hist.append(t.macd_hist if t else None)

        for r in results:
            stock, f, t, v, fib, articles = r["stock"], r["fundamentals"], r["technicals"], r["valuation"], r["fibonacci"], r["news"]
            valuation_score = scoring.compute_valuation_score(f.pe_ratio, f.forward_pe, f.peg_ratio, f.price_to_book, f.ev_ebitda, v.margin_of_safety_pct if v else None, pop)
            growth_score = scoring.compute_growth_score(f.revenue_growth_yoy, f.eps_growth, f.fcf_growth, f.roe, f.roic, pop)
            health_score = scoring.compute_financial_health_score(f.debt_equity, f.current_ratio, f.interest_coverage, f.altman_z_score, pop)
            technical_score = scoring.compute_technical_score(t.rsi14 if t else None, t.macd_hist if t else None, t.ma_crossover_signal if t else None, t.volume_breakout if t else False, t.week52_breakout if t else None, pop)
            news_score = scoring.compute_news_sentiment_score([a.sentiment_score for a in articles], [a.impact_score for a in articles])
            composite = scoring.compute_composite_score(valuation_score, growth_score, health_score, technical_score, news_score)
            rating = scoring.rating_for_score(composite)
            db.add(ScreenerScore(stock_id=stock.id, as_of_date=today, valuation_score=valuation_score, growth_score=growth_score, financial_health_score=health_score, technical_score=technical_score, news_sentiment_score=news_score, composite_score=composite, rating=rating))

            context = {
                "ticker": stock.ticker, "company_name": stock.company_name, "sector": stock.sector, "price": f.price,
                "pe_ratio": f.pe_ratio, "peg_ratio": f.peg_ratio, "roe": f.roe, "revenue_growth_yoy": f.revenue_growth_yoy,
                "debt_equity": f.debt_equity, "altman_z_score": f.altman_z_score,
                "margin_of_safety_pct": v.margin_of_safety_pct if v else None,
                "rsi14": t.rsi14 if t else None, "macd_hist": t.macd_hist if t else None,
                "nearest_support": fib.nearest_support if fib else None, "nearest_resistance": fib.nearest_resistance if fib else None,
                "composite_score": composite, "rating": rating,
            }
            ai_result = await ai_engine.generate_ai_analysis(context)
            db.add(AIAnalysis(
                stock_id=stock.id, bullish_bearish_score=ai_result.bullish_bearish_score, risk_score=ai_result.risk_score,
                investment_thesis=ai_result.investment_thesis, technical_thesis=ai_result.technical_thesis,
                key_risks="\n".join(ai_result.key_risks), entry_zone_low=ai_result.entry_zone_low, entry_zone_high=ai_result.entry_zone_high,
                stop_loss=ai_result.stop_loss, target_3m=ai_result.target_3m, target_6m=ai_result.target_6m, target_1y=ai_result.target_1y,
                raw_model_output=ai_result.raw_model_output,
            ))

        await db.commit()
        print(f"Seeded dev SQLite DB with {len(results)} demo stocks at {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(seed_if_empty())

    import uvicorn

    # Port 8001, not FastAPI's usual 8000 default — this machine also runs EduQuestAI's
    # backend dev server on 8000 (separate sibling project, see CLAUDE.md), so this project
    # picked the next port over to let both run side by side without a conflict.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=False)
