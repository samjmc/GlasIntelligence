"""Tests for calibration grading (backend/app/services/calibration_grading.py).

Mirrors the shared interface contract: case_id == simulation_id, dimension ==
scenario name, predicted_score / actual_score on a 0-100 scale, and binary
resolution detection when actual_score is exactly 0.0 or 100.0.
"""

import math

from app.services.calibration_grading import compute_calibration_grades


class TestSinglePair:
    def test_basic_metrics(self):
        grades = compute_calibration_grades(
            predictions=[{"case_id": "sim_a", "dimension": "Trade deal signed", "predicted_score": 70}],
            outcomes=[{"case_id": "sim_a", "dimension": "Trade deal signed", "actual_score": 60}],
        )
        assert grades["errors"] == {"Trade deal signed": [10.0]}
        assert grades["dimension_biases"] == {"Trade deal signed": 10.0}
        assert grades["dimension_accuracies"] == {"Trade deal signed": 0.90}
        assert grades["overall_accuracy"] == 0.90
        assert grades["total_cases"] == 1
        assert grades["n_predictions"] == 1
        assert "binary" not in grades


class TestMultiDimensionMultiCase:
    def test_known_aggregates(self):
        predictions = [
            {"case_id": "case_a", "dimension": "dim1", "predicted_score": 80},
            {"case_id": "case_a", "dimension": "dim2", "predicted_score": 50},
            {"case_id": "case_b", "dimension": "dim1", "predicted_score": 30},
        ]
        outcomes = [
            {"case_id": "case_a", "dimension": "dim1", "actual_score": 60},
            {"case_id": "case_a", "dimension": "dim2", "actual_score": 40},
            {"case_id": "case_b", "dimension": "dim1", "actual_score": 80},
        ]
        grades = compute_calibration_grades(predictions, outcomes)
        assert grades["n_predictions"] == 3
        assert grades["total_cases"] == 2
        assert grades["errors"] == {"dim1": [20.0, -50.0], "dim2": [10.0]}
        assert grades["dimension_biases"] == {"dim1": -15.0, "dim2": 10.0}
        assert grades["dimension_accuracies"] == {"dim1": 0.65, "dim2": 0.90}
        assert math.isclose(grades["overall_accuracy"], 1.0 - (80.0 / 3.0) / 100.0)
        assert "binary" not in grades


class TestBinaryCohort:
    def test_single_binary_pair(self):
        grades = compute_calibration_grades(
            predictions=[{"case_id": "sim_a", "dimension": "Deal signed", "predicted_score": 70}],
            outcomes=[{"case_id": "sim_a", "dimension": "Deal signed", "actual_score": 100}],
        )
        binary = grades["binary"]
        assert binary["n"] == 1
        assert binary["forecasts"] == [0.7]
        assert binary["outcomes"] == [1.0]
        assert binary["brier"] == (0.7 - 1.0) ** 2
        assert math.isclose(binary["mean_log_score"], -math.log(0.7))

    def test_mixed_cohort_only_binary_counted(self):
        predictions = [
            {"case_id": "sim_a", "dimension": "Yes/No", "predicted_score": 70},
            {"case_id": "sim_a", "dimension": "Magnitude", "predicted_score": 40},
        ]
        outcomes = [
            {"case_id": "sim_a", "dimension": "Yes/No", "actual_score": 100},
            {"case_id": "sim_a", "dimension": "Magnitude", "actual_score": 40},
        ]
        grades = compute_calibration_grades(predictions, outcomes)
        assert grades["n_predictions"] == 2
        binary = grades["binary"]
        assert binary["n"] == 1
        assert binary["forecasts"] == [0.7]
        assert binary["outcomes"] == [1.0]

    def test_binary_outcome_zero(self):
        grades = compute_calibration_grades(
            predictions=[{"case_id": "sim_a", "dimension": "Deal collapses", "predicted_score": 25}],
            outcomes=[{"case_id": "sim_a", "dimension": "Deal collapses", "actual_score": 0}],
        )
        binary = grades["binary"]
        assert binary["n"] == 1
        assert binary["outcomes"] == [0.0]
        assert binary["brier"] == (0.25 - 0.0) ** 2


class TestMatching:
    def test_unmatched_predictions_excluded(self):
        predictions = [
            {"case_id": "sim_a", "dimension": "Matched", "predicted_score": 70},
            {"case_id": "sim_a", "dimension": "Unresolved", "predicted_score": 90},
            {"case_id": "sim_b", "dimension": "No outcome", "predicted_score": 60},
        ]
        outcomes = [{"case_id": "sim_a", "dimension": "Matched", "actual_score": 60}]
        grades = compute_calibration_grades(predictions, outcomes)
        assert grades["n_predictions"] == 1
        assert grades["total_cases"] == 1
        assert grades["errors"] == {"Matched": [10.0]}

    def test_outcomes_without_predictions_excluded(self):
        predictions = [{"case_id": "sim_a", "dimension": "Matched", "predicted_score": 70}]
        outcomes = [
            {"case_id": "sim_a", "dimension": "Matched", "actual_score": 60},
            {"case_id": "sim_b", "dimension": "No prediction", "actual_score": 80},
        ]
        grades = compute_calibration_grades(predictions, outcomes)
        assert grades["n_predictions"] == 1
        assert grades["errors"] == {"Matched": [10.0]}


class TestEmptyInputs:
    def test_empty_lists_return_zero_shape(self):
        grades = compute_calibration_grades([], [])
        assert grades["errors"] == {}
        assert grades["dimension_biases"] == {}
        assert grades["dimension_accuracies"] == {}
        assert grades["overall_accuracy"] == 0.0
        assert grades["total_cases"] == 0
        assert grades["n_predictions"] == 0
        assert "binary" not in grades


class TestBiasSign:
    def test_overprediction_is_positive_bias(self):
        grades = compute_calibration_grades(
            predictions=[{"case_id": "sim_a", "dimension": "dim1", "predicted_score": 80}],
            outcomes=[{"case_id": "sim_a", "dimension": "dim1", "actual_score": 50}],
        )
        assert grades["errors"] == {"dim1": [30.0]}
        assert grades["dimension_biases"] == {"dim1": 30.0}

    def test_accuracy_clamped_at_zero(self):
        grades = compute_calibration_grades(
            predictions=[{"case_id": "sim_a", "dimension": "dim1", "predicted_score": 100}],
            outcomes=[{"case_id": "sim_a", "dimension": "dim1", "actual_score": 0}],
        )
        assert grades["dimension_accuracies"] == {"dim1": 0.0}
        assert grades["overall_accuracy"] == 0.0
        assert grades["binary"]["n"] == 1


class TestNullScoreRows:
    def test_null_scores_are_skipped(self):
        grades = compute_calibration_grades(
            predictions=[
                {"case_id": "sim_a", "dimension": "dim1", "predicted_score": None},
                {"case_id": "sim_a", "dimension": "dim1", "predicted_score": 70},
                {"case_id": "sim_b", "dimension": "dim2", "predicted_score": None},
            ],
            outcomes=[
                {"case_id": "sim_a", "dimension": "dim1", "actual_score": None},
                {"case_id": "sim_a", "dimension": "dim1", "actual_score": 60},
                {"case_id": "sim_b", "dimension": "dim2", "actual_score": 50},
            ],
        )
        assert grades["n_predictions"] == 1
        assert grades["errors"] == {"dim1": [10.0]}
        assert grades["total_cases"] == 1


class TestDuplicateOutcomeRows:
    def test_newest_created_at_wins(self):
        grades = compute_calibration_grades(
            predictions=[
                {"case_id": "sim_a", "dimension": "dim1", "predicted_score": 70},
            ],
            outcomes=[
                {"case_id": "sim_a", "dimension": "dim1", "actual_score": 60, "created_at": "2026-01-01T00:00:00Z"},
                {"case_id": "sim_a", "dimension": "dim1", "actual_score": 90, "created_at": "2026-06-01T00:00:00Z"},
            ],
        )
        assert grades["errors"] == {"dim1": [-20.0]}
        assert grades["dimension_biases"] == {"dim1": -20.0}
