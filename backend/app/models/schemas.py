"""Pydantic response/request models. Keep in sync with app/db/orm.py."""
from datetime import date, datetime

from pydantic import BaseModel, Field


class CandleOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    class Config:
        from_attributes = True


class FundamentalsOut(BaseModel):
    as_of_date: date
    price: float
    pe_ratio: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_book: float | None
    ev_ebitda: float | None
    revenue_growth_yoy: float | None
    eps_growth: float | None
    fcf_growth: float | None
    roe: float | None
    roic: float | None
    debt_equity: float | None
    current_ratio: float | None
    interest_coverage: float | None
    altman_z_score: float | None
    week52_high: float | None
    week52_low: float | None
    avg_volume: float | None

    class Config:
        from_attributes = True


class TechnicalsOut(BaseModel):
    as_of_date: date
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    bollinger_upper: float | None
    bollinger_mid: float | None
    bollinger_lower: float | None
    vwap: float | None
    atr14: float | None
    obv: float | None
    stoch_rsi: float | None
    ma_crossover_signal: str | None
    volume_breakout: bool
    week52_breakout: str | None

    class Config:
        from_attributes = True


class FibonacciOut(BaseModel):
    as_of_date: date
    trend_direction: str
    swing_high: float
    swing_low: float
    level_0: float
    level_236: float
    level_382: float
    level_500: float
    level_618: float
    level_786: float
    level_100: float
    nearest_support: float | None
    nearest_resistance: float | None
    breakout_probability: float | None

    class Config:
        from_attributes = True


class ValuationInputs(BaseModel):
    wacc: float = Field(default=0.08, ge=0.01, le=0.5)
    fcf_growth_rate: float = Field(default=0.05, ge=-0.5, le=1.0)
    terminal_growth_rate: float = Field(default=0.025, ge=0.0, le=0.10)
    projection_years: int = Field(default=5, ge=1, le=15)


class ValuationMethodResult(BaseModel):
    method: str
    intrinsic_value: float | None
    current_price: float
    margin_of_safety_pct: float | None
    notes: str | None = None


class ValuationOut(BaseModel):
    as_of_date: date
    inputs: ValuationInputs
    results: list[ValuationMethodResult]
    blended_intrinsic_value: float | None


class NewsArticleOut(BaseModel):
    source: str
    headline: str
    url: str
    summary: str | None
    published_at: datetime
    sentiment_score: float | None
    sentiment_label: str | None
    impact_score: str | None

    class Config:
        from_attributes = True


class AIAnalysisOut(BaseModel):
    generated_at: datetime
    bullish_bearish_score: int
    risk_score: int
    investment_thesis: str
    technical_thesis: str
    key_risks: list[str]
    entry_zone_low: float | None
    entry_zone_high: float | None
    stop_loss: float | None
    target_3m: float | None
    target_6m: float | None
    target_1y: float | None


class StockSummary(BaseModel):
    ticker: str
    company_name: str
    sector: str | None
    industry: str | None
    market_cap: float | None
    price: float | None


class ScreenerRow(BaseModel):
    ticker: str
    company_name: str
    sector: str | None
    price: float | None
    market_cap: float | None
    pe_ratio: float | None
    peg_ratio: float | None
    margin_of_safety_pct: float | None
    revenue_growth_yoy: float | None
    roe: float | None
    debt_equity: float | None
    rsi14: float | None
    macd_hist: float | None
    valuation_score: float
    growth_score: float
    financial_health_score: float
    technical_score: float
    news_sentiment_score: float
    composite_score: float
    rating: str


class ScreenerFilters(BaseModel):
    """All filters optional; omitted = no constraint. Matches spec section 2.1."""

    sector: str | None = None
    pe_max: float | None = None
    forward_pe_max: float | None = None
    peg_max: float | None = None
    price_to_book_max: float | None = None
    ev_ebitda_max: float | None = None
    margin_of_safety_min: float | None = None

    revenue_growth_min: float | None = None
    eps_growth_min: float | None = None
    fcf_growth_min: float | None = None
    roe_min: float | None = None
    roic_min: float | None = None

    debt_equity_max: float | None = None
    current_ratio_min: float | None = None
    interest_coverage_min: float | None = None
    altman_z_min: float | None = None

    rsi_min: float | None = None
    rsi_max: float | None = None
    macd_bullish_only: bool = False
    golden_cross_only: bool = False
    near_52w_high: bool = False
    near_52w_low: bool = False
    volume_breakout_only: bool = False

    min_composite_score: float | None = None
    rating: str | None = None

    sort_by: str = "composite_score"
    sort_desc: bool = True
    # Default is 10, not a larger number — the batch job (scripts/refresh_universe.py)
    # only guarantees CORE_TICKERS (~10) fresh daily and treats the rest of the universe
    # as best-effort, so a small default matches what's actually reliably populated most
    # days. Still overridable up to 500 for whoever's applied filters that narrow things
    # down, or just wants to see everything that happens to be fresh.
    limit: int = Field(default=10, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str


class AuthToken(BaseModel):
    access_token: str
    user: UserOut


class AlertCreate(BaseModel):
    ticker: str
    alert_type: str
    threshold_value: float | None = None
    delivery_method: str = "email"


class AlertOut(BaseModel):
    id: str
    ticker: str
    alert_type: str
    threshold_value: float | None
    delivery_method: str
    is_active: bool
    last_triggered_at: datetime | None
    created_at: datetime
