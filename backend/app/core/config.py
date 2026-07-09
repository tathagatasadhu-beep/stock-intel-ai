"""Centralized environment configuration. Import `settings` rather than reading os.environ directly."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", "").rstrip("/"))
    supabase_anon_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_ANON_KEY", ""))
    app_jwt_secret: str = field(default_factory=lambda: os.environ.get("APP_JWT_SECRET", ""))

    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))

    fmp_api_key: str = field(default_factory=lambda: os.environ.get("FMP_API_KEY", ""))
    fmp_base_url: str = field(default_factory=lambda: os.environ.get("FMP_BASE_URL", "https://financialmodelingprep.com/api/v3"))

    finnhub_api_key: str = field(default_factory=lambda: os.environ.get("FINNHUB_API_KEY", ""))
    finnhub_base_url: str = field(default_factory=lambda: os.environ.get("FINNHUB_BASE_URL", "https://finnhub.io/api/v1"))

    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.environ.get("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD", ""))
    alert_from_email: str = field(default_factory=lambda: os.environ.get("ALERT_FROM_EMAIL", "alerts@stock-intel.local"))

    redis_url: str = field(default_factory=lambda: os.environ.get("REDIS_URL", ""))

    # Intrinsic Value Engine defaults (spec section 2.2)
    default_wacc: float = 0.08
    default_fcf_growth_rate: float = 0.05
    default_terminal_growth_rate: float = 0.025
    default_projection_years: int = 5


settings = Settings()
