"""Tests for calibration_guardrails (glas-core discipline adapted for 0–100%)."""

import math
from typing import Any

import pytest

from app.services.calibration_guardrails import (
    MAX_PROBABILITY,
    MIN_PROBABILITY,
    apply_estimate_guardrails,
    apply_evidence_correlation_discount,
    bayesian_update_with_caps,
    bound_likelihood_ratio,
    cap_probability,
    detect_scale,
    enforce_ordering,
    enforce_range_width,
)


class TestDetectScale:
    def test_fractions_scaled(self):
        low, mid, high = detect_scale(0.2, 0.5, 0.8)
        assert (low, mid, high) == (20.0, 50.0, 80.0)

    def test_zeros_not_scaled(self):
        low, mid, high = detect_scale(0.0, 0.0, 0.0)
        assert (low, mid, high) == (0.0, 0.0, 0.0)

    def test_percentages_unchanged(self):
        low, mid, high = detect_scale(30.0, 50.0, 70.0)
        assert (low, mid, high) == (30.0, 50.0, 70.0)


class TestEnforceOrdering:
    def test_scrambled_sorted(self):
        low, mid, high = enforce_ordering(70.0, 30.0, 50.0)
        assert low <= mid <= high
        assert (low, mid, high) == (30.0, 30.0, 50.0)

    def test_already_ordered(self):
        assert enforce_ordering(10.0, 20.0, 30.0) == (10.0, 20.0, 30.0)


class TestEnforceRangeWidth:
    def test_narrow_widened(self):
        low, mid, high = enforce_range_width(48.0, 50.0, 52.0)
        assert high - low >= 5.0 - 1e-6
        assert abs(mid - 50.0) < 1.0

    def test_mid_zero_skipped(self):
        assert enforce_range_width(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0)


class TestCapProbability:
    def test_within_bounds(self):
        assert cap_probability(50.0) == 50.0

    def test_above_max(self):
        assert cap_probability(97.0) == MAX_PROBABILITY

    def test_below_min(self):
        assert cap_probability(3.0) == MIN_PROBABILITY

    def test_exact_boundary(self):
        assert cap_probability(95.0) == 95.0
        assert cap_probability(5.0) == 5.0

    def test_nan_becomes_min(self):
        assert cap_probability(float("nan")) == MIN_PROBABILITY


class TestBoundLikelihoodRatio:
    def test_within_bounds(self):
        assert bound_likelihood_ratio(5.0) == 5.0

    def test_above_max(self):
        assert bound_likelihood_ratio(100.0) == 20.0

    def test_below_min(self):
        assert bound_likelihood_ratio(0.01) == pytest.approx(1 / 20)

    def test_exactly_one(self):
        assert bound_likelihood_ratio(1.0) == 1.0

    def test_non_positive_returns_one(self):
        assert bound_likelihood_ratio(0.0) == 1.0
        assert bound_likelihood_ratio(-1.0) == 1.0


class TestApplyEvidenceCorrelationDiscount:
    def test_empty(self):
        assert apply_evidence_correlation_discount([]) == 1.0

    def test_single(self):
        lr = apply_evidence_correlation_discount([4.0])
        assert lr == 4.0

    def test_multiple_uncorrelated_path(self):
        lr = apply_evidence_correlation_discount([2.0, 2.0])
        assert 1.0 < lr <= 20.0

    def test_short_matrix_falls_back(self):
        lr = apply_evidence_correlation_discount([2.0, 2.0], correlation_matrix=[[1.0]])
        assert 1.0 < lr <= 20.0

    def test_matrix_path_between_uncorrelated_and_no_discount(self):
        lr = apply_evidence_correlation_discount(
            [2.0, 8.0], correlation_matrix=[[1.0, 0.3], [0.3, 1.0]]
        )
        uncorrelated = apply_evidence_correlation_discount([2.0, 8.0])
        no_discount = 16.0
        assert math.isfinite(lr)
        assert 1.0 / 20.0 <= lr <= 20.0
        assert lr != pytest.approx(uncorrelated)
        assert uncorrelated <= lr <= no_discount

    def test_matrix_asymmetric_weights_strictly_between(self):
        lr = apply_evidence_correlation_discount(
            [2.0, 6.0], correlation_matrix=[[1.0, 0.1], [0.9, 1.0]]
        )
        uncorrelated = apply_evidence_correlation_discount([2.0, 6.0])
        no_discount = 12.0
        assert uncorrelated < lr < no_discount

    def test_matrix_too_few_rows_falls_back_to_uncorrelated(self):
        matrix_lr = apply_evidence_correlation_discount(
            [2.0, 8.0], correlation_matrix=[[1.0]]
        )
        uncorrelated = apply_evidence_correlation_discount([2.0, 8.0])
        assert matrix_lr == pytest.approx(uncorrelated)

    def test_malformed_matrix_falls_back_to_uncorrelated(self):
        malformed: Any = [[1.0, "x"], [0.3, 1.0]]
        matrix_lr = apply_evidence_correlation_discount([2.0, 8.0], correlation_matrix=malformed)
        uncorrelated = apply_evidence_correlation_discount([2.0, 8.0])
        assert matrix_lr == pytest.approx(uncorrelated)


class TestBayesianUpdateWithCaps:
    def test_moderate_update(self):
        result = bayesian_update_with_caps(30.0, 3.0)
        assert MIN_PROBABILITY <= result["posterior"] <= MAX_PROBABILITY

    def test_extreme_lr_bounded(self):
        result = bayesian_update_with_caps(50.0, 1000.0)
        assert result["was_lr_bounded"]
        assert result["posterior"] <= MAX_PROBABILITY

    def test_prior_near_zero(self):
        result = bayesian_update_with_caps(5.0, 0.5)
        assert result["posterior"] >= MIN_PROBABILITY


class TestApplyEstimateGuardrails:
    def test_valid_input_unchanged(self):
        r = apply_estimate_guardrails(30.0, 50.0, 70.0)
        assert (r.low, r.mid, r.high) == (30.0, 50.0, 70.0)
        assert not r.was_corrected

    def test_decimal_scale_detected(self):
        r = apply_estimate_guardrails(0.2, 0.5, 0.8)
        assert (r.low, r.mid, r.high) == (20.0, 50.0, 80.0)
        assert r.was_corrected

    def test_ordering_fixed(self):
        r = apply_estimate_guardrails(70.0, 30.0, 50.0)
        assert r.low <= r.mid <= r.high

    def test_overconfident_capped(self):
        r = apply_estimate_guardrails(90.0, 97.0, 99.0)
        assert r.high <= MAX_PROBABILITY
        assert r.mid <= MAX_PROBABILITY

    def test_underconfident_floored(self):
        r = apply_estimate_guardrails(1.0, 2.0, 3.0)
        assert r.low >= MIN_PROBABILITY

    def test_narrow_range_widened(self):
        r = apply_estimate_guardrails(48.0, 50.0, 52.0)
        assert r.high - r.low >= 5.0 - 1e-6

    def test_negative_values_clamped(self):
        r = apply_estimate_guardrails(-10.0, 30.0, 110.0)
        assert r.low >= 0.0
        assert r.high <= 100.0

    def test_all_zero_gets_floored_with_caps(self):
        r = apply_estimate_guardrails(0.0, 0.0, 0.0)
        assert r.low >= MIN_PROBABILITY
        assert r.was_corrected

    def test_caps_disabled(self):
        r = apply_estimate_guardrails(2.0, 98.0, 99.0, apply_caps=False)
        assert r.mid == 98.0
        assert r.high == 99.0

    def test_audit_trail_populated(self):
        r = apply_estimate_guardrails(0.99, 0.5, 0.2)
        assert len(r.corrections) > 0
        assert r.was_corrected

    def test_to_estimate_fields(self):
        r = apply_estimate_guardrails(30.0, 50.0, 70.0)
        d = r.to_estimate_fields()
        assert d == {"probability_low": 30.0, "probability_mid": 50.0, "probability_high": 70.0}


class TestTripletPreservesFinite:
    def test_no_nan_output(self):
        r = apply_estimate_guardrails(float("nan"), 50.0, 60.0)
        assert all(math.isfinite(x) for x in (r.low, r.mid, r.high))
