"""
AI Trading Assistant (spec section 2.5): plain-English investment thesis, technical
thesis, key risks, bullish/bearish + risk scoring, entry zone, stop-loss, and 3M/6M/1Y
targets — generated from the already-computed fundamentals/technicals/valuation/Fibonacci
data for one stock (this module does no data fetching itself).

Falls back to a deterministic rule-based summary when OPENAI_API_KEY isn't set, so local
dev (dev_server_sqlite.py) and CI can exercise the full pipeline without a real key. The
fallback is intentionally template-y — it's a placeholder, not a substitute for the real
model output.
"""
import json
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings


@dataclass
class AIAnalysisResult:
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
    raw_model_output: str | None = None


_SYSTEM_PROMPT = """You are a professional equity research assistant. Given structured \
fundamental, technical, valuation, and news-sentiment data for one stock, produce a plain-English \
analysis. Respond ONLY with a JSON object matching this exact schema:
{
  "bullish_bearish_score": <int 0-100, 0=extremely bearish, 100=extremely bullish>,
  "risk_score": <int 0-100, 0=very low risk, 100=very high risk>,
  "investment_thesis": <string, 2-4 sentences on valuation/growth/financial health>,
  "technical_thesis": <string, 2-4 sentences on price action/indicators/Fibonacci>,
  "key_risks": [<string>, ...up to 5 short bullet points>],
  "entry_zone_low": <number or null>,
  "entry_zone_high": <number or null>,
  "stop_loss": <number or null>,
  "target_3m": <number or null>,
  "target_6m": <number or null>,
  "target_1y": <number or null>
}
Do not include any text outside the JSON object. Be specific and quantitative where the \
input data supports it; do not invent numbers that weren't derivable from the input."""


def _build_user_prompt(context: dict) -> str:
    return f"Stock data:\n{json.dumps(context, indent=2, default=str)}"


async def generate_ai_analysis(context: dict) -> AIAnalysisResult:
    if not settings.openai_api_key:
        return _fallback_analysis(context)

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(context)},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = response.choices[0].message.content
    parsed = json.loads(raw)
    return AIAnalysisResult(
        bullish_bearish_score=int(parsed.get("bullish_bearish_score", 50)),
        risk_score=int(parsed.get("risk_score", 50)),
        investment_thesis=parsed.get("investment_thesis", ""),
        technical_thesis=parsed.get("technical_thesis", ""),
        key_risks=list(parsed.get("key_risks", [])),
        entry_zone_low=parsed.get("entry_zone_low"),
        entry_zone_high=parsed.get("entry_zone_high"),
        stop_loss=parsed.get("stop_loss"),
        target_3m=parsed.get("target_3m"),
        target_6m=parsed.get("target_6m"),
        target_1y=parsed.get("target_1y"),
        raw_model_output=raw,
    )


def _fallback_analysis(context: dict) -> AIAnalysisResult:
    """No OpenAI key configured — deterministic placeholder derived from the same inputs
    so the rest of the pipeline (persistence, API, frontend) has something real to render."""
    price = context.get("price") or 0.0
    mos = context.get("margin_of_safety_pct")
    rsi = context.get("rsi14")
    macd_hist = context.get("macd_hist")
    support = context.get("nearest_support")
    resistance = context.get("nearest_resistance")

    bullish = 50
    if mos is not None:
        bullish += max(-20, min(20, mos / 2))
    if macd_hist is not None:
        bullish += 10 if macd_hist > 0 else -10
    if rsi is not None:
        if rsi < 30:
            bullish += 5
        elif rsi > 70:
            bullish -= 5
    bullish = int(max(0, min(100, bullish)))

    risk = 50
    if context.get("debt_equity") is not None:
        risk += 10 if context["debt_equity"] > 1.5 else -5
    if context.get("altman_z_score") is not None:
        risk += -10 if context["altman_z_score"] > 3 else 10
    risk = int(max(0, min(100, risk)))

    mos_phrase = f"trading {abs(mos):.0f}% {'below' if mos and mos > 0 else 'above'} estimated intrinsic value" if mos is not None else "intrinsic value could not be estimated from available data"
    investment_thesis = (
        f"{context.get('company_name', context.get('ticker', 'This stock'))} is {mos_phrase}. "
        f"Revenue growth is {'positive' if (context.get('revenue_growth_yoy') or 0) > 0 else 'negative'} "
        f"and return on equity is {context.get('roe', 'unavailable')}."
    )
    macd_phrase = "MACD has turned bullish" if (macd_hist or 0) > 0 else "MACD is bearish"
    rsi_phrase = f"RSI is {rsi:.0f}" if rsi is not None else "RSI is unavailable"
    fib_phrase = f", with a potential support zone near {support:.2f}" if support else ""
    technical_thesis = f"{rsi_phrase} and {macd_phrase}{fib_phrase}."

    key_risks = ["Auto-generated fallback analysis — OPENAI_API_KEY not configured, this is not a real model output."]
    if context.get("debt_equity") and context["debt_equity"] > 1.5:
        key_risks.append("Elevated debt/equity ratio relative to typical peers.")
    if rsi is not None and rsi > 70:
        key_risks.append("RSI indicates overbought conditions.")

    return AIAnalysisResult(
        bullish_bearish_score=bullish,
        risk_score=risk,
        investment_thesis=investment_thesis,
        technical_thesis=technical_thesis,
        key_risks=key_risks,
        entry_zone_low=round(support, 2) if support else None,
        entry_zone_high=round(price, 2) if price else None,
        stop_loss=round(support * 0.95, 2) if support else None,
        target_3m=round(price * 1.05, 2) if price else None,
        target_6m=round(price * 1.10, 2) if price else None,
        target_1y=round(price * 1.18, 2) if price else None,
        raw_model_output=None,
    )
