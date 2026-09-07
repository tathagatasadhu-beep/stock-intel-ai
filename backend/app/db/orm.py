"""
SQLAlchemy ORM models for the stock intelligence platform.

Conventions mirror EduQuestAI's backend (see ../../../CLAUDE.md -> Conventions):
UUID primary keys, a UTCDateTime type that coerces SQLite's naive datetimes to
UTC-aware (needed for local dev against SQLite, see dev_server_sqlite.py), and
every persisted table computed by scripts/refresh_universe.py rather than on
the request path.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True), but coerces naive results (SQLite) to UTC-aware."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class AppUser(Base):
    """A signed-in investor account (Supabase Auth). Only exists locally to scope Alerts."""

    __tablename__ = "app_users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)  # == Supabase auth.users.id
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    alerts: Mapped[list["Alert"]] = relationship(back_populates="user")
    portfolio_holdings: Mapped[list["PortfolioHolding"]] = relationship(back_populates="user")


class Stock(Base):
    __tablename__ = "stocks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    ticker: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    exchange: Mapped[str | None] = mapped_column(String, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_sp500: Mapped[bool] = mapped_column(Boolean, default=True)
    # "stock" | "etf" — added for portfolio holdings, which can include tickers outside
    # the S&P 500 screener universe entirely (is_sp500=False) and specifically ETFs,
    # which don't get fundamentals-based valuation/scoring (see services/ingest.py).
    asset_type: Mapped[str] = mapped_column(String, default="stock")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    fundamentals: Mapped[list["FundamentalSnapshot"]] = relationship(back_populates="stock")
    candles: Mapped[list["PriceCandle"]] = relationship(back_populates="stock")
    technicals: Mapped[list["TechnicalSnapshot"]] = relationship(back_populates="stock")
    fibonacci_levels: Mapped[list["FibonacciLevel"]] = relationship(back_populates="stock")
    valuations: Mapped[list["ValuationResult"]] = relationship(back_populates="stock")
    news: Mapped[list["NewsArticle"]] = relationship(back_populates="stock")
    ai_analyses: Mapped[list["AIAnalysis"]] = relationship(back_populates="stock")
    screener_scores: Mapped[list["ScreenerScore"]] = relationship(back_populates="stock")


class FundamentalSnapshot(Base):
    """Latest-known fundamentals for a stock, refreshed by scripts/refresh_universe.py."""

    __tablename__ = "fundamental_snapshots"
    __table_args__ = (UniqueConstraint("stock_id", "as_of_date", name="uq_fundamentals_stock_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    # Valuation
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    peg_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_to_book: Mapped[float | None] = mapped_column(Float, nullable=True)
    ev_ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Growth
    revenue_growth_yoy: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    fcf_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    roic: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Financial health
    debt_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    interest_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    altman_z_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Raw inputs needed downstream for DCF/DDM/Owner Earnings (kept alongside the ratios above
    # so services/valuation.py doesn't need a second round-trip to the provider)
    free_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_debt: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_value_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)

    week52_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    week52_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_volume: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="fundamentals")


class PriceCandle(Base):
    __tablename__ = "price_candles"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_candle_stock_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)

    stock: Mapped["Stock"] = relationship(back_populates="candles")


class TechnicalSnapshot(Base):
    __tablename__ = "technical_snapshots"
    __table_args__ = (UniqueConstraint("stock_id", "as_of_date", name="uq_technicals_stock_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    rsi14: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_hist: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma200: Mapped[float | None] = mapped_column(Float, nullable=True)
    bollinger_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    bollinger_mid: Mapped[float | None] = mapped_column(Float, nullable=True)
    bollinger_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    vwap: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr14: Mapped[float | None] = mapped_column(Float, nullable=True)
    obv: Mapped[float | None] = mapped_column(Float, nullable=True)
    stoch_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)

    ma_crossover_signal: Mapped[str | None] = mapped_column(String, nullable=True)  # golden_cross | death_cross | none
    volume_breakout: Mapped[bool] = mapped_column(Boolean, default=False)
    week52_breakout: Mapped[str | None] = mapped_column(String, nullable=True)  # high | low | none

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="technicals")


class FibonacciLevel(Base):
    __tablename__ = "fibonacci_levels"

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    trend_direction: Mapped[str] = mapped_column(String, nullable=False)  # up | down
    swing_high: Mapped[float] = mapped_column(Float, nullable=False)
    swing_low: Mapped[float] = mapped_column(Float, nullable=False)

    level_0: Mapped[float] = mapped_column(Float, nullable=False)
    level_236: Mapped[float] = mapped_column(Float, nullable=False)
    level_382: Mapped[float] = mapped_column(Float, nullable=False)
    level_500: Mapped[float] = mapped_column(Float, nullable=False)
    level_618: Mapped[float] = mapped_column(Float, nullable=False)
    level_786: Mapped[float] = mapped_column(Float, nullable=False)
    level_100: Mapped[float] = mapped_column(Float, nullable=False)

    nearest_support: Mapped[float | None] = mapped_column(Float, nullable=True)
    nearest_resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakout_probability: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="fibonacci_levels")


class ValuationResult(Base):
    __tablename__ = "valuation_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)  # dcf | ddm | owner_earnings | comparable | blended

    wacc: Mapped[float | None] = mapped_column(Float, nullable=True)
    fcf_growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    terminal_growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    projection_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    intrinsic_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    margin_of_safety_pct: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="valuations")


class NewsArticle(Base):
    """A single wire article can legitimately be relevant news for more than one
    ticker (e.g. a sector-wide Zacks/Yahoo piece mentioning both XOM and MPC) —
    services/ingest.py::refresh_news already dedupes per stock_id, not globally, so
    the same URL can and should get its own row per stock it's relevant to. Uniqueness
    is therefore on (stock_id, url), not url alone (see the migration note in
    app/db/migrate.py for the production fix)."""

    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("stock_id", "url", name="uq_news_stock_url"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1..1
    sentiment_label: Mapped[str | None] = mapped_column(String, nullable=True)  # positive | neutral | negative
    impact_score: Mapped[str | None] = mapped_column(String, nullable=True)  # low | medium | high

    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    stock: Mapped["Stock | None"] = relationship(back_populates="news")


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    bullish_bearish_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..100
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..100
    investment_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    technical_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    key_risks: Mapped[str] = mapped_column(Text, nullable=False)  # newline-separated bullets

    entry_zone_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_zone_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_1y: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_model_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    stock: Mapped["Stock"] = relationship(back_populates="ai_analyses")


class ScreenerScore(Base):
    __tablename__ = "screener_scores"
    __table_args__ = (UniqueConstraint("stock_id", "as_of_date", name="uq_screener_stock_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    valuation_score: Mapped[float] = mapped_column(Float, nullable=False)
    growth_score: Mapped[float] = mapped_column(Float, nullable=False)
    financial_health_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_score: Mapped[float] = mapped_column(Float, nullable=False)
    news_sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[str] = mapped_column(String, nullable=False)  # Strong Buy | Buy | Hold | Weak Hold | Avoid

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="screener_scores")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"))
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))

    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    # price_below_support | price_above_resistance | macd_bullish_cross | macd_bearish_cross
    # | rsi_oversold | rsi_overbought | volume_spike | breaking_news | analyst_upgrade | analyst_downgrade
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_method: Mapped[str] = mapped_column(String, default="email")  # email | push | telegram | discord
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    user: Mapped["AppUser"] = relationship(back_populates="alerts")
    stock: Mapped["Stock"] = relationship()


class PortfolioHolding(Base):
    """A user's actual position in a stock or ETF — quantity + cost basis, so the app can
    show real unrealized P&L and base exit/risk flags on the user's own entry price, not
    just generic technical signals. `stock_id` may point at a Stock outside the S&P 500
    screener universe entirely (is_sp500=False) — added on the fly when a holding is
    created for a ticker we don't already track (see routers/portfolio.py)."""

    __tablename__ = "portfolio_holdings"
    __table_args__ = (UniqueConstraint("user_id", "stock_id", name="uq_portfolio_user_stock"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"))
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    user: Mapped["AppUser"] = relationship(back_populates="portfolio_holdings")
    stock: Mapped["Stock"] = relationship()


class PortfolioFlag(Base):
    """A monitoring flag raised for one holding by scripts/refresh_universe.py's
    portfolio-monitoring pass (see services/portfolio_monitor.py) — exit suggestions,
    risk warnings, and news-driven upside/downside flags. Persisted (not just emailed)
    so the portfolio page can show flag history, and so the daily job doesn't re-email
    the same flag every day it's still true (see the uniqueness constraint)."""

    __tablename__ = "portfolio_flags"
    __table_args__ = (UniqueConstraint("holding_id", "flag_type", "as_of_date", name="uq_portfolio_flag_per_day"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    holding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolio_holdings.id", ondelete="CASCADE"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    flag_type: Mapped[str] = mapped_column(String, nullable=False)
    # stop_loss_hit | target_reached | overbought_trim | oversold_watch | death_cross_risk
    # | golden_cross_positive | negative_news_risk | positive_news_upside
    # | large_unrealized_loss | large_unrealized_gain | sector_concentration
    severity: Mapped[str] = mapped_column(String, nullable=False)  # info | warning | critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    holding: Mapped["PortfolioHolding"] = relationship()
