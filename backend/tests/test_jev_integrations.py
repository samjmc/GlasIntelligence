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
from app.utils.jev_metrics import LEDGER


class FakeJev:
    """Returns scripted per-item answers and records what it was asked."""

    def __init__(self, answers):
        self.answers = answers
        self.items = None
        self.site = None

    def evaluate_many(self, items, max_workers=None, *, site="unlabelled"):
        self.items = items
        self.site = site
        assert len(items) == len(self.answers), "test script must cover every item"
        return self.answers


@pytest.fixture(autouse=True)
def _fresh_ledger():
    LEDGER.reset()
    yield
    LEDGER.reset()


@pytest.fixture
def jev_on(monkeypatch):
    """Active mode with a scripted Jev. The repo .env may set JEV_MODE, so pin it."""
    monkeypatch.setattr(app_config.Config, "JEV_MIN_CONFIDENCE", 0.6)
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "active")
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset())

    def _install(answers):
        fake = FakeJev(answers)
        monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake))
        return fake

    return _install


@pytest.fixture
def jev_shadow(monkeypatch, jev_on):
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "shadow")
    return jev_on


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

    with patch("app.utils.llm_client.OpenAI", mock_openai):
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

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "observer", 2: "analyst"}
    mock_openai.return_value.chat.completions.create.assert_not_called()


def test_tool_roles_jev_option_outside_set_falls_back(monkeypatch, jev_on):
    jev_on([{"role": JevAnswer("choice", "wizard", 0.99)}] + [{"role": JevAnswer("choice", "none", 0.9)}] * 2)
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"0": "leader"}')

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "none", 2: "none"}


def test_tool_roles_jev_off_sends_every_agent_to_llm(monkeypatch, jev_off):
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"0": "leader", "1": "observer", "2": "analyst"}')

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "observer", 2: "analyst"}
    prompt = _llm_prompt(mock_openai)
    assert all(name in prompt for name in ("NHS England", "Jane Doe", "The Guardian"))


def test_tool_roles_jev_off_no_llm_key_returns_empty(monkeypatch, jev_off):
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "")
    assert st.assign_tool_roles(_agents(), "req") == {}


def test_tool_roles_empty_input():
    assert st.assign_tool_roles([], "req") == {}


def test_tool_roles_shadow_uses_llm_but_records_agreement(monkeypatch, jev_shadow):
    fake = jev_shadow(
        [
            {"role": JevAnswer("choice", "leader", 0.95)},  # agrees with LLM
            {"role": JevAnswer("choice", "analyst", 0.95)},  # disagrees (LLM says observer)
            {"role": JevAnswer("choice", "analyst", 0.40)},  # unsure -> not compared
        ]
    )
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"0": "leader", "1": "observer", "2": "analyst"}')

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "leader", 1: "observer", 2: "analyst"}  # LLM answers win in shadow
    assert len(fake.items) == 3  # Jev still evaluated everything
    site = LEDGER.summary()["sites"]["tool_roles"]
    assert (site["shadow_compared"], site["shadow_agreed"]) == (2, 1)
    assert site["items_llm"] == 3 and site["items_jev_confident"] == 2 and site["llm_calls"] == 1
    assert site["llm_prompt_chars"] > 0


def test_tool_roles_disabled_site_forces_llm(monkeypatch, jev_on):
    fake = jev_on([{"role": JevAnswer("choice", "leader", 0.99)}] * 3)
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"tool_roles"}))
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"0": "observer", "1": "observer", "2": "observer"}')

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        result = st.assign_tool_roles(_agents(), "req")

    assert result == {0: "observer", 1: "observer", 2: "observer"}
    assert fake.items is None  # Jev never called


def test_tool_roles_active_ledger_counts(monkeypatch, jev_on):
    jev_on([{"role": JevAnswer("choice", "leader", 0.95)}, {"role": JevAnswer("choice", "x", 0.9)}, None])
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    mock_openai = _llm_returning('{"1": "observer", "2": "analyst"}')

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        st.assign_tool_roles(_agents(), "req")

    site = LEDGER.summary()["sites"]["tool_roles"]
    assert site["items_total"] == 3
    assert (site["items_jev_confident"], site["items_jev_low_confidence"], site["items_jev_failed"]) == (1, 1, 1)
    assert site["items_llm"] == 2
    assert site["llm_cost_avoided_usd_est"] is not None and site["llm_cost_avoided_usd_est"] > 0


def test_tool_roles_llm_disables_deepseek_thinking(monkeypatch, jev_off):
    # With thinking on, DeepSeek V4.1 spends the whole max_tokens budget on hidden
    # reasoning and returns empty content (measured 2026-09-24).
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    monkeypatch.setattr(app_config.Config, "LLM_BASE_URL", "https://api.deepseek.com")
    mock_openai = _llm_returning('{"0": "leader", "1": "observer", "2": "analyst"}')

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        assert st.assign_tool_roles(_agents(), "req") == {0: "leader", 1: "observer", 2: "analyst"}

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_scenario_tools_llm_disables_deepseek_thinking(monkeypatch):
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    monkeypatch.setattr(app_config.Config, "LLM_BASE_URL", "https://api.deepseek.com")
    mock_openai = _llm_returning(
        '[{"name": "file_complaint", "description": "d", "param_name": "p", "param_description": "pd", "effects": []}]'
    )

    with patch("app.utils.llm_client.OpenAI", mock_openai):
        tools = st.generate_scenario_tool_definitions("Pharmacy First caps", ["Organization"])

    assert [t.name for t in tools] == ["file_complaint"]
    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


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


def test_risk_matrix_one_unsure_dimension_keeps_llm_numbers_for_that_risk(monkeypatch, jev_on):
    """A risk is re-scored as a unit: if either dimension is unsure, both LLM numbers stay."""
    jev_on(
        [
            {"likelihood": JevAnswer("score", 4.0, 0.9), "impact": JevAnswer("score", 0.0, 0.1)},
            None,
        ]
    )
    svc = QuantitativeAnalysisService(llm_client=_risk_llm())

    matrix = svc.risk_matrix("s")

    a = next(r for r in matrix.risks if r.risk == "Closures accelerate")
    assert (a.likelihood, a.impact, a.severity) == (3, 3, "moderate")
    site = LEDGER.summary()["sites"]["risk_scores"]
    assert (site["items_jev_low_confidence"], site["items_jev_failed"], site["items_jev_confident"]) == (1, 1, 0)


def test_risk_matrix_shadow_records_agreement_without_changing_numbers(monkeypatch, jev_shadow):
    jev_shadow(
        [
            {"likelihood": JevAnswer("score", 2.0, 0.9), "impact": JevAnswer("score", 2.0, 0.9)},  # -> (3,3) agrees
            {"likelihood": JevAnswer("score", 4.0, 0.9), "impact": JevAnswer("score", 4.0, 0.9)},  # -> (5,5) disagrees
        ]
    )
    svc = QuantitativeAnalysisService(llm_client=_risk_llm())

    matrix = svc.risk_matrix("s")

    by_name = {r.risk: r for r in matrix.risks}
    assert (by_name["Closures accelerate"].likelihood, by_name["Minor admin friction"].likelihood) == (3, 2)
    site = LEDGER.summary()["sites"]["risk_scores"]
    assert (site["shadow_compared"], site["shadow_agreed"]) == (2, 1)


def test_risk_matrix_jev_off_unchanged(monkeypatch, jev_off):
    svc = QuantitativeAnalysisService(llm_client=_risk_llm())

    matrix = svc.risk_matrix("s")

    by_name = {r.risk: r for r in matrix.risks}
    assert by_name["Closures accelerate"].severity == "moderate"
    assert by_name["Minor admin friction"].severity == "low"
