"""
Intrinsic Value Engine (spec section 2.2): DCF, Dividend Discount Model, Owner Earnings,
and Comparable valuation. Each function returns None when its required inputs aren't
available (e.g. DDM needs a dividend-paying stock) rather than fabricating a number.

margin_of_safety_pct follows the spec's own example phrasing ("trading 18% below
estimated intrinsic value") — positive means undervalued (price below intrinsic value):
    margin_of_safety_pct = (intrinsic_value - current_price) / intrinsic_value * 100
"""
from dataclasses import dataclass


@dataclass
class MethodResult:
    method: str
    intrinsic_value: float | None
    notes: str | None = None


def margin_of_safety_pct(intrinsic_value: float | None, current_price: float) -> float | None:
    if intrinsic_value is None or intrinsic_value <= 0:
        return None
    return round((intrinsic_value - current_price) / intrinsic_value * 100, 2)


def dcf_valuation(
    free_cash_flow: float | None,
    shares_outstanding: float | None,
    total_debt: float | None,
    cash_and_equivalents: float | None,
    wacc: float,
    fcf_growth_rate: float,
    terminal_growth_rate: float,
    projection_years: int,
) -> MethodResult:
    if not free_cash_flow or not shares_outstanding or shares_outstanding <= 0:
        return MethodResult("dcf", None, "Missing free cash flow or shares outstanding.")
    if wacc <= terminal_growth_rate:
        return MethodResult("dcf", None, "Discount rate must exceed terminal growth rate.")

    pv_sum = 0.0
    fcf = free_cash_flow
    for year in range(1, projection_years + 1):
        fcf = fcf * (1 + fcf_growth_rate)
        pv_sum += fcf / ((1 + wacc) ** year)

    terminal_value = fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    pv_terminal = terminal_value / ((1 + wacc) ** projection_years)

    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - (total_debt or 0) + (cash_and_equivalents or 0)
    intrinsic_per_share = equity_value / shares_outstanding
    return MethodResult("dcf", round(intrinsic_per_share, 2))


def ddm_valuation(dividend_per_share: float | None, wacc: float, dividend_growth_rate: float) -> MethodResult:
    if not dividend_per_share or dividend_per_share <= 0:
        return MethodResult("ddm", None, "Stock does not pay a dividend — DDM not applicable.")
    g = min(dividend_growth_rate, wacc - 0.01)
    if wacc <= g:
        return MethodResult("ddm", None, "Discount rate must exceed dividend growth rate.")
    d1 = dividend_per_share * (1 + g)
    intrinsic = d1 / (wacc - g)
    return MethodResult("ddm", round(intrinsic, 2))


def owner_earnings_valuation(eps: float | None, wacc: float, growth_rate: float) -> MethodResult:
    """Buffett-style owner earnings, approximated by EPS since this data source doesn't
    break out D&A vs. maintenance capex separately from the reported free cash flow figure
    used by dcf_valuation(). Documented as an approximation, not a full owner-earnings
    calc (net income + D&A - maintenance capex - working capital change)."""
    if not eps or eps <= 0:
        return MethodResult("owner_earnings", None, "Missing or negative EPS.")
    g = min(growth_rate, wacc - 0.01)
    if wacc <= g:
        return MethodResult("owner_earnings", None, "Discount rate must exceed growth rate.")
    next_earnings = eps * (1 + g)
    intrinsic = next_earnings / (wacc - g)
    return MethodResult(
        "owner_earnings",
        round(intrinsic, 2),
        "Approximated using EPS as a proxy for owner earnings (no D&A/capex breakdown available).",
    )


def comparable_valuation(eps: float | None, peer_avg_pe: float | None) -> MethodResult:
    if not eps or eps <= 0:
        return MethodResult("comparable", None, "Missing or negative EPS.")
    if not peer_avg_pe or peer_avg_pe <= 0:
        return MethodResult("comparable", None, "No peer/sector average P/E available.")
    return MethodResult("comparable", round(eps * peer_avg_pe, 2))


def blended_intrinsic_value(results: list[MethodResult]) -> float | None:
    values = [r.intrinsic_value for r in results if r.intrinsic_value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)
