"""Tests for demo-mode canned agent interviews.

The static demo cannot interview live OASIS agents (the subprocess is gone),
so DEMO_MODE serves pre-recorded, scenario-grounded responses. These tests
pin the contract: shape-compatible with the live path, keyword-matched
responses, and an explicit "recorded" marker so visitors can't mistake the
output for live agent behavior.
"""

import pytest

from app.services.demo_interviews import canned_batch, canned_response


class TestCannedResponse:
    def test_keyword_matches_scenario_response(self):
        """'cap' routes to the pharmacy-sector response with a recorded marker."""
        res = canned_response(0, "What do you think about the payment caps?")
        assert "caps" in res["response"].lower()
        assert "recorded response" in res["response"].lower()
        assert res["platform"] == "reddit"

    def test_funding_question_routes_to_nhs_england(self):
        res = canned_response(4, "How will funding work next year?")
        assert "funding" in res["response"].lower()

    def test_gp_question_routes_to_gp_persona(self):
        res = canned_response(5, "what happens to GP appointments?")
        assert "gp" in res["response"].lower() or "general practice" in res["response"].lower()

    def test_unknown_question_falls_back_with_marker(self):
        """Unmatched questions get the opening position, still marked recorded."""
        res = canned_response(3, "what is the weather like in London?")
        assert "recorded response" in res["response"].lower()

    def test_response_uses_persona_name(self):
        res = canned_response(7, "tell me about workforce pressure")
        assert "pharmacists_292" in res["response"]

    def test_platform_respected(self):
        res = canned_response(0, "caps?", platform="twitter")
        assert res["platform"] == "twitter"


class TestCannedBatch:
    def test_batch_shape_matches_live_contract(self):
        """The result dict uses <platform>_<agent_id> keys like the live path."""
        res = canned_batch("demo-sim", [
            {"agent_id": 0, "prompt": "caps?"},
            {"agent_id": 4, "prompt": "funding?"},
        ])
        assert res["success"] is True
        results = res["data"]["result"]["results"]
        assert "reddit_0" in results
        assert "reddit_4" in results
        assert results["reddit_0"]["agent_id"] == 0

    def test_batch_honors_per_item_platform(self):
        res = canned_batch("demo-sim", [
            {"agent_id": 1, "prompt": "caps?", "platform": "twitter"},
        ])
        assert "twitter_1" in res["data"]["result"]["results"]
