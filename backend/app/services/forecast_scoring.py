"""
Forecast scoring for binary outcomes: Brier, log score, empirical CRPS, calibration curves.

Pure functions for backtesting and synthesis; not wired into the live report pipeline yet.
Forecasts are probabilities in [0, 1]; outcomes are 0 or 1.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from collections.abc import Sequence


@dataclass
class BrierDecomposition:
    score: float
    reliability: float
    resolution: float
    uncertainty: float
    n: int


@dataclass
class CalibrationBin:
    bin_lower: float
    bin_upper: float
    mean_forecast: float
    mean_outcome: float
    count: int


@dataclass
class ScoringReport:
    brier: BrierDecomposition
    mean_log_score: float
    mean_crps: float | None
    calibration: list[CalibrationBin]
    overconfidence: float
    n_forecasts: int
    log_scores: list[float] = field(default_factory=list)


def _validate_probability(forecast: float) -> float:
    p = float(forecast)
    if math.isnan(p) or math.isinf(p) or p < 0.0 or p > 1.0:
        raise ValueError(f"forecast must be in [0, 1], got {forecast!r}")
    return p


def _validate_binary_outcome(outcome: int | float) -> int:
    if isinstance(outcome, bool):
        raise ValueError("outcome must be 0 or 1 (int or float), not bool")
    o = float(outcome)
    if o != 0.0 and o != 1.0:
        raise ValueError(f"outcome must be 0 or 1, got {outcome!r}")
    return int(o)


def brier_score(forecast: float, outcome: int | float) -> float:
    """Single-forecast Brier score. forecast in [0,1], outcome in {0,1}."""
    p = _validate_probability(forecast)
    o = float(_validate_binary_outcome(outcome))
    return (p - o) ** 2


def _bin_index(p: float, n_bins: int) -> int:
    p = max(0.0, min(1.0, p))
    if p >= 1.0:
        return n_bins - 1
    return min(n_bins - 1, int(p * n_bins))


def brier_score_batch(
    forecasts: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> tuple[float, BrierDecomposition]:
    """
    Mean Brier score and Murphy decomposition:
    Brier = Reliability - Resolution + Uncertainty

    Raises:
        ValueError: if len(forecasts) != len(outcomes).

    Both-empty (0 forecasts, 0 outcomes) is valid: returns (nan, decomposition with score=nan
    and n=0); mean Brier is undefined, not a real score.
    """
    if len(forecasts) != len(outcomes):
        raise ValueError(f"forecasts and outcomes must have the same length, got {len(forecasts)} and {len(outcomes)}")
    if len(forecasts) == 0:
        _nan = float("nan")
        return _nan, BrierDecomposition(score=_nan, reliability=0.0, resolution=0.0, uncertainty=0.0, n=0)

    fs = [max(0.0, min(1.0, float(f))) for f in forecasts]
    os_list = [float(_validate_binary_outcome(o)) for o in outcomes]
    n = len(fs)

    brier = sum((f - float(o)) ** 2 for f, o in zip(fs, os_list, strict=True)) / n
    bar_o = sum(os_list) / n
    uncertainty = bar_o * (1.0 - bar_o)

    bins: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for f, o in zip(fs, os_list, strict=True):
        bins[_bin_index(f, n_bins)].append((f, o))

    reliability = 0.0
    resolution = 0.0
    for _b, pairs in bins.items():
        if not pairs:
            continue
        n_b = len(pairs)
        p_bar = sum(p[0] for p in pairs) / n_b
        o_bar = sum(p[1] for p in pairs) / n_b
        reliability += n_b * (p_bar - o_bar) ** 2
        resolution += n_b * (o_bar - bar_o) ** 2
    reliability /= n
    resolution /= n

    return brier, BrierDecomposition(
        score=brier,
        reliability=reliability,
        resolution=resolution,
        uncertainty=uncertainty,
        n=n,
    )


def log_score(
    forecast: float,
    outcome: int | float,
    epsilon: float = 1e-15,
) -> float:
    """Logarithmic loss (negative log likelihood). Lower is better."""
    p = _validate_probability(forecast)
    o = _validate_binary_outcome(outcome)
    p = max(epsilon, min(1.0 - epsilon, p))
    if o == 1:
        return -math.log(p)
    return -math.log(1.0 - p)


def crps_empirical(samples: Sequence[float], observation: float) -> float:
    """
    CRPS from empirical samples vs observation in [0, 1].
    CRPS = E|X - y| - 0.5 * E|X - X'| (expectations over empirical distribution).
    """
    n = len(samples)
    if n == 0:
        return float("inf")
    s = [max(0.0, min(1.0, float(x))) for x in samples]
    y = max(0.0, min(1.0, float(observation)))
    m1 = sum(abs(x - y) for x in s) / n
    pair_sum = 0.0
    for i in range(n):
        for j in range(n):
            pair_sum += abs(s[i] - s[j])
    m2 = pair_sum / (n * n)
    return m1 - 0.5 * m2


def calibration_curve(
    forecasts: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> tuple[list[CalibrationBin], float]:
    """
    Equal-width bins on [0, 1]. Returns bins and overconfidence score
    (positive => forecasts systematically too extreme vs outcomes).
    """
    fs = [max(0.0, min(1.0, float(f))) for f in forecasts]
    os_list = [1 if int(o) else 0 for o in outcomes]
    n = len(fs)
    if n == 0 or len(os_list) != n:
        return [], 0.0

    bins_data: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for f, o in zip(fs, os_list, strict=True):
        bins_data[_bin_index(f, n_bins)].append((f, o))

    curve: list[CalibrationBin] = []
    total_weight = 0
    total_overconf = 0.0

    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        pairs = bins_data.get(i, [])
        if not pairs:
            curve.append(
                CalibrationBin(
                    bin_lower=lo,
                    bin_upper=hi,
                    mean_forecast=0.0,
                    mean_outcome=0.0,
                    count=0,
                )
            )
            continue
        cnt = len(pairs)
        mf = sum(p[0] for p in pairs) / cnt
        mo = sum(p[1] for p in pairs) / cnt
        curve.append(
            CalibrationBin(
                bin_lower=lo,
                bin_upper=hi,
                mean_forecast=mf,
                mean_outcome=mo,
                count=cnt,
            )
        )
        if mf > 0.5 + 1e-12:
            total_overconf += (mf - mo) * cnt
        elif mf < 0.5 - 1e-12:
            total_overconf += (mo - mf) * cnt
        total_weight += cnt

    overconfidence = total_overconf / max(1, total_weight)
    return curve, overconfidence


def scoring_summary(
    forecasts: Sequence[float],
    outcomes: Sequence[int],
    mc_samples_per_forecast: Sequence[Sequence[float]] | None = None,
    n_bins: int = 10,
) -> ScoringReport:
    """Run Brier (+ decomposition), mean log score, optional mean CRPS, calibration."""
    fs = list(forecasts)
    os_list = list(outcomes)
    if len(fs) != len(os_list):
        raise ValueError(f"forecasts and outcomes must have the same length, got {len(fs)} and {len(os_list)}")
    if len(fs) == 0:
        brier, decomp = brier_score_batch(fs, os_list, n_bins=n_bins)
        cal_bins, overconf = calibration_curve(fs, os_list, n_bins=n_bins)
        return ScoringReport(
            brier=decomp,
            mean_log_score=0.0,
            mean_crps=None,
            calibration=cal_bins,
            overconfidence=overconf,
            n_forecasts=0,
            log_scores=[],
        )

    brier, decomp = brier_score_batch(fs, os_list, n_bins=n_bins)
    log_scores = [log_score(f, o) for f, o in zip(fs, os_list, strict=True)]
    mean_log = sum(log_scores) / len(log_scores) if log_scores else 0.0

    cal_bins, overconf = calibration_curve(fs, os_list, n_bins=n_bins)

    mean_crps = None
    if mc_samples_per_forecast is not None and len(mc_samples_per_forecast) == len(fs):
        crps_vals: list[float] = []
        for samples, o in zip(mc_samples_per_forecast, os_list, strict=True):
            crps_vals.append(crps_empirical(samples, float(o)))
        mean_crps = sum(crps_vals) / len(crps_vals) if crps_vals else None

    return ScoringReport(
        brier=decomp,
        mean_log_score=mean_log,
        mean_crps=mean_crps,
        calibration=cal_bins,
        overconfidence=overconf,
        n_forecasts=len(fs),
        log_scores=log_scores,
    )
