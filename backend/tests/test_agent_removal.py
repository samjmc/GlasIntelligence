"""Removing agents on the Environment Setup page, before the run starts (app/services/agent_removal.py).

The fixture writes a prepared simulation with the same code prepare uses (OasisProfileGenerator's
save_profiles, SimulationParameters.to_json), so the files have the real shapes.
"""

import csv
import json
import os
import sys
from types import SimpleNamespace

import pytest

from app.middleware import auth
from app.models.project import ProjectManager
from app.services.oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator
from app.services.simulation_config_generator import (
    AgentActivityConfig,
    EventConfig,
    SimulationParameters,
    TimeSimulationConfig,
)
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner

OWNER, OTHER = "user-a", "user-b"
SIM = "sim_rm"
_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")

# name, entity type; agent i is list item i
AGENTS = [
    ("Vodafone Ireland", "Company"),
    ("O2", "Company"),  # gone from Ireland since 2015
    ("ComReg", "GovernmentBody"),
    ("Worldov", "Organization"),
    ("The Irish Times", "MediaOutlet"),
    ("boards.ie thread", "Organization"),
]
POSTS = [  # (poster_agent_id, poster_type)
    (1, "Company"),
    (3, "Organization"),
    (2, "GovernmentBody"),
    (4, "MediaOutlet"),
]


def _write_prepared(sim_dir, project_id, status="ready", twitter=True):
    sim_dir.mkdir(parents=True)
    profiles = [
        OasisAgentProfile(
            user_id=i,
            user_name=f"{name.lower().replace(' ', '_')}_{100 + i}",
            name=name,
            bio=f"{etype}: {name}",
            persona=f"{name} persona",
            source_entity_type=etype,
        )
        for i, (name, etype) in enumerate(AGENTS)
    ]
    gen = object.__new__(OasisProfileGenerator)  # no LLM client: only the file writers are used
    gen.save_profiles(profiles, str(sim_dir / "reddit_profiles.json"), platform="reddit")
    if twitter:
        gen.save_profiles(profiles, str(sim_dir / "twitter_profiles.csv"), platform="twitter")
    params = SimulationParameters(
        simulation_id=SIM,
        project_id=project_id,
        graph_id="g",
        simulation_requirement="Irish mobile market",
        time_config=TimeSimulationConfig(agents_per_hour_min=4, agents_per_hour_max=5),
        agent_configs=[
            AgentActivityConfig(
                agent_id=i, entity_uuid=f"uuid-{i}", entity_name=name, entity_type=etype, influence_weight=1.0 + i
            )
            for i, (name, etype) in enumerate(AGENTS)
        ],
        event_config=EventConfig(
            initial_posts=[{"content": f"post by {a}", "poster_type": t, "poster_agent_id": a} for a, t in POSTS],
            hot_topics=["roaming"],
        ),
    )
    (sim_dir / "simulation_config.json").write_text(params.to_json(), encoding="utf-8")
    (sim_dir / "state.json").write_text(
        json.dumps(
            {
                "simulation_id": SIM,
                "project_id": project_id,
                "graph_id": "g",
                "enable_twitter": twitter,
                "enable_reddit": True,
                "status": status,
                "entities_count": len(AGENTS),
                "profiles_count": len(AGENTS),
                "entity_types": sorted({t for _, t in AGENTS}),
                "config_generated": True,
            }
        ),
        encoding="utf-8",
    )


def _read(sim_dir, name):
    return json.loads((sim_dir / name).read_text(encoding="utf-8"))


def _snapshot(sim_dir):
    return {p.name: p.read_bytes() for p in sim_dir.iterdir()}


def _as(user):
    return {"Authorization": f"Bearer {user}"}


@pytest.fixture
def prepared(api, tmp_path, monkeypatch):
    from app.api import simulation as simulation_api  # after ``api`` (see conftest.py)

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations"))
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path / "simulations"))
    monkeypatch.setattr(simulation_api.Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path / "simulations"))
    monkeypatch.setattr(auth.Config, "SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setattr(auth.Config, "SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr(auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    project = ProjectManager.create_project("owned", user_id=OWNER)
    sim_dir = tmp_path / "simulations" / SIM
    _write_prepared(sim_dir, project.project_id)
    return SimpleNamespace(dir=sim_dir, project_id=project.project_id)


def _remove(api, body, user=OWNER):
    return api.post(f"/api/simulation/{SIM}/agents/remove", json=body, headers=_as(user))


def test_removal_updates_every_artefact_consistently(api, prepared):
    res = _remove(api, {"agent_ids": [1, 3, 5]})

    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["removed"] == ["O2", "Worldov", "boards.ie thread"]
    assert data["count"] == 3
    kept = ["Vodafone Ireland", "ComReg", "The Irish Times"]

    profiles = _read(prepared.dir, "reddit_profiles.json")
    assert [p["name"] for p in profiles] == kept
    assert [p["user_id"] for p in profiles] == [0, 1, 2]
    assert data["profiles"] == profiles

    config = _read(prepared.dir, "simulation_config.json")
    assert [(a["agent_id"], a["entity_name"]) for a in config["agent_configs"]] == list(enumerate(kept))
    assert [a["entity_uuid"] for a in config["agent_configs"]] == ["uuid-0", "uuid-2", "uuid-4"]
    assert config["time_config"]["agents_per_hour_max"] == 3
    assert config["time_config"]["agents_per_hour_min"] == 3
    assert data["config"] == config

    with open(prepared.dir / "twitter_profiles.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(r["user_id"], r["name"]) for r in rows] == [("0", kept[0]), ("1", kept[1]), ("2", kept[2])]

    state = _read(prepared.dir, "state.json")
    assert (state["entities_count"], state["profiles_count"]) == (3, 3)
    assert state["entity_types"] == ["Company", "GovernmentBody", "MediaOutlet"]
    assert state["status"] == "ready"
    assert not [p for p in prepared.dir.iterdir() if p.name.endswith(".removing")]


def test_opening_posts_of_removed_agents_are_reassigned_or_dropped(api, prepared):
    assert _remove(api, {"agent_ids": [1, 3, 5]}).status_code == 200

    posts = _read(prepared.dir, "simulation_config.json")["event_config"]["initial_posts"]
    assert [(p["content"], p["poster_agent_id"]) for p in posts] == [
        ("post by 1", 0),  # O2's Company post goes to the remaining Company, Vodafone (now 0)
        # "post by 3": Worldov's Organization post is dropped, no Organization is left
        ("post by 2", 1),  # ComReg renumbered 2 -> 1
        ("post by 4", 2),  # Irish Times renumbered 4 -> 2
    ]


def test_ids_stay_valid_for_the_runner(api, prepared):
    """What the runner does at start: agent i = profile i, names from agent_configs, posters looked up."""
    assert _remove(api, {"names": ["o2"]}).status_code == 200
    for p in (_SCRIPTS, os.path.join(_SCRIPTS, "lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import platform_runners
    from config_utils import get_agent_names_from_config

    profiles = _read(prepared.dir, "reddit_profiles.json")
    config = _read(prepared.dir, "simulation_config.json")

    class Graph:  # agent_graphs.py builds agent_id=i for each profile list item i
        def get_agent(self, agent_id):
            if not 0 <= agent_id < len(profiles):
                raise KeyError(agent_id)
            return profiles[agent_id]["name"]

    names = get_agent_names_from_config(config)
    assert names == {i: p["name"] for i, p in enumerate(profiles)}
    assert "O2" not in names.values()
    _, accepted = platform_runners._opening_actions(Graph(), config["event_config"]["initial_posts"])
    assert len(accepted) == len(POSTS)  # no opening post points at a missing agent
    assert [names[a] for a, _ in accepted] == ["Vodafone Ireland", "Worldov", "ComReg", "The Irish Times"]


def test_profiles_endpoint_no_longer_returns_removed_agents(api, prepared):
    assert _remove(api, {"names": ["O2", "Worldov"]}).status_code == 200
    res = api.get(f"/api/simulation/{SIM}/profiles", headers=_as(OWNER))
    names = [p["name"] for p in res.get_json()["data"]["profiles"]]
    assert names == ["Vodafone Ireland", "ComReg", "The Irish Times", "boards.ie thread"]
    realtime = api.get(f"/api/simulation/{SIM}/profiles/realtime", headers=_as(OWNER)).get_json()["data"]
    assert (realtime["count"], realtime["total_expected"]) == (4, 4)


@pytest.mark.parametrize("status", ["running", "completed", "stopped", "preparing", "failed"])
def test_not_ready_is_409(api, prepared, status):
    state = _read(prepared.dir, "state.json")
    (prepared.dir / "state.json").write_text(json.dumps({**state, "status": status}), encoding="utf-8")
    before = _snapshot(prepared.dir)
    res = _remove(api, {"agent_ids": [1]})
    assert res.status_code == 409
    assert status in res.get_json()["error"]
    assert _snapshot(prepared.dir) == before


def test_started_run_is_409_even_if_state_still_says_ready(api, prepared):
    (prepared.dir / "run_state.json").write_text(json.dumps({"runner_status": "starting"}), encoding="utf-8")
    before = _snapshot(prepared.dir)
    res = _remove(api, {"agent_ids": [1]})
    assert res.status_code == 409
    assert "already been started" in res.get_json()["error"]
    assert _snapshot(prepared.dir) == before


def test_other_user_gets_404(api, prepared):
    before = _snapshot(prepared.dir)
    res = _remove(api, {"agent_ids": [1]}, user=OTHER)
    assert res.status_code == 404
    assert res.get_json()["error"] == f"Simulation not found: {SIM}"
    assert _snapshot(prepared.dir) == before


def test_no_token_is_401(api, prepared):
    assert api.post(f"/api/simulation/{SIM}/agents/remove", json={"agent_ids": [1]}).status_code == 401


def test_below_minimum_is_400(api, prepared):
    before = _snapshot(prepared.dir)
    res = _remove(api, {"agent_ids": [0, 1, 2, 3, 4]})
    assert res.status_code == 400
    assert "at least 2 agents" in res.get_json()["error"]
    assert _snapshot(prepared.dir) == before


@pytest.mark.parametrize(
    "body,message",
    [
        ({"names": ["Eir"]}, "Unknown agent name: Eir"),
        ({"agent_ids": [6]}, "Unknown agent id: 6"),
        ({"agent_ids": [1, 99]}, "Unknown agent id: 99"),  # one bad id: nothing is removed
        ({"agent_ids": ["1"]}, "Unknown agent id: 1"),
        ({"agent_ids": [True]}, "Unknown agent id: True"),
        ({}, "Name at least one agent"),
        ({"agent_ids": 1}, "must be lists"),
    ],
)
def test_unknown_or_bad_input_is_400_and_changes_nothing(api, prepared, body, message):
    before = _snapshot(prepared.dir)
    res = _remove(api, body)
    assert res.status_code == 400
    assert message in res.get_json()["error"]
    assert _snapshot(prepared.dir) == before


def test_ambiguous_name_is_400(api, prepared):
    profiles = _read(prepared.dir, "reddit_profiles.json")
    profiles[5]["name"] = "Worldov"
    (prepared.dir / "reddit_profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
    res = _remove(api, {"names": ["Worldov"]})
    assert res.status_code == 400
    assert "2 agents are called" in res.get_json()["error"]


def test_files_out_of_step_are_refused(api, prepared):
    profiles = _read(prepared.dir, "reddit_profiles.json")
    (prepared.dir / "reddit_profiles.json").write_text(json.dumps(profiles[:-1]), encoding="utf-8")
    assert _remove(api, {"agent_ids": [1]}).status_code == 409


def test_reddit_only_run_has_no_twitter_file(api, prepared):
    (prepared.dir / "twitter_profiles.csv").unlink()
    assert _remove(api, {"agent_ids": [1]}).status_code == 200
    assert not (prepared.dir / "twitter_profiles.csv").exists()
    assert len(_read(prepared.dir, "reddit_profiles.json")) == 5


def test_each_removal_is_logged(api, prepared, monkeypatch):
    from app.services import agent_removal

    lines: list[str] = []
    monkeypatch.setattr(agent_removal, "logger", SimpleNamespace(info=lines.append))
    assert _remove(api, {"agent_ids": [1, 3]}).status_code == 200
    removed = [m for m in lines if "Removed agent before start" in m]
    assert len(removed) == 2
    assert "'O2'" in removed[0] and "'Worldov'" in removed[1]
