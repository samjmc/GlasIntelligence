"""Tests for the Monte Carlo engine (app.services.monte_carlo_engine)."""

import math

import pytest

from app.services.monte_carlo_engine import (
    _mulberry32,
    _percentile,
    from_probability_estimate,
    from_score_estimate,
    run_monte_carlo,
    run_monte_carlo_on_estimates,
    sample_beta,
    sample_from_distribution,
    sample_pert,
    sample_triangular,
)

_ESTIMATES = [
    {"outcome": "a", "probability_range": {"low": 20.0, "mid": 45.0, "high": 90.0}},
    {"outcome": "b", "probability_range": {"low": 5.0, "mid": 30.0, "high": 85.0}},
]


def identity_percent(sample: dict[str, float]) -> float:
    return sample["probability"] * 100


class TestSeededDeterminism:
    def test_same_seed_identical_results(self):
        first = run_monte_carlo_on_estimates(_ESTIMATES, seed=42)
        second = run_monte_carlo_on_estimates(_ESTIMATES, seed=42)
        assert first == second

    def test_different_seed_differs(self):
        first = run_monte_carlo_on_estimates(_ESTIMATES, seed=42)
        second = run_monte_carlo_on_estimates(_ESTIMATES, seed=43)
        assert first[0]["monte_carlo"]["mean"] != second[0]["monte_carlo"]["mean"]

    def test_run_monte_carlo_same_seed_identical(self):
        inputs = {"probability": from_probability_estimate(20.0, 45.0, 90.0)}
        first = run_monte_carlo(inputs, identity_percent, iterations=5000, seed=42)
        second = run_monte_carlo(inputs, identity_percent, iterations=5000, seed=42)
        assert first == second
        assert first.to_dict() == second.to_dict()


class TestBoundsClamping:
    def test_normal_samples_clamped_to_bounds(self):
        dist = {"type": "normal", "params": [0.5, 0.4], "bounds": {"min": 0.0, "max": 1.0}}
        rng = _mulberry32(42)
        values = [sample_from_distribution(dist, rng) for _ in range(10000)]
        assert min(values) >= 0.0
        assert max(values) <= 1.0
        assert min(values) == 0.0


class TestPertMean:
    def test_pert_mean_first_triplet(self):
        inputs = {"probability": from_probability_estimate(20.0, 45.0, 90.0)}
        result = run_monte_carlo(inputs, identity_percent, iterations=10000, seed=42)
        assert abs(result.mean - (20.0 + 4 * 45.0 + 90.0) / 6) <= 0.5

    def test_pert_mean_second_triplet(self):
        inputs = {"probability": from_probability_estimate(5.0, 30.0, 85.0)}
        result = run_monte_carlo(inputs, identity_percent, iterations=10000, seed=42)
        assert abs(result.mean - (5.0 + 4 * 30.0 + 85.0) / 6) <= 0.5


class TestPercentilesAndCIs:
    def test_percentile_known_list(self):
        values = list(range(100))
        assert _percentile(values, 50) == 49.5
        assert _percentile(values, 5) == 4.95

    def test_normal_ci_coverage(self):
        dist = {"type": "normal", "params": [0.5, 0.1], "bounds": {"min": 0.0, "max": 1.0}}
        seed = 42
        iterations = 20000
        result = run_monte_carlo(
            {"x": dist}, lambda s: s["x"], iterations=iterations, seed=seed
        )
        lower, upper = result.confidence_intervals["95%"]
        rng = _mulberry32(seed)
        draws = [sample_from_distribution(dist, rng) for _ in range(iterations)]
        coverage = sum(1 for v in draws if lower <= v <= upper) / iterations * 100
        assert 92.0 <= coverage <= 98.0


class TestLowGreaterEqualHighContract:
    def test_invalid_estimates_become_none(self):
        estimates = [
            {"outcome": "ok", "probability_range": {"low": 20.0, "mid": 45.0, "high": 90.0}},
            {"outcome": "bad", "probability_range": {"low": 80.0, "mid": 60.0, "high": 40.0}},
            {"outcome": "equal", "probability_range": {"low": 50.0, "mid": 50.0, "high": 50.0}},
        ]
        results = run_monte_carlo_on_estimates(estimates, seed=42)
        assert len(results) == 3
        assert results[0] is not None
        assert results[0]["outcome"] == "ok"
        assert results[1] is None
        assert results[2] is None


class TestConvergenceSemantics:
    def test_deterministic_triangular_converges(self):
        inputs = {"score": from_score_estimate(40.0, 50.0, 60.0)}
        result = run_monte_carlo(inputs, lambda s: s["score"], iterations=10000, seed=42)
        assert result.convergence["converged"] is True
        assert result.convergence["relative_error"] < 0.02
        assert result.convergence["recommended_iterations"] is None


class TestSamplerEdgeCases:
    def test_triangular_low_equals_high(self):
        rng = _mulberry32(1)
        assert sample_triangular(5.0, 6.0, 5.0, rng) == 5.0
        assert sample_triangular(4.0, 4.0, 4.0, rng) == 4.0

    def test_pert_high_le_low_returns_mode(self):
        rng = _mulberry32(1)
        assert sample_pert(80.0, 50.0, 40.0, rng) == 50.0
        assert sample_pert(50.0, 60.0, 50.0, rng) == 60.0

    def test_beta_nonpositive_params_do_not_raise(self):
        rng = _mulberry32(1)
        for alpha, beta in [(0.0, 2.0), (-1.0, 2.0), (2.0, 0.0), (2.0, -1.0), (0.0, 0.0)]:
            value = sample_beta(alpha, beta, rng)
            assert math.isfinite(value)
            assert 0.0 <= value <= 1.0

    def test_unknown_distribution_raises(self):
        rng = _mulberry32(1)
        with pytest.raises(ValueError):
            sample_from_distribution({"type": "gamma", "params": [1.0, 1.0]}, rng)


class TestHistogramInvariants:
    def test_histogram_structure(self):
        inputs = {"probability": from_probability_estimate(20.0, 45.0, 90.0)}
        iterations = 10000
        result = run_monte_carlo(inputs, identity_percent, iterations=iterations, seed=42)
        assert len(result.histogram) == 20
        assert result.histogram[-1].cumulative_percentage >= 99.0
        assert sum(bin_.count for bin_ in result.histogram) == iterations
