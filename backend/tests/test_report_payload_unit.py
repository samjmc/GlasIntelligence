"""Unit tests for report payload generation and rendering."""

import pytest
from app.services.report_payload import (
    REPORT_PAYLOAD_VERSION,
    build_report_payload_v1,
    render_scenarios_markdown,
    render_financial_summary_markdown,
    render_causal_chain_markdown,
    render_decision_markdown,
    _placeholder_scenarios,
    payload_preamble_for_prompt,
)


class TestPlaceholderScenarios:
    def test_returns_three_scenarios(self):
        scenarios = _placeholder_scenarios()
        assert len(scenarios) == 3

    def test_scenario_structure(self):
        for s in _placeholder_scenarios():
            assert "name" in s
            assert "assumptions" in s
            assert "probability_range" in s
            pr = s["probability_range"]
            assert pr["low"] < pr["mid"] < pr["high"]


class TestBuildPayload:
    def test_minimal_payload(self):
        p = build_report_payload_v1(
            simulation_requirement="test",
            simulation_id="sim_1",
            graph_id="g_1",
            project=None,
            metrics_payload={"x": 1},
            positions_payload=None,
            risks_payload=None,
            stakeholder_matrix_payload=None,
            scenarios=_placeholder_scenarios(),
            staleness_warnings=[],
            claims=[],
        )
        assert p["version"] == REPORT_PAYLOAD_VERSION
        assert p["simulation_id"] == "sim_1"
        assert p["graph_id"] == "g_1"
        assert len(p["scenarios"]) == 3
        assert "decision" not in p

    def test_payload_with_decision(self):
        decision = {"verdict": "Proceed", "confidence": "High"}
        p = build_report_payload_v1(
            simulation_requirement="test",
            simulation_id="s",
            graph_id="g",
            project=None,
            metrics_payload=None,
            positions_payload=None,
            risks_payload=None,
            stakeholder_matrix_payload=None,
            scenarios=[],
            staleness_warnings=[],
            claims=[],
            decision_payload=decision,
        )
        assert p["decision"]["verdict"] == "Proceed"


class TestRenderScenarios:
    def test_render_non_empty(self):
        md = render_scenarios_markdown(_placeholder_scenarios())
        assert "Base case" in md
        assert "Stress" in md

    def test_render_empty_list(self):
        md = render_scenarios_markdown([])
        assert "Scenario ladder" in md


class TestRenderFinancialSummary:
    def test_none_returns_empty(self):
        assert render_financial_summary_markdown(None) == ""

    def test_not_applicable_returns_empty(self):
        assert render_financial_summary_markdown({"applicable": False}) == ""

    def test_applicable_renders_table(self):
        md = render_financial_summary_markdown({
            "applicable": True,
            "revenue_range": {"low": "10M", "high": "20M", "unit": "USD"},
        })
        assert "Revenue" in md
        assert "10M" in md


class TestRenderCausalChain:
    def test_none_returns_empty(self):
        assert render_causal_chain_markdown(None) == ""

    def test_renders_chain(self):
        chain = [{"cause": "A", "effect": "B", "confidence": "high"}]
        md = render_causal_chain_markdown(chain)
        assert "A" in md
        assert "B" in md


class TestRenderDecision:
    def test_none_returns_fallback(self):
        md = render_decision_markdown(None)
        assert "not available" in md

    def test_renders_verdict(self):
        md = render_decision_markdown({"verdict": "Go", "confidence": "Medium"})
        assert "Go" in md
        assert "Medium" in md


class TestPayloadPreamble:
    def test_truncates_large_payload(self):
        payload = {"data": "x" * 20000}
        result = payload_preamble_for_prompt(payload, max_chars=100)
        assert "..." in result
