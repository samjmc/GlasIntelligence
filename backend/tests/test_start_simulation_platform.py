"""Twitter was dropped: every run is reddit only.

start_simulation starts run_parallel_simulation.py with no platform flag, the runner knows
only reddit, and a new simulation is created with twitter off (so prepare writes no
twitter_profiles.csv and the config has no twitter_config).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from app.services import simulation_runner as sr
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


class _FakeProc:
    pid = 4242

    def poll(self):
        return 0


class _NoThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


@pytest.fixture
def launches(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sim_dir = tmp_path / "sim_x"
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({"time_config": {"total_simulation_hours": 2, "minutes_per_round": 60}}), encoding="utf-8"
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(sr.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd) or _FakeProc())
    monkeypatch.setattr(sr.threading, "Thread", _NoThread)
    yield calls
    f = SimulationRunner._stdout_files.pop("sim_x", None)
    if f:
        f.close()
    for registry in (SimulationRunner._processes, SimulationRunner._run_states, SimulationRunner._action_queues):
        registry.pop("sim_x", None)


def test_start_runs_reddit_only(launches):
    state = SimulationRunner.start_simulation("sim_x", max_rounds=1)

    assert len(launches) == 1
    cmd = launches[0]
    assert os.path.basename(cmd[1]) == "run_parallel_simulation.py"
    assert os.path.exists(cmd[1])
    assert cmd[2:4] == ["--config", os.path.join(SimulationRunner.RUN_STATE_DIR, "sim_x", "simulation_config.json")]
    assert not [a for a in cmd if "twitter" in a or a.endswith("-only")]
    assert (state.twitter_running, state.reddit_running) == (False, True)


def test_runner_knows_only_reddit():
    for p in (_SCRIPTS, os.path.join(_SCRIPTS, "lib")):  # the paths run_parallel_simulation.py sets up
        if p not in sys.path:
            sys.path.insert(0, p)
    import platform_runners

    assert set(platform_runners.PLATFORMS) == {"reddit"}
    assert not hasattr(platform_runners, "TWITTER_ACTIONS")


def test_new_simulation_has_twitter_off(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    state = SimulationManager().create_simulation(project_id="proj_x", graph_id="g_x")
    assert (state.enable_twitter, state.enable_reddit) == (False, True)
