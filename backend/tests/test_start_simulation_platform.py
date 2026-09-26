"""Every platform choice starts run_parallel_simulation.py; one platform is a flag.

The per-platform scripts (run_twitter_simulation.py / run_reddit_simulation.py) were an
older copy of the round loop that wrote no actions.jsonl, so a single-platform run showed
nothing downstream. They are gone; this pins the replacement argv.
"""

from __future__ import annotations

import json
import os

import pytest

from app.services import simulation_runner as sr
from app.services.simulation_runner import SimulationRunner


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


@pytest.mark.parametrize(
    ("platform", "flags", "twitter", "reddit"),
    [
        ("twitter", ["--twitter-only"], True, False),
        ("reddit", ["--reddit-only"], False, True),
        ("parallel", [], True, True),
    ],
)
def test_platform_choice_runs_the_parallel_script(launches, platform, flags, twitter, reddit):
    state = SimulationRunner.start_simulation("sim_x", platform=platform, max_rounds=1)

    assert len(launches) == 1
    cmd = launches[0]
    assert os.path.basename(cmd[1]) == "run_parallel_simulation.py"
    assert os.path.exists(cmd[1])
    assert cmd[2] == "--config" and cmd[3].endswith("simulation_config.json")
    assert [a for a in cmd if a.endswith("-only")] == flags
    assert (state.twitter_running, state.reddit_running) == (twitter, reddit)
