"""
Calibration guardrails adapted from glas-core posterior discipline (BayesianCalibrationService).

Caps probability estimates, bounds likelihood ratios, and enforces sane low/mid/high
triplets for LLM probability outputs (0–100 scale). Pure functions; no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("glas.calibration_guardrails")

# From glas-core: MAX_POSTERIOR / MIN_UNCERTAINTY scaled to percentage points
MAX_PROBABILITY = 95.0
MIN_PROBABILITY = 5.0
MAX_LIKELIHOOD_RATIO = 20.0
CORRELATION_DISCOUNT = 0.7
MIN_RANGE_WIDTH = 5.0


@dataclass
class GuardrailResult:
    low: float
    mid: float
    high: float
    raw_low: float
    raw_mid: float
    raw_high: float
    corrections: list[str] = field(default_factory=list)
    was_corrected: bool = False

    def to_estimate_fields(self) -> dict[str, float]:
        return {
            "probability_low": self.low,
            "probability_mid": self.mid,
            "probability_high": self.high,
        }


def _is_finite(x: float) -> bool:
    return math.isfinite(x)


def _clamp_0_100(x: float) -> float:
    if not _is_finite(x):
        return 0.0
    return max(0.0, min(100.0, x))


def _detect_scale_with_reason(low: float, mid: float, high: float) -> tuple[float, float, float, str | None]:
    """
    If all values look like 0–1 fractions (each in [0, 1]), scale to 0–100.
    Does not scale mixed triplets (e.g. 0.5, 50, 80).

    Returns (low, mid, high, reason) where reason is None if unchanged,
    "scaled_from_01" if 0–1→100 scaling ran, or "clamped_non_finite" if
    non-finite inputs were clamped via _clamp_0_100.
    """
    if not all(_is_finite(v) for v in (low, mid, high)):
        return (
            _clamp_0_100(low),
            _clamp_0_100(mid),
            _clamp_0_100(high),
            "clamped_non_finite",
        )

    mx = max(low, mid, high)
    if mx > 0.0 and low >= 0 and mid >= 0 and high >= 0 and low <= 1.0 and mid <= 1.0 and high <= 1.0:
        logger.warning(
            "Probability triplet appears to be on 0–1 scale; scaling to 0–100: (%s, %s, %s)",
            low,
            mid,
            high,
        )
        return low * 100.0, mid * 100.0, high * 100.0, "scaled_from_01"

    return low, mid, high, None


def detect_scale(low: float, mid: float, high: float) -> tuple[float, float, float]:
    """
    If all values look like 0–1 fractions (each in [0, 1]), scale to 0–100.
    Does not scale mixed triplets (e.g. 0.5, 50, 80).
    """
    l, m, h, _ = _detect_scale_with_reason(low, mid, high)
    return l, m, h


def enforce_ordering(low: float, mid: float, high: float) -> tuple[float, float, float]:
    """Ensure low <= mid <= high; if inconsistent, coerce or sort."""
    low, mid, high = _clamp_0_100(low), _clamp_0_100(mid), _clamp_0_100(high)
    if low > mid:
        low = mid
    if mid > high:
        high = mid
    if low > high:
        vals = sorted([low, mid, high])
        return vals[0], vals[1], vals[2]
    return low, mid, high


def enforce_range_width(
    low: float,
    mid: float,
    high: float,
    min_width: float = MIN_RANGE_WIDTH,
) -> tuple[float, float, float]:
    """
    Widen (low, high) symmetrically around mid so span >= min_width when mid > 0.
    Skips degenerate single-point triplets and when mid == 0.
    """
    low, mid, high = enforce_ordering(low, mid, high)
    if mid <= 0:
        return low, mid, high
    if abs(high - low) < 1e-9 and abs(mid - low) < 1e-9:
        return low, mid, high

    span = high - low
    if span >= min_width - 1e-9:
        return low, mid, high

    half = max(span / 2.0, min_width / 2.0)
    new_low = mid - half
    new_high = mid + half
    if new_low < 0.0:
        shift = -new_low
        new_low = 0.0
        new_high = min(100.0, new_high + shift)
    if new_high > 100.0:
        shift = new_high - 100.0
        new_high = 100.0
        new_low = max(0.0, new_low - shift)

    new_low, mid, new_high = enforce_ordering(new_low, mid, new_high)
    if new_high - new_low < min_width - 1e-9:
        deficit = min_width - (new_high - new_low)
        new_low = max(0.0, new_low - deficit / 2.0)
        new_high = min(100.0, new_high + deficit / 2.0)
        new_low, mid, new_high = enforce_ordering(new_low, mid, new_high)

    return new_low, mid, new_high


def cap_probability(
    value: float,
    max_p: float = MAX_PROBABILITY,
    min_p: float = MIN_PROBABILITY,
) -> float:
    """Clamp a single percentage to [min_p, max_p] on 0–100 scale."""
    if not _is_finite(value):
        logger.warning("Non-finite probability replaced with min_p=%s", min_p)
        return min_p
    v = _clamp_0_100(value)
    if v > max_p:
        logger.warning(
            "Probability %.3f exceeds maximum %.3f; capping.",
            v,
            max_p,
        )
        return max_p
    if v < min_p:
        logger.warning(
            "Probability %.3f below minimum %.3f; raising.",
            v,
            min_p,
        )
        return min_p
    return v


def bound_likelihood_ratio(lr: float, max_lr: float = MAX_LIKELIHOOD_RATIO) -> float:
    if not _is_finite(lr) or lr <= 0:
        return 1.0
    if lr > max_lr:
        logger.warning(
            "Likelihood ratio %.4f exceeds maximum %.4f; bounding.",
            lr,
            max_lr,
        )
        return max_lr
    if lr < 1.0 / max_lr:
        logger.warning(
            "Likelihood ratio %.4f below minimum %.4f; bounding.",
            lr,
            1.0 / max_lr,
        )
        return 1.0 / max_lr
    return lr


def _uncorrelated_combined_log_lr(bounded: list[float]) -> float:
    """Effective-sample-size adjustment with default average correlation (no matrix)."""
    avg_correlation = 0.5
    n = len(bounded)
    effective_n = n / (1.0 + (n - 1) * avg_correlation)
    log_lr_sum = sum(math.log(lr) for lr in bounded)
    return log_lr_sum * (effective_n / n)


def apply_evidence_correlation_discount(
    likelihood_ratios: list[float],
    correlation_matrix: list[list[float]] | None = None,
    discount: float = CORRELATION_DISCOUNT,
) -> float:
    """
    Combine likelihood ratios with optional correlation structure.
    Uses math.log/exp (no numpy).
    """
    if not likelihood_ratios:
        return 1.0
    if len(likelihood_ratios) == 1:
        return bound_likelihood_ratio(likelihood_ratios[0])

    bounded = [bound_likelihood_ratio(lr) for lr in likelihood_ratios]

    if correlation_matrix is None:
        combined_log_lr = _uncorrelated_combined_log_lr(bounded)
    else:
        n = len(bounded)
        try:
            m = len(correlation_matrix)
            if m < n:
                logger.warning(
                    "correlation_matrix rows (%s) < likelihood_ratios (%s); using uncorrelated combine",
                    m,
                    n,
                )
                combined_log_lr = _uncorrelated_combined_log_lr(bounded)
            else:
                weights: list[float] = []
                for i in range(n):
                    row = correlation_matrix[i]
                    row_len = len(row) if isinstance(row, list) else 0
                    others = [row[j] for j in range(min(n, row_len)) if j != i]
                    avg_corr = sum(others) / max(1, len(others)) if others else 0.0
                    weights.append(1.0 - avg_corr * discount)
                wsum = sum(weights) or 1.0
                log_lr_sum = sum(w * math.log(lr) for w, lr in zip(weights, bounded, strict=False))
                combined_log_lr = log_lr_sum / wsum * len(weights)
        except (TypeError, ValueError, ZeroDivisionError, KeyError, IndexError) as e:
            logger.warning(
                "correlation_matrix combine failed (%s: %s); using uncorrelated combine",
                type(e).__name__,
                e,
            )
            combined_log_lr = _uncorrelated_combined_log_lr(bounded)

    combined_lr = math.exp(combined_log_lr)
    return bound_likelihood_ratio(combined_lr)


def bayesian_update_with_caps(
    prior: float,
    likelihood_ratio: float,
    max_p: float = MAX_PROBABILITY,
    min_p: float = MIN_PROBABILITY,
) -> dict[str, Any]:
    """
    Bayesian update on 0–100 prior; returns posterior in 0–100 with caps.
    """
    prior_01 = _clamp_0_100(prior) / 100.0
    bounded_lr = bound_likelihood_ratio(likelihood_ratio)

    if prior_01 >= 1.0:
        prior_odds = 999.0
    elif prior_01 <= 0.0:
        prior_odds = 1e-12
    else:
        prior_odds = prior_01 / (1.0 - prior_01)

    posterior_odds = prior_odds * bounded_lr
    raw_posterior_01 = posterior_odds / (1.0 + posterior_odds)
    raw_posterior = raw_posterior_01 * 100.0

    capped_posterior = cap_probability(raw_posterior, max_p=max_p, min_p=min_p)

    was_capped = abs(raw_posterior - capped_posterior) > 1e-9
    was_lr_bounded = abs(likelihood_ratio - bounded_lr) > 1e-9

    warnings: list[str] = []
    if was_capped:
        warnings.append(
            f"Posterior adjusted from {raw_posterior:.3f}% to {capped_posterior:.3f}% "
            f"(discipline bounds [{min_p}, {max_p}])."
        )
    if was_lr_bounded:
        warnings.append(f"Likelihood ratio bounded from {likelihood_ratio:.4f} to {bounded_lr:.4f}.")

    return {
        "posterior": capped_posterior,
        "raw_posterior": raw_posterior,
        "prior": prior,
        "likelihood_ratio": likelihood_ratio,
        "bounded_likelihood_ratio": bounded_lr,
        "was_capped": was_capped,
        "was_lr_bounded": was_lr_bounded,
        "warnings": warnings,
        "confidence_appropriate": len(warnings) == 0,
    }


def _triplet_equal(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    tol: float = 1e-6,
) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def apply_estimate_guardrails(
    low: float,
    mid: float,
    high: float,
    apply_caps: bool = True,
) -> GuardrailResult:
    """
    Full pipeline: scale detection, clamp, ordering, range width, optional caps.
    """
    raw_low, raw_mid, raw_high = low, mid, high
    corrections: list[str] = []

    # 1) Scale
    low, mid, high, scale_reason = _detect_scale_with_reason(low, mid, high)
    if scale_reason == "scaled_from_01":
        corrections.append("interpreted triplet as 0–1 scale and scaled to 0–100")
    elif scale_reason == "clamped_non_finite" and not _triplet_equal((low, mid, high), (raw_low, raw_mid, raw_high)):
        corrections.append("clamped non-finite input values to valid range")

    # 2) Clamp to [0, 100]
    prev = (low, mid, high)
    low, mid, high = _clamp_0_100(low), _clamp_0_100(mid), _clamp_0_100(high)
    if not _triplet_equal(prev, (low, mid, high)):
        corrections.append("clamped values to [0, 100]")

    # 3) Ordering
    prev = (low, mid, high)
    low, mid, high = enforce_ordering(low, mid, high)
    if not _triplet_equal(prev, (low, mid, high)):
        corrections.append("enforced low ≤ mid ≤ high")

    # 4) Range width (skip mid==0 or degenerate point)
    prev = (low, mid, high)
    if mid > 0 and not (abs(low - mid) < 1e-9 and abs(mid - high) < 1e-9):
        low, mid, high = enforce_range_width(low, mid, high)
    if not _triplet_equal(prev, (low, mid, high)):
        corrections.append(f"widened range to at least {MIN_RANGE_WIDTH}% span")

    # 5) Caps
    if apply_caps:
        prev = (low, mid, high)
        low = cap_probability(low)
        mid = cap_probability(mid)
        high = cap_probability(high)
        if not _triplet_equal(prev, (low, mid, high)):
            corrections.append(f"capped/floored to [{MIN_PROBABILITY}, {MAX_PROBABILITY}]%")

    # 6) Re-order after caps
    prev = (low, mid, high)
    low, mid, high = enforce_ordering(low, mid, high)
    if not _triplet_equal(prev, (low, mid, high)):
        corrections.append("re-enforced ordering after caps")

    was_corrected = len(corrections) > 0 or not _triplet_equal(
        (low, mid, high),
        (raw_low, raw_mid, raw_high),
    )

    return GuardrailResult(
        low=low,
        mid=mid,
        high=high,
        raw_low=raw_low,
        raw_mid=raw_mid,
        raw_high=raw_high,
        corrections=corrections,
        was_corrected=was_corrected,
    )
