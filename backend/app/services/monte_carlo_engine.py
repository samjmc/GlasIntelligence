"""
Lightweight Monte Carlo engine for Glas Intelligence.

Propagates uncertainty through LLM-generated probability estimates
(low/mid/high triplets) to produce proper statistical confidence intervals,
histograms, tail risk metrics, and convergence checks.

Aligned with the glas-core TypeScript MC engine API.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable


# ═══════════════════════════════════════════════════════════════
# Distribution Sampling
# ═══════════════════════════════════════════════════════════════


def _mulberry32(seed: int) -> Callable[[], float]:
    """Deterministic PRNG matching glas-core's Mulberry32."""
    state = [seed & 0xFFFFFFFF]

    def next_float() -> float:
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 0x100000000

    return next_float


def _sample_gamma(alpha: float, rng: Callable[[], float]) -> float:
    """Marsaglia and Tsang's method for gamma variates (alpha >= 1)."""
    if alpha < 1:
        return _sample_gamma(alpha + 1, rng) * (rng() ** (1.0 / alpha))
    d = alpha - 1.0 / 3.0
    c = 1.0 / math.sqrt(9.0 * d)
    while True:
        while True:
            u1 = max(rng(), 1e-10)
            u2 = rng()
            x = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
            v = 1.0 + c * x
            if v > 0:
                break
        v = v * v * v
        u = rng()
        x_sq = x * x
        if u < 1.0 - 0.0331 * x_sq * x_sq:
            return d * v
        if math.log(u) < 0.5 * x_sq + d * (1.0 - v + math.log(v)):
            return d * v


def sample_triangular(low: float, mode: float, high: float, rng: Callable[[], float]) -> float:
    u = rng()
    if high == low:
        return low
    fc = (mode - low) / (high - low)
    if u < fc:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1 - u) * (high - low) * (high - mode))


def sample_pert(low: float, mode: float, high: float, rng: Callable[[], float], lam: float = 4.0) -> float:
    """PERT distribution via Beta scaling."""
    if high <= low:
        return mode
    mu = (low + lam * mode + high) / (lam + 2)
    if mu <= low or mu >= high:
        mu = (low + high) / 2
    if abs(mode - mu) < 1e-10:
        a1 = 1.0 + lam / 2.0
    else:
        a1 = ((mu - low) * (2 * mode - low - high)) / ((mode - mu) * (high - low))
    if a1 <= 0:
        a1 = 1.5
    a2 = a1 * (high - mu) / (mu - low) if (mu - low) > 0 else a1
    if a2 <= 0:
        a2 = 1.5
    return sample_beta(a1, a2, rng) * (high - low) + low


def sample_beta(alpha: float, beta_param: float, rng: Callable[[], float]) -> float:
    if alpha <= 0:
        alpha = 0.5
    if beta_param <= 0:
        beta_param = 0.5
    x = _sample_gamma(alpha, rng)
    y = _sample_gamma(beta_param, rng)
    return x / (x + y) if (x + y) > 0 else 0.5


def sample_normal(mu: float, sigma: float, rng: Callable[[], float]) -> float:
    u1 = max(rng(), 1e-10)
    u2 = rng()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return mu + sigma * z


def sample_uniform(low: float, high: float, rng: Callable[[], float]) -> float:
    return low + rng() * (high - low)


def sample_from_distribution(dist: dict[str, Any], rng: Callable[[], float]) -> float:
    dtype = dist["type"]
    params = dist["params"]
    bounds = dist.get("bounds")

    if dtype == "triangular":
        val = sample_triangular(params[0], params[1], params[2], rng)
    elif dtype == "pert":
        val = sample_pert(params[0], params[1], params[2], rng)
    elif dtype == "beta":
        val = sample_beta(params[0], params[1], rng)
    elif dtype == "normal":
        val = sample_normal(params[0], params[1], rng)
    elif dtype == "uniform":
        val = sample_uniform(params[0], params[1], rng)
    else:
        raise ValueError(f"Unknown distribution type: {dtype}")

    if bounds:
        if bounds.get("min") is not None:
            val = max(val, bounds["min"])
        if bounds.get("max") is not None:
            val = min(val, bounds["max"])
    return val


# ═══════════════════════════════════════════════════════════════
# Convenience Builders (from LLM probability triplets)
# ═══════════════════════════════════════════════════════════════


def from_probability_estimate(low: float, mid: float, high: float) -> dict[str, Any]:
    """Convert a low/mid/high percentage triplet into a PERT distribution (0-1 scale)."""
    return {
        "type": "pert",
        "params": [low / 100.0, mid / 100.0, high / 100.0],
        "bounds": {"min": 0.0, "max": 1.0},
    }


def from_score_estimate(low: float, mid: float, high: float) -> dict[str, Any]:
    """Convert a low/mid/high score triplet into a triangular distribution."""
    return {
        "type": "triangular",
        "params": [low, mid, high],
    }


# ═══════════════════════════════════════════════════════════════
# Core Monte Carlo Engine
# ═══════════════════════════════════════════════════════════════


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (p / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


@dataclass
class HistogramBin:
    min_val: float = 0.0
    max_val: float = 0.0
    center: float = 0.0
    count: int = 0
    percentage: float = 0.0
    cumulative_percentage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "min": round(self.min_val, 6),
            "max": round(self.max_val, 6),
            "center": round(self.center, 6),
            "count": self.count,
            "percentage": round(self.percentage, 2),
            "cumulative_percentage": round(self.cumulative_percentage, 2),
        }


@dataclass
class MonteCarloResult:
    mean: float = 0.0
    median: float = 0.0
    std_dev: float = 0.0
    mode: float = 0.0
    confidence_intervals: dict[str, list[float]] = field(default_factory=dict)
    histogram: list[HistogramBin] = field(default_factory=list)
    tail_risk: dict[str, float] = field(default_factory=dict)
    convergence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": round(self.mean, 6),
            "median": round(self.median, 6),
            "std_dev": round(self.std_dev, 6),
            "mode": round(self.mode, 6),
            "confidence_intervals": {k: [round(v[0], 6), round(v[1], 6)] for k, v in self.confidence_intervals.items()},
            "histogram": [b.to_dict() for b in self.histogram],
            "tail_risk": {k: round(v, 6) for k, v in self.tail_risk.items()},
            "convergence": self.convergence,
            "metadata": self.metadata,
        }


def run_monte_carlo(
    inputs: dict[str, dict[str, Any]],
    model: Callable[[dict[str, float]], float],
    iterations: int = 10000,
    seed: int | None = None,
    confidence_levels: list[float] | None = None,
    histogram_bins: int = 20,
) -> MonteCarloResult:
    """
    Run Monte Carlo simulation.

    Args:
        inputs: Named distributional inputs, each with type/params/bounds.
        model: Deterministic function mapping sampled input values to a scalar output.
        iterations: Number of MC draws.
        seed: Optional random seed for reproducibility.
        confidence_levels: CI levels (default [0.90, 0.95, 0.99]).
        histogram_bins: Number of histogram bins.

    Returns:
        MonteCarloResult with CIs, histogram, tail risk, and convergence info.
    """
    if confidence_levels is None:
        confidence_levels = [0.90, 0.95, 0.99]

    rng = _mulberry32(seed) if seed is not None else random.random

    results: list[float] = []
    for _ in range(iterations):
        sample = {}
        for key, dist in inputs.items():
            sample[key] = sample_from_distribution(dist, rng)
        results.append(model(sample))

    sorted_results = sorted(results)
    n = len(sorted_results)

    mean = sum(sorted_results) / n
    median = _percentile(sorted_results, 50)
    variance = sum((x - mean) ** 2 for x in sorted_results) / n
    std_dev = math.sqrt(variance)

    cis: dict[str, list[float]] = {}
    for level in confidence_levels:
        alpha = (1 - level) / 2
        lower = _percentile(sorted_results, alpha * 100)
        upper = _percentile(sorted_results, (1 - alpha) * 100)
        cis[f"{int(level * 100)}%"] = [lower, upper]

    # Histogram
    min_val = sorted_results[0] if sorted_results else 0
    max_val = sorted_results[-1] if sorted_results else 0
    bin_width = (max_val - min_val) / histogram_bins if max_val > min_val else 1.0
    hist_bins: list[HistogramBin] = []
    cumulative = 0.0
    for i in range(histogram_bins):
        b_min = min_val + i * bin_width
        b_max = min_val + (i + 1) * bin_width
        count = sum(1 for v in sorted_results if b_min <= v < b_max or (i == histogram_bins - 1 and v == b_max))
        pct = (count / n) * 100
        cumulative += pct
        hist_bins.append(
            HistogramBin(
                min_val=b_min,
                max_val=b_max,
                center=(b_min + b_max) / 2,
                count=count,
                percentage=pct,
                cumulative_percentage=cumulative,
            )
        )

    mode_bin = max(hist_bins, key=lambda b: b.count) if hist_bins else HistogramBin()
    mode = mode_bin.center

    # Tail risk
    p1 = _percentile(sorted_results, 1)
    p5 = _percentile(sorted_results, 5)
    p99 = _percentile(sorted_results, 99)
    worst_5pct_cutoff = max(1, int(math.ceil(n * 0.05)))
    expected_shortfall = sum(sorted_results[:worst_5pct_cutoff]) / worst_5pct_cutoff

    # Convergence check
    se = std_dev / math.sqrt(n) if n > 0 else 0
    relative_error = (se / abs(mean)) if abs(mean) > 1e-10 else se
    converged = relative_error < 0.02
    recommended = None
    if not converged and relative_error > 0:
        recommended = int(n * (relative_error / 0.01) ** 2)

    result = MonteCarloResult(
        mean=mean,
        median=median,
        std_dev=std_dev,
        mode=mode,
        confidence_intervals=cis,
        histogram=hist_bins,
        tail_risk={
            "percentile_1": p1,
            "percentile_5": p5,
            "percentile_99": p99,
            "expected_shortfall": expected_shortfall,
        },
        convergence={
            "converged": converged,
            "relative_error": round(relative_error, 6),
            "standard_error": round(se, 6),
            "recommended_iterations": recommended,
        },
        metadata={
            "iterations": iterations,
            "seed": seed,
            "input_count": len(inputs),
        },
    )
    return result


# ═══════════════════════════════════════════════════════════════
# High-Level: MC from Probability Estimates
# ═══════════════════════════════════════════════════════════════


def run_monte_carlo_on_estimates(
    estimates: list[dict[str, Any]],
    iterations: int = 10000,
    seed: int | None = 42,
) -> list[dict[str, Any]]:
    """
    Run Monte Carlo on a list of ProbabilityEstimate dicts.

    Each estimate has probability_range {low, mid, high} (percentages 0-100).
    Returns a list of MC result dicts, one per estimate.
    """
    mc_results = []
    for est in estimates:
        pr = est.get("probability_range", {})
        low = pr.get("low", 0)
        mid = pr.get("mid", 0)
        high = pr.get("high", 0)

        if low >= high:
            mc_results.append(None)
            continue

        inputs = {
            "probability": from_probability_estimate(low, mid, high),
        }

        def identity_model(sample: dict[str, float]) -> float:
            return sample["probability"] * 100  # back to percentage scale

        mc = run_monte_carlo(
            inputs=inputs,
            model=identity_model,
            iterations=iterations,
            seed=seed,
        )
        mc_results.append(
            {
                "outcome": est.get("outcome", ""),
                "original_range": {"low": low, "mid": mid, "high": high},
                "monte_carlo": mc.to_dict(),
            }
        )

    return mc_results


def run_composite_monte_carlo(
    estimates: list[dict[str, Any]],
    iterations: int = 10000,
    seed: int | None = 42,
) -> dict[str, Any]:
    """
    Run a composite MC that aggregates all outcome probabilities into
    a weighted score, producing a single distribution for the overall
    scenario favorability.

    Each estimate contributes its midpoint probability to the composite.
    """
    if not estimates:
        return {}

    valid_estimates = []
    for est in estimates:
        pr = est.get("probability_range", {})
        low, mid, high = pr.get("low", 0), pr.get("mid", 0), pr.get("high", 0)
        if low < high:
            valid_estimates.append({"low": low, "mid": mid, "high": high})

    if not valid_estimates:
        return {}

    inputs = {}
    for i, ve in enumerate(valid_estimates):
        inputs[f"est_{i}"] = from_probability_estimate(ve["low"], ve["mid"], ve["high"])

    n_est = len(valid_estimates)

    def composite_model(sample: dict[str, float]) -> float:
        return sum(sample[f"est_{i}"] for i in range(n_est)) / n_est * 100

    mc = run_monte_carlo(
        inputs=inputs,
        model=composite_model,
        iterations=iterations,
        seed=seed,
    )
    return mc.to_dict()
