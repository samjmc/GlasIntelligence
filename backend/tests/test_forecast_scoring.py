"""Tests for forecast_scoring (Brier, log score, CRPS, calibration)."""

import math

import pytest

from app.services.forecast_scoring import (
    brier_score,
    brier_score_batch,
    calibration_curve,
    crps_empirical,
    log_score,
    scoring_summary,
)


class TestBrierScore:
    def test_perfect_forecast(self):
        assert brier_score(1.0, 1) == 0.0
        assert brier_score(0.0, 0) == 0.0

    def test_worst_forecast(self):
        assert brier_score(1.0, 0) == 1.0

    def test_fifty_fifty(self):
        assert brier_score(0.5, 1) == 0.25


class TestBrierDecomposition:
    def test_decomposition_identity(self):
        fs = [0.1, 0.4, 0.6, 0.9, 0.8, 0.3, 0.7, 0.2]
        ys = [0, 0, 1, 1, 1, 0, 1, 0]
        score, decomp = brier_score_batch(fs, ys)
        reconstructed = decomp.reliability - decomp.resolution + decomp.uncertainty
        assert abs(score - reconstructed) < 0.02
        assert abs(decomp.score - score) < 1e-9


class TestLogScore:
    def test_perfect(self):
        assert log_score(0.999, 1) < 0.01

    def test_confident_wrong(self):
        assert log_score(0.99, 0) > 4.0

    def test_symmetric(self):
        assert abs(log_score(0.3, 0) - log_score(0.7, 1)) < 0.001


class TestCRPS:
    def test_perfect_distribution(self):
        assert crps_empirical([0.5] * 100, 0.5) < 0.001

    def test_spread_distribution(self):
        narrow = crps_empirical([0.49, 0.50, 0.51] * 100, 0.5)
        wide = crps_empirical([0.1, 0.5, 0.9] * 100, 0.5)
        assert wide > narrow

    def test_empty_samples(self):
        assert crps_empirical([], 0.5) == float("inf")


class TestCalibrationCurve:
    def test_perfect_calibration_rough(self):
        fs = [0.1] * 10 + [0.9] * 10
        ys = [0] * 9 + [1] * 1 + [1] * 9 + [0] * 1
        bins, overconf = calibration_curve(fs, ys)
        assert len(bins) == 10
        assert abs(overconf) < 0.25


class TestScoringSummary:
    def test_runs_without_mc(self):
        fs = [0.2, 0.8]
        ys = [0, 1]
        rep = scoring_summary(fs, ys)
        assert rep.n_forecasts == 2
        assert rep.mean_crps is None
        assert len(rep.log_scores) == 2

    def test_with_mc_samples(self):
        fs = [0.5, 0.5]
        ys = [1, 0]
        mc = [[0.4, 0.5, 0.6], [0.4, 0.5, 0.6]]
        rep = scoring_summary(fs, ys, mc_samples_per_forecast=mc)
        assert rep.mean_crps is not None
        assert math.isfinite(rep.mean_crps)
