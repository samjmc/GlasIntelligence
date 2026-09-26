"""POST /api/simulation/suggest-followups.

Until this was fixed the endpoint returned 500 on every call: 9849885 moved it into
simulation.py but left FOLLOWUP_SYSTEM_PROMPT behind, and the prompt was later deleted.
"""

import json
from types import SimpleNamespace

import pytest

from app.api import simulation as simulation_api

_SUGGESTIONS = [
    {
        "title": "Costs up 20%",
        "scenario": "Same scenario, but operating costs rise 20%.",
        "change_summary": "+20% operating costs",
        "variation_type": "cost",
        "parameter": "operating costs",
        "magnitude": "+20%",
    }
]


@pytest.fixture
def llm_calls(monkeypatch):
    """Stub the report lookup and the LLM; return the list of chat() calls."""

    class Calls(list):
        fake = None

    calls = Calls()

    class FakeLLM:
        reply = json.dumps(_SUGGESTIONS)

        def chat(self, messages, **kwargs):
            calls.append(messages)
            return FakeLLM.reply

    monkeypatch.setattr(simulation_api, "LLMClient", FakeLLM)
    monkeypatch.setattr(
        simulation_api.ReportManager, "get_report", classmethod(lambda cls, rid: SimpleNamespace(simulation_id="sim_x"))
    )
    monkeypatch.setattr(
        simulation_api.ReportManager,
        "load_payload_v1",
        classmethod(lambda cls, rid: {"simulation_requirement": "Cap pharmacy fees at 5%", "decision": {}}),
    )
    calls.fake = FakeLLM
    return calls


def test_returns_the_llm_suggestions(client, llm_calls):
    res = client.post("/api/simulation/suggest-followups", json={"report_id": "report_x"})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["data"]["suggestions"] == _SUGGESTIONS


def test_system_prompt_asks_for_the_fields_the_frontend_reads(client, llm_calls):
    client.post("/api/simulation/suggest-followups", json={"report_id": "report_x"})
    assert len(llm_calls) == 1
    system = llm_calls[0][0]
    assert system["role"] == "system"
    # Step4Report.vue renders title, change_summary, variation_type, magnitude and re-runs `scenario`.
    for field in ("title", "scenario", "change_summary", "variation_type", "magnitude"):
        assert f'"{field}"' in system["content"], field
    assert 'Original scenario: "Cap pharmacy fees at 5%"' in llm_calls[0][1]["content"]


def test_json_wrapped_in_prose_is_still_parsed(client, llm_calls):
    llm_calls.fake.reply = "Here you go:\n" + json.dumps(_SUGGESTIONS) + "\nGood luck."
    res = client.post("/api/simulation/suggest-followups", json={"report_id": "report_x"})
    assert res.status_code == 200
    assert res.get_json()["data"]["suggestions"] == _SUGGESTIONS
