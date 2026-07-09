"""
Auto swing-high/low detection and Fibonacci retracement levels (spec section 2.4).

There's no universally agreed definition of "the" swing high/low for retracement
purposes — this uses the simplest defensible one: the highest high and lowest low
over a trailing lookback window, with trend direction inferred from which one
happened more recently. Good enough for a research dashboard; a discretionary
trader may draw different swing points by eye.
"""
from dataclasses import dataclass

import numpy as np

FIB_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


@dataclass
class FibonacciResult:
    trend_direction: str  # "up" | "down"
    swing_high: float
    swing_low: float
    levels: dict[str, float]  # "0", "236", "382", "500", "618", "786", "100" -> price
    nearest_support: float | None
    nearest_resistance: float | None
    breakout_probability: float | None


def compute_fibonacci(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    lookback: int = 90,
) -> FibonacciResult | None:
    window = min(lookback, len(closes))
    if window < 10:
        return None

    h = highs[-window:]
    l = lows[-window:]
    c = closes[-window:]
    v = volumes[-window:]

    high_idx = int(np.argmax(h))
    low_idx = int(np.argmin(l))
    swing_high = float(h[high_idx])
    swing_low = float(l[low_idx])
    if swing_high <= swing_low:
        return None

    trend_direction = "up" if high_idx > low_idx else "down"
    span = swing_high - swing_low

    levels: dict[str, float] = {}
    for ratio in FIB_RATIOS:
        key = str(int(ratio * 1000)) if ratio not in (0.0, 1.0) else ("0" if ratio == 0.0 else "100")
        if trend_direction == "up":
            # retracement measured down from the swing high
            price = swing_high - span * ratio
        else:
            # retracement measured up from the swing low
            price = swing_low + span * ratio
        levels[key] = round(price, 2)

    current_price = float(c[-1])
    sorted_levels = sorted(levels.values())
    supports = [p for p in sorted_levels if p <= current_price]
    resistances = [p for p in sorted_levels if p > current_price]
    nearest_support = max(supports) if supports else None
    nearest_resistance = min(resistances) if resistances else None

    breakout_probability = _estimate_breakout_probability(
        current_price, nearest_support, nearest_resistance, v
    )

    return FibonacciResult(
        trend_direction=trend_direction,
        swing_high=swing_high,
        swing_low=swing_low,
        levels=levels,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        breakout_probability=breakout_probability,
    )


def _estimate_breakout_probability(
    price: float, support: float | None, resistance: float | None, volumes: np.ndarray
) -> float | None:
    """Heuristic 0..1 "how likely is a breakout soon" estimate — NOT a statistically
    fitted probability. Combines how close price is squeezed toward the nearer level
    with recent volume trend (rising volume near a level suggests building pressure).
    Documented as a heuristic in the API response; treat as a rough signal only."""
    if support is None or resistance is None or resistance <= support:
        return None
    band = resistance - support
    if band <= 0:
        return None
    dist_to_nearest = min(price - support, resistance - price) / band  # 0 = right at a level, 0.5 = mid-band
    proximity_score = 1 - min(dist_to_nearest / 0.5, 1.0)  # closer to a level -> higher

    if len(volumes) >= 10:
        recent_avg = volumes[-5:].mean()
        prior_avg = volumes[-10:-5].mean()
        volume_trend = 0.5 if prior_avg == 0 else min(recent_avg / prior_avg, 2.0) / 2.0
    else:
        volume_trend = 0.5

    probability = 0.6 * proximity_score + 0.4 * volume_trend
    return round(min(max(probability, 0.0), 1.0), 2)
