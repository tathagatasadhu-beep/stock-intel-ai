"""
Technical indicator math (spec section 2.3/2.4). Pure functions over numpy arrays of
chronologically-ascending OHLCV data — no I/O, no DB access, so these are trivially
unit-testable and reusable from both scripts/refresh_universe.py (persists the latest
value per stock per day) and the technicals router (returns the full series for charting).

All "series" functions return an array the same length as the input, front-padded with
NaN wherever there isn't enough history yet for that indicator.
"""
from dataclasses import dataclass

import numpy as np


def sma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    cumsum = np.cumsum(np.insert(values, 0, 0))
    out[period - 1 :] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    alpha = 2 / (period + 1)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = values[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full(len(closes), np.nan)
    if len(closes) <= period:
        return out
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def stochastic_rsi(closes: np.ndarray, period: int = 14, smooth_k: int = 3) -> np.ndarray:
    """Returns %K (0-100), smoothed. Needs ~2*period+smooth_k warm-up bars."""
    rsi_series = rsi(closes, period)
    out = np.full(len(closes), np.nan)
    for i in range(len(closes)):
        if i < period - 1 or np.isnan(rsi_series[i]):
            continue
        window = rsi_series[max(0, i - period + 1) : i + 1]
        window = window[~np.isnan(window)]
        if len(window) < period:
            continue
        lo, hi = window.min(), window.max()
        out[i] = 50.0 if hi == lo else (rsi_series[i] - lo) / (hi - lo) * 100
    return sma(out, smooth_k)


@dataclass
class MACDResult:
    macd: np.ndarray
    signal: np.ndarray
    hist: np.ndarray


def macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9) -> MACDResult:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = ema_fast - ema_slow
    # ema() of macd_line, but macd_line has NaN padding up to `slow`-1 — feed only the valid tail
    valid_start = slow - 1
    signal_tail = ema(macd_line[valid_start:], signal_period)
    signal_line = np.full(len(closes), np.nan)
    signal_line[valid_start:] = signal_tail
    hist = macd_line - signal_line
    return MACDResult(macd=macd_line, signal=signal_line, hist=hist)


@dataclass
class BollingerResult:
    upper: np.ndarray
    mid: np.ndarray
    lower: np.ndarray


def bollinger_bands(closes: np.ndarray, period: int = 20, num_std: float = 2.0) -> BollingerResult:
    mid = sma(closes, period)
    upper = np.full(len(closes), np.nan)
    lower = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        std = window.std(ddof=0)
        upper[i] = mid[i] + num_std * std
        lower[i] = mid[i] - num_std * std
    return BollingerResult(upper=upper, mid=mid, lower=lower)


def rolling_vwap(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray, period: int = 20) -> np.ndarray:
    """True intraday VWAP needs tick data we don't have on daily bars. This is a rolling
    volume-weighted average of the typical price over `period` trailing daily candles —
    a common proxy used by daily-bar dashboards, not exchange-computed intraday VWAP."""
    typical = (highs + lows + closes) / 3
    out = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        tp = typical[i - period + 1 : i + 1]
        vol = volumes[i - period + 1 : i + 1]
        total_vol = vol.sum()
        out[i] = np.nan if total_vol == 0 else (tp * vol).sum() / total_vol
    return out


def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full(len(closes), np.nan)
    if len(closes) <= period:
        return out
    prev_close = closes[:-1]
    tr = np.maximum.reduce(
        [
            highs[1:] - lows[1:],
            np.abs(highs[1:] - prev_close),
            np.abs(lows[1:] - prev_close),
        ]
    )
    out[period] = tr[:period].mean()
    for i in range(period, len(tr)):
        out[i + 1] = (out[i] * (period - 1) + tr[i]) / period
    return out


def obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    out = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def ma_crossover_signal(sma_short: np.ndarray, sma_long: np.ndarray) -> str | None:
    """Golden/death cross on the most recent bar, looking at the last two points."""
    if len(sma_short) < 2 or np.isnan(sma_short[-2]) or np.isnan(sma_long[-2]):
        return None
    prev_diff = sma_short[-2] - sma_long[-2]
    cur_diff = sma_short[-1] - sma_long[-1]
    if prev_diff <= 0 < cur_diff:
        return "golden_cross"
    if prev_diff >= 0 > cur_diff:
        return "death_cross"
    return "none"


def volume_breakout(volumes: np.ndarray, avg_period: int = 20, threshold: float = 1.5) -> bool:
    if len(volumes) <= avg_period:
        return False
    avg = volumes[-avg_period - 1 : -1].mean()
    return bool(avg > 0 and volumes[-1] > threshold * avg)


def week52_breakout(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, lookback: int = 252) -> str | None:
    window = min(lookback, len(closes))
    if window < 30:
        return None
    hi = highs[-window:].max()
    lo = lows[-window:].min()
    last = closes[-1]
    if last >= hi:
        return "high"
    if last <= lo:
        return "low"
    return "none"
