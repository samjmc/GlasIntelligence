"""Stance and stakeholder tables must find each agent's entity type on a reddit-only run.

Live report_e8120cae4a96 (2026-10-10, 90 agents): the stakeholder matrix had one row,
"Unknown | n/a | unknown | 0.0". Two causes:
- reddit_profiles.json stores the display name as ``name``; the map keyed agents by
  ``username`` ("dunnes_169"), which never matches the action log's agent_name ("Dunnes");
- the stance call's max_tokens=4096 cut the 90-agent JSON mid-list, so it failed to parse.
"""

from __future__ import annotations

import json

import pytest

from app.services import quantitative_analysis_service as qas
from app.services.quantitative_analysis_service import QuantitativeAnalysisService

AGENTS = [("Dunnes", "dunnes_169", "Company"), ("Micheál Martin", "micheal_martin_42", "Politician")]


@pytest.fixture
def sim(tmp_path, monkeypatch):
    sim_dir = tmp_path / "sim_x"
    sim_dir.mkdir()
    profiles = [
        {"name": n, "username": u, "profession": "free text, not a type", "country": "Ireland"} for n, u, _ in AGENTS
    ]
    (sim_dir / "reddit_profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
    configs = [{"agent_id": i, "entity_name": n, "entity_type": t} for i, (n, _, t) in enumerate(AGENTS)]
    (sim_dir / "simulation_config.json").write_text(json.dumps({"agent_configs": configs}), encoding="utf-8")
    monkeypatch.setattr(QuantitativeAnalysisService, "_sim_dir", staticmethod(lambda sid: str(tmp_path / sid)))
    return "sim_x"


def test_type_map_uses_display_names_and_config_entity_types(sim):
    svc = QuantitativeAnalysisService()
    type_map = svc._build_agent_type_map(svc._load_agent_profiles(sim), sim)

    assert type_map["Dunnes"] == "Company"
    assert type_map["Micheál Martin"] == "Politician"
    assert "dunnes_169" not in type_map


class _FakeLLM:
    def __init__(self):
        self.max_tokens = None

    def chat_json(self, messages, temperature, max_tokens):
        self.max_tokens = max_tokens
        return {
            "stances": [
                {"agent_index": 0, "position": "opposing", "intensity": 4, "confidence": "high"},
                {"agent_index": 1, "position": "supportive", "intensity": 3, "confidence": "high"},
            ]
        }


def test_stance_analysis_groups_by_entity_type(sim, monkeypatch):
    monkeypatch.setattr(qas.JevClient, "from_config", classmethod(lambda cls: None))  # LLM path only
    llm = _FakeLLM()
    result = QuantitativeAnalysisService(llm_client=llm).stance_analysis(sim, "vape price floor", graph_id="")

    assert [(s.agent_name, s.agent_type) for s in result.stances] == [
        ("Dunnes", "Company"),
        ("Micheál Martin", "Politician"),
    ]
    assert set(result.by_entity_type) == {"Company", "Politician"}
    assert llm.max_tokens >= 16000  # room for ~90 agents at ~45 tokens each
