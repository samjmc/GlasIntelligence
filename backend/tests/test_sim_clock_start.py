"""The simulated clock must start in active hours, and a run with no agent actions must fail loud.

Measured 2026-10-02 on sim_e0c917782178: time_config total_simulation_hours=10,
minutes_per_round=60, run with max_rounds=8. The clock started at 00:00, so rounds 1-8
were hours 00-07. No agent has any of those hours in active_hours, so every round was
skipped: "Published 10 initial posts", then "total actions: 10" - the opening posts and
nothing else - and the run still reported success.

These tests drive the real round loop (run_platform_simulation) with a fake OASIS env, so
no LLM is called. The agents below are that run's 50 agents (activity_level, active_hours).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
for _p in (_SCRIPTS, os.path.join(_SCRIPTS, "lib")):  # the paths run_parallel_simulation.py sets up
    if _p not in sys.path:
        sys.path.insert(0, _p)
import platform_runners as pr  # noqa: E402
import time_utils  # noqa: E402
from action_logger import SimulationLogManager  # noqa: E402

from app.services.simulation_runner import (  # noqa: E402
    ZERO_AGENT_ACTIONS_ERROR,
    RunnerStatus,
    SimulationRunner,
    SimulationRunState,
)


def _h(a: int, b: int) -> list[int]:
    return list(range(a, b + 1))


W = _h(9, 17)
MEASURED_AGENTS = [
    (0.4, W),
    (0.6, _h(9, 20)),
    (0.7, _h(18, 23)),
    (0.5, _h(8, 23)),
    (0.3, W),
    (0.5, _h(8, 20)),
    (0.6, _h(8, 23)),
    (0.5, W),
    (0.7, _h(8, 22)),
    (0.4, W),
    (0.2, W),
    (0.6, W),
    (0.2, W),
    (0.7, _h(9, 22)),
    (0.8, _h(18, 23)),
    (0.5, _h(8, 18)),
    (0.4, _h(9, 18)),
    (0.2, W),
    (0.6, _h(8, 18)),
    (0.2, W),
    (0.3, W),
    (0.6, _h(8, 23)),
    (0.5, _h(8, 23)),
    (0.4, _h(8, 20)),
    (0.5, _h(8, 23)),
    (0.6, _h(8, 18)),
    (0.2, W),
    (0.4, _h(8, 22)),
    (0.2, W),
    (0.2, W),
    (0.7, _h(18, 23)),
    (0.45, _h(8, 18)),
    (0.5, W),
    (0.5, W),
    (0.55, _h(8, 23)),
    (0.2, W),
    (0.55, _h(8, 23)),
    (0.5, _h(8, 23)),
    (0.15, W),
    (0.3, _h(9, 18)),
    (0.5, W),
    (0.4, W),
    (0.4, _h(8, 18)),
    (0.45, W),
    (0.4, _h(8, 18)),
    (0.22, W),
    (0.5, _h(8, 23)),
    (0.1, W),
    (0.78, [8, 9, 12, 13, *_h(18, 23)]),
    (0.56, [*W, 19, 20, 21]),
]


def measured_config(**time_overrides) -> dict:
    time_config = {
        "total_simulation_hours": 10,
        "minutes_per_round": 60,
        "agents_per_hour_min": 3,
        "agents_per_hour_max": 35,
        "peak_hours": [10, 11, 14, 15, 19, 20],
        "peak_activity_multiplier": 1.5,
        "off_peak_hours": [0, 1, 2, 3, 4, 5, 23],
        "off_peak_activity_multiplier": 0.05,
        "morning_hours": [6, 7, 8],
        "morning_activity_multiplier": 0.4,
        "work_hours": W,
        "work_activity_multiplier": 0.7,
    }
    time_config.update(time_overrides)
    return {
        "time_config": time_config,
        "agent_configs": [
            {"agent_id": i, "entity_name": f"Agent {i}", "activity_level": lvl, "active_hours": hours}
            for i, (lvl, hours) in enumerate(MEASURED_AGENTS)
        ],
        "event_config": {"initial_posts": [{"poster_agent_id": i, "content": f"opening {i}"} for i in range(10)]},
    }


class FakeAgent:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.system_message = None


class FakeGraph:
    def __init__(self, n):
        self._agents = {i: FakeAgent(i) for i in range(n)}

    def get_agent(self, agent_id):
        return self._agents[agent_id]

    def get_agents(self):
        return list(self._agents.items())

    def get_num_nodes(self):
        return len(self._agents)


class FakeEnv:
    """Records which agents each LLM round stepped; each one produces one comment."""

    def __init__(self, graph):
        self.agent_graph = graph
        self.llm_rounds: list[list[int]] = []
        self.pending: list[int] = []

    async def reset(self):
        pass

    async def step(self, actions):
        if all(isinstance(a, pr.LLMAction) for a in actions.values()):
            ids = [agent.agent_id for agent in actions]
            self.llm_rounds.append(ids)
            self.pending = ids

    async def close(self):
        pass


class ExitedCleanly:
    """A finished simulation subprocess with exit code 0."""

    returncode = 0

    def poll(self):
        return 0


def _run(tmp_path, monkeypatch, config, max_rounds=8):
    sim_dir = tmp_path / "sim"
    sim_dir.mkdir()
    (sim_dir / "reddit_profiles.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("OASIS_SEED", "7")

    graph = FakeGraph(len(config["agent_configs"]))
    env = FakeEnv(graph)

    async def build_graph(**_kwargs):
        return graph

    def fetch(_db_path, last_rowid, agent_names):
        actions = [
            {"agent_id": i, "agent_name": agent_names.get(i, ""), "action_type": "CREATE_COMMENT", "action_args": {}}
            for i in env.pending
        ]
        env.pending = []
        return actions, last_rowid + len(actions)

    spec = pr._PlatformSpec("Reddit", "reddit_profiles.json", build_graph, [], None, use_boost=False)
    monkeypatch.setitem(pr.PLATFORMS, "reddit", spec)
    monkeypatch.setattr(pr, "create_model", lambda *a, **k: None)
    monkeypatch.setattr(pr.oasis, "make", lambda **_k: env)
    monkeypatch.setattr(pr, "fetch_new_actions_from_db", fetch)
    monkeypatch.setattr(pr, "fetch_new_tool_calls", lambda *a, **k: [])

    log_manager = SimulationLogManager(str(sim_dir))
    try:
        asyncio.run(
            pr.run_platform_simulation(
                "reddit",
                config,
                str(sim_dir),
                action_logger=log_manager.get_reddit_logger(),
                main_logger=log_manager,
                max_rounds=max_rounds,
            )
        )
    finally:
        for handler in list(log_manager._main_logger.handlers):
            handler.close()
            log_manager._main_logger.removeHandler(handler)

    events = [
        json.loads(line) for line in (sim_dir / "reddit" / "actions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    sim_log = (sim_dir / "simulation.log").read_text(encoding="utf-8")
    return env, events, sim_log, sim_dir


def _round_hours(events):
    return [e["simulated_hour"] for e in events if e.get("event_type") == "round_start" and e["round"] > 0]


def _end(events):
    return next(e for e in events if e.get("event_type") == "simulation_end")


def test_short_run_starts_at_the_first_work_hour_and_agents_act(tmp_path, monkeypatch):
    env, events, sim_log, _ = _run(tmp_path, monkeypatch, measured_config())

    assert _round_hours(events) == list(range(9, 17))
    assert len(env.llm_rounds) == 8, "every round should have had active agents"
    end = _end(events)
    assert end["agent_actions"] == sum(len(r) for r in env.llm_rounds) > 0
    assert end["total_actions"] == 10 + end["agent_actions"]
    assert "WARNING" not in sim_log
    assert "Simulated clock starts at 09:00" in sim_log


def test_clock_at_midnight_reproduces_the_silent_zero_action_run(tmp_path, monkeypatch):
    # start_hour=0 is the old clock. Proves the test above can fail, and that it now fails loud.
    env, events, sim_log, sim_dir = _run(tmp_path, monkeypatch, measured_config(start_hour=0))

    assert _round_hours(events) == list(range(0, 8))
    assert env.llm_rounds == []
    end = _end(events)
    assert (end["total_actions"], end["agent_actions"]) == (10, 0)
    assert "WARNING - [Reddit] Zero agent actions in 8 rounds" in sim_log

    # The backend monitor reads that log and marks the run FAILED, and a clean process exit
    # (exit code 0) does not flip it back to COMPLETED.
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    state = SimulationRunState(simulation_id="sim", runner_status=RunnerStatus.RUNNING)
    monkeypatch.setitem(SimulationRunner._run_states, "sim", state)
    monkeypatch.setitem(SimulationRunner._processes, "sim", ExitedCleanly())
    SimulationRunner._monitor_simulation("sim")

    assert state.reddit_actions_count == 10  # the opening posts: the old guard counted these and passed
    assert state.runner_status == RunnerStatus.FAILED
    assert state.error == ZERO_AGENT_ACTIONS_ERROR
    saved = json.loads((sim_dir / "run_state.json").read_text(encoding="utf-8"))
    assert (saved["runner_status"], saved["agent_actions_count"]) == ("failed", 0)


def test_zero_action_run_names_the_llm_credit_failure(tmp_path, monkeypatch):
    # Live run sim_b8bb8b07981b (2026-10-10): every agent call got DeepSeek's 402
    # "Insufficient Balance", and the UI only said "check model/API key and the schedule".
    _, _, _, sim_dir = _run(tmp_path, monkeypatch, measured_config(start_hour=0))
    with open(sim_dir / "simulation.log", "a", encoding="utf-8") as f:
        for _ in range(3):
            f.write(
                "openai.APIStatusError: Error code: 402 - {'error': {'message': 'Insufficient Balance'}}\n"
            )
        f.write("openai.RateLimitError: Error code: 429 - {'error': {'message': 'slow down'}}\n")

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    state = SimulationRunState(simulation_id="sim", runner_status=RunnerStatus.RUNNING)
    monkeypatch.setitem(SimulationRunner._run_states, "sim", state)
    monkeypatch.setitem(SimulationRunner._processes, "sim", ExitedCleanly())
    SimulationRunner._monitor_simulation("sim")

    assert state.runner_status == RunnerStatus.FAILED  # a clean exit must not flip it to COMPLETED
    assert state.error.startswith(ZERO_AGENT_ACTIONS_ERROR)
    assert "out of credit (HTTP 402)" in state.error  # the most frequent code wins over the one 429


def test_a_run_with_agent_actions_still_completes(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, measured_config())

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    state = SimulationRunState(simulation_id="sim", runner_status=RunnerStatus.RUNNING)
    monkeypatch.setitem(SimulationRunner._run_states, "sim", state)
    monkeypatch.setitem(SimulationRunner._processes, "sim", ExitedCleanly())
    SimulationRunner._monitor_simulation("sim")

    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.error is None
    assert state.agent_actions_count > 0


@pytest.mark.parametrize(
    ("time_config", "expected"),
    [
        ({"work_hours": [10, 9, 11]}, 9),
        ({"work_hours": [], "peak_hours": [19, 20]}, 19),
        ({}, time_utils.DEFAULT_START_HOUR),
        ({"start_hour": 14, "work_hours": W}, 14),
        ({"start_hour": 24, "work_hours": W}, 9),  # out of range: ignored
        ({"start_hour": True, "work_hours": W}, 9),  # a bool is not an hour
        ({"time_scale": {"unit": "hour", "start_date": "2026-10-01T07:30"}, "work_hours": W}, 7),
        ({"time_scale": {"unit": "hour", "start_date": "2026-10-01"}, "work_hours": W}, 9),
        ({"time_scale": {"unit": "day"}, "work_hours": W}, 0),  # phase-based: unchanged
    ],
)
def test_resolve_start_hour(time_config, expected):
    assert time_utils.resolve_start_hour(time_config) == expected


def test_time_label_clock_matches_the_start_hour():
    ts = {"unit": "hour", "per_round": 1, "start_date": "2026-10-01"}
    assert time_utils.compute_time_label(0, ts, start_hour=9)["anchor"] == "Oct 01 2026, 09:00"
    assert time_utils.compute_time_label(16, ts, start_hour=9)["anchor"] == "Oct 02 2026, 01:00"
    assert (
        time_utils.compute_time_label(2, {"unit": "day", "per_round": 1, "start_date": "2026-10-01"}, 9)["anchor"]
        == "Oct 03, 2026"
    )
