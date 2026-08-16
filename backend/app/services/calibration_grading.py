"""
Calibration grading: compare recorded case predictions against resolved outcomes.

Pure, importable functions used by the ``calibration_ledger`` CLI script and
unit tests. No database access — callers pass in row dicts (as returned by
PostgREST) for ``case_predictions`` (case_id, dimension, predicted_score) and
``case_outcomes`` (case_id, dimension, actual_score).

Score conventions (0-100 scale):
- error = predicted - actual (positive = overpredict).
- accuracy = max(0.0, 1 - mean(|error|) / 100).
- Binary resolutions: actual_score in {0, 100} -> probability = predicted/100,
  outcome = actual/100, scored with ``forecast_scoring`` (Brier + log score).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .forecast_scoring import brier_score_batch, log_score

BINARY_OUTCOMES = (0.0, 100.0)


def compute_calibration_grades(predictions: list[dict], outcomes: list[dict]) -> dict[str, Any]:
    """
    Grade matched (case_id, dimension) prediction/outcome pairs.

    Predictions without a matching outcome (and vice versa) are excluded.
    Empty inputs return a zero-shaped result without raising.
    """
    outcome_map: dict[tuple[str, str], tuple[float, str]] = {}
    for outcome in outcomes:
        actual = outcome.get("actual_score")
        if actual is None:
            continue
        key = (outcome["case_id"], outcome["dimension"])
        entry = (float(actual), outcome.get("created_at") or "")
        if key not in outcome_map or entry[1] > outcome_map[key][1]:
            outcome_map[key] = entry

    matched = []
    for pred in predictions:
        key = (pred["case_id"], pred["dimension"])
        predicted = pred.get("predicted_score")
        if predicted is None:
            continue
        if key in outcome_map:
            matched.append((key, float(predicted), outcome_map[key][0]))
    matched.sort(key=lambda item: item[0])

    errors_by_dimension: dict[str, list[float]] = defaultdict(list)
    for (_case_id, dimension), predicted, actual in matched:
        errors_by_dimension[dimension].append(predicted - actual)

    dimension_biases = {d: sum(errs) / len(errs) for d, errs in errors_by_dimension.items()}
    dimension_accuracies = {
        d: max(0.0, 1.0 - (sum(abs(e) for e in errs) / len(errs)) / 100.0)
        for d, errs in errors_by_dimension.items()
    }

    all_errors = [e for errs in errors_by_dimension.values() for e in errs]
    overall_accuracy = 0.0
    if all_errors:
        mae = sum(abs(e) for e in all_errors) / len(all_errors)
        overall_accuracy = max(0.0, 1.0 - mae / 100.0)

    result: dict[str, Any] = {
        "errors": dict(errors_by_dimension),
        "dimension_biases": dimension_biases,
        "dimension_accuracies": dimension_accuracies,
        "overall_accuracy": overall_accuracy,
        "total_cases": len({m[0][0] for m in matched}),
        "n_predictions": len(matched),
    }

    binary_pairs = [
        (predicted / 100.0, actual / 100.0)
        for _key, predicted, actual in matched
        if actual in BINARY_OUTCOMES
    ]
    if binary_pairs:
        forecasts = [p for p, _o in binary_pairs]
        binary_outcomes = [o for _p, o in binary_pairs]
        brier, _decomposition = brier_score_batch(forecasts, [int(o) for o in binary_outcomes])
        log_scores = [log_score(f, o) for f, o in binary_pairs]
        result["binary"] = {
            "n": len(binary_pairs),
            "brier": brier,
            "mean_log_score": sum(log_scores) / len(log_scores),
            "forecasts": forecasts,
            "outcomes": binary_outcomes,
        }

    return result
