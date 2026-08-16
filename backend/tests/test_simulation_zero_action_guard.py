"""Tests for the zero-action completion guard in SimulationRunner."""

import json

import pytest

from app.services.simulation_runner import (
    ZERO_ACTIONS_ERROR,
    RunnerStatus,
    SimulationRunner,
    SimulationRunState,
)

EXPECTED_ZERO_ACTIONS_ERROR = (
    "Simulation completed with zero actions across all platforms — "
    "check model/API key configuration."
)


def _enable_platform(sim_dir, platform):
    """Create the actions.jsonl file that marks a platform as enabled."""
    platform_dir = sim_dir / platform
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / "actions.jsonl").write_text("", encoding="utf-8")


@pytest.fixture
def sim_dir(tmp_path):
    return tmp_path / "sim-1"


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    return SimulationRunner


@pytest.fixture
def make_state():
    def _make_state(**kwargs):
        defaults = {
            "simulation_id": "sim-1",
            "twitter_completed": False,
            "reddit_completed": False,
            "twitter_actions_count": 0,
            "reddit_actions_count": 0,
        }
        defaults.update(kwargs)
        return SimulationRunState(**defaults)

    return _make_state


class TestCompletedWithZeroActions:
    def test_both_completed_zero_actions(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        _enable_platform(sim_dir, "reddit")
        state = make_state(twitter_completed=True, reddit_completed=True)
        assert runner._completed_with_zero_actions(state)

    def test_one_completed_with_actions_other_disabled(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        state = make_state(twitter_completed=True, twitter_actions_count=5)
        assert not runner._completed_with_zero_actions(state)

    def test_both_completed_with_actions(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        _enable_platform(sim_dir, "reddit")
        state = make_state(
            twitter_completed=True,
            reddit_completed=True,
            twitter_actions_count=3,
            reddit_actions_count=2,
        )
        assert not runner._completed_with_zero_actions(state)

    def test_neither_completed(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        _enable_platform(sim_dir, "reddit")
        state = make_state()
        assert not runner._completed_with_zero_actions(state)

    def test_one_enabled_but_not_completed(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        _enable_platform(sim_dir, "reddit")
        state = make_state(twitter_completed=True)
        assert not runner._completed_with_zero_actions(state)

    def test_no_platforms_enabled(self, runner, make_state):
        state = make_state()
        assert not runner._completed_with_zero_actions(state)


class TestCompletionTransition:
    def test_zero_action_completion_marks_failed(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        log_path = sim_dir / "twitter" / "actions.jsonl"
        log_path.write_text(
            json.dumps({"event_type": "simulation_end", "total_rounds": 3, "total_actions": 0}) + "\n",
            encoding="utf-8",
        )
        state = make_state()
        runner._read_action_log(str(log_path), 0, state, "twitter")
        assert state.runner_status == RunnerStatus.FAILED
        assert state.error == EXPECTED_ZERO_ACTIONS_ERROR
        assert state.completed_at is not None

    def test_completion_with_actions_marks_completed(self, runner, make_state, sim_dir):
        _enable_platform(sim_dir, "twitter")
        log_path = sim_dir / "twitter" / "actions.jsonl"
        lines = [
            json.dumps({
                "round": 1,
                "timestamp": "2026-01-01T00:00:00",
                "agent_id": 1,
                "agent_name": "agent-1",
                "action_type": "CREATE_POST",
                "success": True,
            }),
            json.dumps({"event_type": "simulation_end", "total_rounds": 3, "total_actions": 1}),
        ]
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        state = make_state()
        runner._read_action_log(str(log_path), 0, state, "twitter")
        assert state.runner_status == RunnerStatus.COMPLETED
        assert state.error is None
        assert state.completed_at is not None


class TestZeroActionsErrorConstant:
    def test_error_string_matches_spec(self):
        assert ZERO_ACTIONS_ERROR == EXPECTED_ZERO_ACTIONS_ERROR
