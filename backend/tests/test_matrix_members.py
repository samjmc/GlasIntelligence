"""The stakeholder matrix names the agents in each type, and each agent is in exactly one type.

Seen live on 2026-11-10: the matrix gave only numbers per type, so the report writer guessed the
groups and listed An Post Mobile under both MVNOBrand and PostalOperator.
"""

from unittest.mock import MagicMock

from app.services import quantitative_analysis_service as qas
from app.services import simulation_runner


def _matrix(monkeypatch, agent_stats, type_map, stances):
    svc = qas.QuantitativeAnalysisService(llm_client=MagicMock())
    monkeypatch.setattr(simulation_runner.SimulationRunner, "get_agent_stats", staticmethod(lambda sid: agent_stats))
    monkeypatch.setattr(svc, "_load_agent_profiles", lambda sid: [])
    monkeypatch.setattr(svc, "_build_agent_type_map", lambda profiles, sid: type_map)
    by_type: dict = {}
    for s in stances:  # as stance_analysis builds it: one stance mix per stance agent_type
        by_type.setdefault(s.agent_type, {})[s.position] = 100.0
    stance = qas.StanceAnalysis(stances=stances, by_entity_type=by_type)
    return svc.stakeholder_impact_matrix("s", "g", "topic", cached_stance=stance)


def test_each_agent_is_listed_once_under_its_profile_type(monkeypatch):
    stats = [
        {"agent_name": "48", "total_actions": 10, "action_types": {}},
        {"agent_name": "An Post Mobile", "total_actions": 6, "action_types": {}},
        {"agent_name": "ComReg", "total_actions": 3, "action_types": {}},
    ]
    type_map = {"48": "MVNOBrand", "An Post Mobile": "PostalOperator", "ComReg": "RegulatoryAgency"}
    stances = [
        qas.AgentStance(agent_name="An Post Mobile", agent_type="MVNOBrand", position="opposing"),
        qas.AgentStance(agent_name="Revolut", agent_type="FintechChallenger", position="supportive"),
    ]

    matrix = _matrix(monkeypatch, stats, type_map, stances)
    rows = {r.entity_type: r.members for r in matrix.rows}

    assert rows["MVNOBrand"] == ["48"]
    assert rows["PostalOperator"] == ["An Post Mobile"]
    assert rows["FintechChallenger"] == ["Revolut"]  # stance-only agent fills the gap
    listed = [name for members in rows.values() for name in members]
    assert sorted(listed) == sorted(set(listed)) and len(listed) == 4


def test_members_reach_the_writer_text_and_payload():
    row = qas.StakeholderImpactRow(entity_type="MVNOBrand", members=["48", "GoMo"])
    matrix = qas.StakeholderImpactMatrix(rows=[row])

    assert "| MVNOBrand | 48, GoMo |" in matrix.to_text()
    assert "exactly ONE type" in matrix.to_text()
    assert matrix.to_dict()["rows"][0]["members"] == ["48", "GoMo"]


def test_relevance_prompt_keeps_local_firms_cited_as_precedents():
    from app.services.simulation_manager import AGENT_RELEVANCE_PROMPT

    assert "operates in the scenario's country or market is ALWAYS kept" in AGENT_RELEVANCE_PROMPT
