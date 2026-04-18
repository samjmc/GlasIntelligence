"""Unit tests for bundle executive synthesis math (no LLM)."""

from app.services.bundle_synthesis import (
    compute_marginals_and_recalc,
    normalize_branch_weights,
    recompute_marginals_from_weights,
)


def test_normalize_branch_weights_renormalizes():
    raw = [
        {"scenario_index": 0, "p_branch": 0.5, "rationale": "x"},
        {"scenario_index": 2, "p_branch": 0.5, "rationale": "y"},
    ]
    out = normalize_branch_weights([0, 2], raw)
    assert len(out) == 2
    assert {b["scenario_index"] for b in out} == {0, 2}
    assert abs(sum(b["p_branch"] for b in out) - 1.0) < 1e-9


def test_normalize_branch_weights_positional_fallback():
    raw = [{"scenario_index": 0, "p_branch": 0.2}, {"scenario_index": 1, "p_branch": 0.8}]
    out = normalize_branch_weights([5, 9], raw)
    assert out[0]["scenario_index"] == 5
    assert out[1]["scenario_index"] == 9
    assert abs(sum(b["p_branch"] for b in out) - 1.0) < 1e-9


def test_compute_marginals_weighted_average():
    payloads = {
        0: {
            "quantitative_analysis": {
                "risks": {
                    "probability_assessment": {
                        "estimates": [
                            {
                                "outcome": "A",
                                "probability_range": {"mid": 60, "low": 50, "high": 70},
                            },
                        ]
                    }
                }
            }
        },
        1: {
            "quantitative_analysis": {
                "risks": {
                    "probability_assessment": {
                        "estimates": [
                            {
                                "outcome": "A",
                                "probability_range": {"mid": 40, "low": 30, "high": 50},
                            },
                        ]
                    }
                }
            }
        },
    }
    canonical = [
        {
            "outcome_id": "a",
            "label": "Outcome A",
            "mapping": [
                {"scenario_index": 0, "estimate_index": 0},
                {"scenario_index": 1, "estimate_index": 0},
            ],
        }
    ]
    weights = [
        {"scenario_index": 0, "p_branch": 0.5, "rationale": ""},
        {"scenario_index": 1, "p_branch": 0.5, "rationale": ""},
    ]
    out, recalc = compute_marginals_and_recalc(canonical, weights, payloads)
    assert len(out) == 1
    assert out[0]["marginal_mid_percent"] is not None
    assert abs(out[0]["marginal_mid_percent"] - 50.0) < 0.5
    assert len(recalc) == 1
    assert len(recalc[0]["per_branch"]) == 2


def test_recompute_marginals_from_weights_flag():
    synthesis = {
        "canonical_outcomes": [
            {
                "outcome_id": "a",
                "label": "A",
                "mapping": [
                    {"scenario_index": 0, "estimate_index": 0},
                    {"scenario_index": 1, "estimate_index": 0},
                ],
            }
        ],
        "branch_weights": [
            {"scenario_index": 0, "p_branch": 0.5, "rationale": "was"},
            {"scenario_index": 1, "p_branch": 0.5, "rationale": "was"},
        ],
        "llm_assigned_weights": True,
    }
    payloads = {
        0: {
            "quantitative_analysis": {
                "risks": {"probability_assessment": {"estimates": [{"probability_range": {"mid": 80}}]}}
            }
        },
        1: {
            "quantitative_analysis": {
                "risks": {"probability_assessment": {"estimates": [{"probability_range": {"mid": 20}}]}}
            }
        },
    }
    updated = recompute_marginals_from_weights(
        synthesis,
        [{"scenario_index": 0, "p_branch": 0.9}, {"scenario_index": 1, "p_branch": 0.1}],
        payloads,
    )
    assert updated["llm_assigned_weights"] is False
    assert len(updated["outcomes"]) == 1
    assert updated["outcomes"][0]["marginal_mid_percent"] > 70
