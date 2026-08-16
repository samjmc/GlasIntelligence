"""Tests for the simulation runner health gate and LLM-error surfacing.

Covers the failure class documented in the technical assessment (Story D2-3):
a run whose every agent LLM call failed used to exit cleanly and surface as
"successful" with zero actions. The health gate must flip such runs to FAILED.
"""

import json
import os

import pytest

from app.services.simulation_runner import (
    MIN_SIMULATION_ACTIONS,
    ZERO_ACTION_ERROR,
    RunnerStatus,
    SimulationRunState,
    SimulationRunner,
)


class _FakeProcess:
    """Minimal subprocess stand-in: exits immediately with a fixed return code."""

    def __init__(self, returncode: int):
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode


@pytest.fixture
def runner_env(tmp_path, monkeypatch):
    """Point RUN_STATE_DIR at a temp dir and isolate class-level runner state."""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state_dicts = [
        "_run_states",
        "_processes",
        "_monitor_threads",
        "_stdout_files",
        "_stderr_files",
        "_graph_memory_enabled",
    ]
    snapshots = {name: dict(getattr(SimulationRunner, name)) for name in state_dicts}
    yield str(tmp_path)
    for name in state_dicts:
        getattr(SimulationRunner, name).clear()
        getattr(SimulationRunner, name).update(snapshots[name])


def _make_state(sim_id: str, runner_status: RunnerStatus = RunnerStatus.RUNNING) -> SimulationRunState:
    return SimulationRunState(
        simulation_id=sim_id,
        runner_status=runner_status,
        total_rounds=25,
        started_at="2026-08-14T10:00:00",
    )


def _write_log(sim_dir: str, lines: list[str]):
    os.makedirs(sim_dir, exist_ok=True)
    with open(os.path.join(sim_dir, "simulation.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class TestHealthGate:
    def test_zero_action_run_marks_failed(self, runner_env):
        sim_id = "sim_gate_zero"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id)
        _write_log(sim_dir, ["INFO round 1", "ERROR 401 Incorrect API key provided: sk-ant-***", "INFO round 2"])

        assert SimulationRunner._apply_health_gate(state) is False

        assert state.runner_status == RunnerStatus.FAILED
        assert ZERO_ACTION_ERROR in state.error
        assert "LLM error line(s)" in state.error
        assert state.llm_error_count == 1

    def test_few_actions_run_marks_failed(self, runner_env):
        sim_id = "sim_gate_few"
        state = _make_state(sim_id)
        state.twitter_actions_count = 2
        state.reddit_actions_count = 1

        assert SimulationRunner._apply_health_gate(state) is False

        assert state.runner_status == RunnerStatus.FAILED
        assert "too few agent actions" in state.error
        assert f"({3} < {MIN_SIMULATION_ACTIONS})" in state.error

    def test_legitimate_run_passes_gate(self, runner_env):
        sim_id = "sim_gate_ok"
        state = _make_state(sim_id, runner_status=RunnerStatus.COMPLETED)
        state.twitter_actions_count = 12
        state.reddit_actions_count = 7

        assert SimulationRunner._apply_health_gate(state) is True

        assert state.runner_status == RunnerStatus.COMPLETED
        assert state.error is None

    def test_single_platform_with_actions_passes_gate(self, runner_env):
        sim_id = "sim_gate_single"
        state = _make_state(sim_id, runner_status=RunnerStatus.COMPLETED)
        state.twitter_actions_count = 6

        assert SimulationRunner._apply_health_gate(state) is True
        assert state.runner_status == RunnerStatus.COMPLETED
        assert state.error is None

    def test_gate_records_llm_error_count_even_when_passing(self, runner_env):
        sim_id = "sim_gate_pass_errs"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id, runner_status=RunnerStatus.COMPLETED)
        state.twitter_actions_count = 10
        _write_log(sim_dir, ["ERROR 401", "ERROR rate limit exceeded", "INFO normal"])

        assert SimulationRunner._apply_health_gate(state) is True
        assert state.runner_status == RunnerStatus.COMPLETED
        assert state.llm_error_count == 2

    def test_llm_error_count_saved_to_run_state(self, runner_env):
        sim_id = "sim_gate_persist"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id)
        _write_log(sim_dir, ["ERROR 403 Forbidden"] * 3)

        SimulationRunner._apply_health_gate(state)
        SimulationRunner._save_run_state(state)

        with open(os.path.join(sim_dir, "run_state.json"), encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["llm_error_count"] == 3
        assert saved["runner_status"] == RunnerStatus.FAILED.value
        assert ZERO_ACTION_ERROR in saved["error"]


class TestLLMErrorDetection:
    def test_counts_known_patterns(self, runner_env):
        sim_dir = os.path.join(runner_env, "sim_errs")
        _write_log(
            sim_dir,
            [
                "ERROR 401 Incorrect API key provided: sk-ant-***",
                "ERROR 403 Forbidden",
                "ERROR insufficient_quota: you exceeded your current quota",
                "ERROR RateLimitError: rate limit reached",
                "ERROR authentication failed: invalid credentials",
                "ERROR 429 Too Many Requests",
            ],
        )

        assert SimulationRunner._count_llm_errors(sim_dir) == 6

    def test_ignores_clean_lines(self, runner_env):
        sim_dir = os.path.join(runner_env, "sim_clean")
        _write_log(
            sim_dir,
            [
                "INFO simulation started",
                "INFO Round 3 completed, 12 actions",
                "INFO profile generated for agent 5",
                "INFO created 201 rows",
                "ERROR some other failure mode",
            ],
        )

        assert SimulationRunner._count_llm_errors(sim_dir) == 0

    def test_missing_log_returns_zero(self, runner_env):
        sim_dir = os.path.join(runner_env, "sim_no_log")
        assert SimulationRunner._count_llm_errors(sim_dir) == 0


class TestMonitorIntegration:
    def test_zero_action_exit_0_marks_failed(self, runner_env):
        sim_id = "sim_mon_zero"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id)
        SimulationRunner._save_run_state(state)
        _write_log(sim_dir, ["ERROR 401 Incorrect API key provided"] * 2)
        SimulationRunner._processes[sim_id] = _FakeProcess(returncode=0)

        SimulationRunner._monitor_simulation(sim_id)

        final = SimulationRunner._run_states[sim_id]
        assert final.runner_status == RunnerStatus.FAILED
        assert ZERO_ACTION_ERROR in final.error
        assert final.llm_error_count == 2
        with open(os.path.join(sim_dir, "run_state.json"), encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["runner_status"] == "failed"
        assert saved["llm_error_count"] == 2

    def test_exit_0_with_actions_stays_completed(self, runner_env):
        sim_id = "sim_mon_ok"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id)
        SimulationRunner._save_run_state(state)
        _write_log(sim_dir, ["INFO normal run"])
        os.makedirs(os.path.join(sim_dir, "twitter"), exist_ok=True)
        with open(os.path.join(sim_dir, "twitter", "actions.jsonl"), "w", encoding="utf-8") as f:
            for i in range(6):
                f.write(
                    json.dumps(
                        {
                            "round": i + 1,
                            "timestamp": "2026-08-14T10:00:00",
                            "agent_id": 1,
                            "agent_name": "Agent A",
                            "action_type": "CREATE_POST",
                            "action_args": {},
                            "result": "ok",
                            "success": True,
                        }
                    )
                    + "\n"
                )
        SimulationRunner._processes[sim_id] = _FakeProcess(returncode=0)

        SimulationRunner._monitor_simulation(sim_id)

        final = SimulationRunner._run_states[sim_id]
        assert final.runner_status == RunnerStatus.COMPLETED
        assert final.error is None
        assert final.twitter_actions_count == 6

    def test_failed_exit_surfaces_llm_error_count(self, runner_env):
        sim_id = "sim_mon_crash"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id)
        SimulationRunner._save_run_state(state)
        _write_log(sim_dir, ["ERROR 401", "ERROR rate limit exceeded"])
        SimulationRunner._processes[sim_id] = _FakeProcess(returncode=1)

        SimulationRunner._monitor_simulation(sim_id)

        final = SimulationRunner._run_states[sim_id]
        assert final.runner_status == RunnerStatus.FAILED
        assert final.error.startswith("Process exit code: 1")
        assert "2 LLM error line(s) in simulation.log" in final.error
        assert final.llm_error_count == 2

    def test_simulation_end_event_triggers_gate(self, runner_env):
        sim_id = "sim_mon_end_event"
        sim_dir = os.path.join(runner_env, sim_id)
        state = _make_state(sim_id)
        state.twitter_running = True
        SimulationRunner._save_run_state(state)
        _write_log(sim_dir, ["ERROR 401 Incorrect API key provided"])
        os.makedirs(os.path.join(sim_dir, "twitter"), exist_ok=True)
        with open(os.path.join(sim_dir, "twitter", "actions.jsonl"), "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"event_type": "simulation_end", "platform": "twitter", "total_rounds": 25, "total_actions": 0}
                )
                + "\n"
            )
        SimulationRunner._processes[sim_id] = _FakeProcess(returncode=0)

        SimulationRunner._monitor_simulation(sim_id)

        final = SimulationRunner._run_states[sim_id]
        assert final.runner_status == RunnerStatus.FAILED
        assert ZERO_ACTION_ERROR in final.error
        assert final.llm_error_count == 1

    def test_state_round_trip_preserves_llm_error_count(self, runner_env):
        sim_id = "sim_gate_roundtrip"
        state = _make_state(sim_id)
        state.llm_error_count = 4
        state.runner_status = RunnerStatus.FAILED
        state.error = "Simulation produced no agent actions"
        SimulationRunner._save_run_state(state)

        loaded = SimulationRunner._load_run_state(sim_id)
        assert loaded is not None
        assert loaded.llm_error_count == 4
        assert loaded.runner_status == RunnerStatus.FAILED
