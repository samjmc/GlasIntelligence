"""Jev fast path in front of the LLM: tool roles, stance classification, risk re-scoring.

Each integration must (a) use Jev's answer when it is confident, (b) hand only
the unsure items to the original LLM prompt, and (c) behave exactly as before
when Jev is off. No network: Jev is a fake, the LLM is a MagicMock.
"""

from unittest.mock import MagicMock, patch

import pytest

from app import config as app_config
from app.services import simulation_tools as st
from app.services.quantitative_analysis_service import QuantitativeAnalysisService
from app.utils.jev_client import JevAnswer, JevClient


class FakeJev:
    """Returns scripted per-item answers and records what it was asked."""

    def __init__(self, answers):
        self.answers = answers
        self.items = None

    def evaluate_many(self, items, max_workers=None):
        self.items = items
        assert len(items) == len(self.answers), "test script must cover every item"
        return self.answers


@pytest.fixture
def jev_on(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_MIN_CONFIDENCE", 0.6)

    def _install(answers):
        fake = FakeJev(answers)
        monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake))
        return fake

    return _install


@pytest.fixture
def jev_off(monkeypatch):
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))


# ====================================================================== tool roles


def _agents():
    return [
        {"agent_id": 0, "entity_name": "NHS England", "entity_type": "GovernmentBody", "stance": "supportive"},
        {"agent_id": 1, "entity_name": "Jane Doe", "entity_type": "Pharmacist", "stance": "opposing"},
        {"agent_id": 2, "entity_name": "The Guardian", "entity_type": "MediaOutlet", "stance": "neutral"},
    ]


def _llm_returning(text: str):
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content=text))]
    return mock_openai


def _llm_prompt(mock_openai) -> str:
    return mock_openai.return_value.chat.completions.create.call_args.kwargs["messages"][0]["content"]


def test_tool_roles_jev_confident_then_llm_only_for_unsure(monkeypatch, jev_on):
    fake = jev_on(
        [
            {"role": JevAnswer("choice", "leader", 0.95)},
            {"role": JevAnswer("choice", "observer", 0.40)},  # below threshold
            None,  # Jev call failed
        ]
    )
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"1": "observer", "2": "analyst"}')

    with patch("app.services.simulation_tools.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "Pharmacy First caps")

    assert result == {0: "leader", 1: "observer", 2: "analyst"}
    prompt = _llm_prompt(mock_openai)
    assert "NHS England" not in prompt
    assert "Jane Doe" in prompt and "The Guardian" in prompt
    assert fake.items[0][0] == {"name": "NHS England", "entity_type": "GovernmentBody", "stance": "supportive"}
    assert fake.items[0][1]["role"]["type"] == "choice"
    assert set(fake.items[0][1]["role"]["criteria"]) == set(st._TOOL_ROLE_OPTIONS)


def test_tool_roles_all_confident_skips_llm(monkeypatch, jev_on):
    jev_on([{"role": JevAnswer("choice", r, 0.9)} for r in ("leader", "observer", "analyst")])
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning("{}")

    with patch("app.services.simulation_tools.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "observer", 2: "analyst"}
    mock_openai.return_value.chat.completions.create.assert_not_called()


def test_tool_roles_jev_option_outside_set_falls_back(monkeypatch, jev_on):
    jev_on([{"role": JevAnswer("choice", "wizard", 0.99)}] + [{"role": JevAnswer("choice", "none", 0.9)}] * 2)
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"0": "leader"}')

    with patch("app.services.simulation_tools.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "none", 2: "none"}


def test_tool_roles_jev_off_sends_every_agent_to_llm(monkeypatch, jev_off):
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"0": "leader", "1": "observer", "2": "analyst"}')

    with patch("app.services.simulation_tools.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "observer", 2: "analyst"}
    prompt = _llm_prompt(mock_openai)
    assert all(name in prompt for name in ("NHS England", "Jane Doe", "The Guardian"))


def test_tool_roles_jev_off_no_llm_key_returns_empty(monkeypatch, jev_off):
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "")
    assert st.assign_tool_roles(_agents(), "req") == {}


def test_tool_roles_empty_input():
    assert st.assign_tool_roles([], "req") == {}


# ====================================================================== stance analysis


def _profiles():
    return [
        {
            "realname": "NHS England",
            "country": "UK",
            "source_entity_type": "GovernmentBody",
            "bio": "b",
            "persona": "p",
        },
        {"realname": "Jane Doe", "country": "UK", "source_entity_type": "Pharmacist", "bio": "b", "persona": "p"},
        {"realname": "The Guardian", "country": "UK", "source_entity_type": "MediaOutlet", "bio": "b", "persona": "p"},
    ]


def _service(monkeypatch, llm):
    svc = QuantitativeAnalysisService(llm_client=llm)
    monkeypatch.setattr(svc, "_load_agent_profiles", lambda _sim: _profiles())
    return svc


def _stance_prompt(llm) -> str:
    return llm.chat_json.call_args.kwargs["messages"][1]["content"]


def test_stance_jev_confident_then_llm_only_for_unsure(monkeypatch, jev_on):
    fake = jev_on(
        [
            {"position": JevAnswer("choice", "supportive", 0.9), "intensity": JevAnswer("score", 3.6, 0.9)},
            {"position": JevAnswer("choice", "opposing", 0.3), "intensity": JevAnswer("score", 2.0, 0.9)},
            None,
        ]
    )
    llm = MagicMock()
    llm.chat_json.return_value = {
        "stances": [
            {"agent_index": 1, "position": "opposing", "intensity": 4, "key_concern": "pay", "confidence": "high"},
            {"agent_index": 2, "position": "neutral", "intensity": 2},
        ]
    }
    svc = _service(monkeypatch, llm)

    result = svc.stance_analysis("sim", "Pharmacy First caps", "graph")

    assert result.agents_analyzed == 3
    assert [s.agent_name for s in result.stances] == ["NHS England", "Jane Doe", "The Guardian"]
    jev_stance = result.stances[0]
    assert (jev_stance.position, jev_stance.intensity, jev_stance.confidence) == ("supportive", 5, "high")
    assert jev_stance.key_concern == ""
    assert (result.stances[1].position, result.stances[1].intensity, result.stances[1].key_concern) == (
        "opposing",
        4,
        "pay",
    )
    prompt = _stance_prompt(llm)
    assert "NHS England" not in prompt
    assert "Jane Doe" in prompt and "The Guardian" in prompt
    assert result.position_distribution  # aggregates still computed
    assert fake.items[0][0]["agent"]["name"] == "NHS England"
    assert fake.items[0][1]["position"]["type"] == "choice"
    assert len(fake.items[0][1]["intensity"]["criteria"]) == 5


def test_stance_jev_moderate_confidence_label_and_intensity_clamp(monkeypatch, jev_on):
    jev_on(
        [
            {"position": JevAnswer("choice", "neutral", 0.7), "intensity": JevAnswer("score", -0.4, 0.9)},
            {"position": JevAnswer("choice", "neutral", 0.7), "intensity": JevAnswer("score", 4.4, 0.9)},
            {"position": JevAnswer("choice", "neutral", 0.7), "intensity": JevAnswer("score", 9.0, 0.9)},
        ]
    )
    llm = MagicMock()
    svc = _service(monkeypatch, llm)

    result = svc.stance_analysis("sim", "t", "g")

    assert [s.intensity for s in result.stances] == [1, 5, 5]
    assert {s.confidence for s in result.stances} == {"moderate"}
    llm.chat_json.assert_not_called()


def test_stance_jev_off_llm_failure_keeps_original_zero_result(monkeypatch, jev_off):
    llm = MagicMock()
    llm.chat_json.side_effect = RuntimeError("boom")
    svc = _service(monkeypatch, llm)

    result = svc.stance_analysis("sim", "t", "g")

    assert result.agents_analyzed == 0
    assert result.stances == []


def test_stance_jev_off_matches_original_behaviour(monkeypatch, jev_off):
    llm = MagicMock()
    llm.chat_json.return_value = {
        "stances": [
            {"agent_index": 0, "position": "supportive", "intensity": 9, "key_concern": "k", "confidence": "high"},
            {"agent_index": 2, "position": "neutral", "intensity": 2},
            {"agent_index": 7, "position": "opposing", "intensity": 3},  # out of range: dropped
        ]
    }
    svc = _service(monkeypatch, llm)

    result = svc.stance_analysis("sim", "t", "g")

    assert result.agents_analyzed == 3
    assert [(s.agent_name, s.intensity) for s in result.stances] == [("NHS England", 5), ("The Guardian", 2)]
    prompt = _stance_prompt(llm)
    assert all(name in prompt for name in ("NHS England", "Jane Doe", "The Guardian"))


def test_stance_partial_result_when_llm_fallback_fails_after_jev(monkeypatch, jev_on):
    jev_on(
        [
            {"position": JevAnswer("choice", "supportive", 0.9), "intensity": JevAnswer("score", 2.0, 0.9)},
            None,
            None,
        ]
    )
    llm = MagicMock()
    llm.chat_json.side_effect = RuntimeError("boom")
    svc = _service(monkeypatch, llm)

    result = svc.stance_analysis("sim", "t", "g")

    assert result.agents_analyzed == 3
    assert [s.agent_name for s in result.stances] == ["NHS England"]


# ====================================================================== risk matrix


def _risk_llm():
    llm = MagicMock()
    llm.chat_json.return_value = {
        "risks": [
            {"risk": "Closures accelerate", "likelihood": 3, "impact": 3, "mitigation_indicators": ["m"]},
            {"risk": "Minor admin friction", "likelihood": 2, "impact": 2},
        ],
        "risk_summary": "s",
    }
    return llm


def test_risk_matrix_jev_rescoring_updates_numbers_severity_and_order(monkeypatch, jev_on):
    fake = jev_on(
        [
            {"likelihood": JevAnswer("score", 3.8, 0.9), "impact": JevAnswer("score", 4.0, 0.95)},
            {"likelihood": JevAnswer("score", 0.0, 0.2), "impact": JevAnswer("score", 0.0, 0.2)},  # unsure
        ]
    )
    svc = QuantitativeAnalysisService(llm_client=_risk_llm())

    matrix = svc.risk_matrix("Pharmacy First caps")

    by_name = {r.risk: r for r in matrix.risks}
    a, b = by_name["Closures accelerate"], by_name["Minor admin friction"]
    assert (a.likelihood, a.impact, a.severity) == (5, 5, "critical")
    assert (b.likelihood, b.impact, b.severity) == (2, 2, "low")
    assert matrix.risks[0].risk == "Closures accelerate"
    assert len(matrix.top_risks) == 2
    assert fake.items[0][0]["risk"] == "Closures accelerate"
    assert "Pharmacy First caps" in fake.items[0][0]["scenario_evidence"]
    assert len(fake.items[0][1]["likelihood"]["criteria"]) == 5


def test_risk_matrix_partial_rescoring_only_confident_dimension(monkeypatch, jev_on):
    jev_on(
        [
            {"likelihood": JevAnswer("score", 4.0, 0.9), "impact": JevAnswer("score", 0.0, 0.1)},
            None,
        ]
    )
    svc = QuantitativeAnalysisService(llm_client=_risk_llm())

    matrix = svc.risk_matrix("s")

    a = next(r for r in matrix.risks if r.risk == "Closures accelerate")
    assert (a.likelihood, a.impact, a.severity) == (5, 3, "high")


def test_risk_matrix_jev_off_unchanged(monkeypatch, jev_off):
    svc = QuantitativeAnalysisService(llm_client=_risk_llm())

    matrix = svc.risk_matrix("s")

    by_name = {r.risk: r for r in matrix.risks}
    assert by_name["Closures accelerate"].severity == "moderate"
    assert by_name["Minor admin friction"].severity == "low"
