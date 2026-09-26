"""/api/simulation/start: a session's credit covers its first run (migrations/004)."""

import json
from types import SimpleNamespace

import pytest

from app.api import simulation as simulation_api
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import RunnerStatus, SimulationRunner
from app.services.supabase_client import SupabaseDB


class Ledger:
    """Records the Supabase writes /start makes."""

    def __init__(self, session=None):
        self.session = session
        self.deducted = []
        self.session_updates = []


@pytest.fixture
def start(api, tmp_path, monkeypatch):
    sim_dir = tmp_path / "sim_s"
    sim_dir.mkdir()
    (sim_dir / "state.json").write_text(json.dumps({"project_id": "proj_x", "status": "ready"}), encoding="utf-8")
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    ledger = Ledger()

    monkeypatch.setattr(SupabaseDB, "get_session", classmethod(lambda cls, sid, user_id=None: ledger.session))
    monkeypatch.setattr(SupabaseDB, "deduct_credit", classmethod(lambda cls, uid, desc="": ledger.deducted.append(desc) or True))
    monkeypatch.setattr(SupabaseDB, "update_session", classmethod(lambda cls, sid, **f: ledger.session_updates.append((sid, f)) or f))
    monkeypatch.setattr(SupabaseDB, "get_profile", classmethod(lambda cls, uid: {"plan": "pro", "credits": 3}))
    monkeypatch.setattr(SimulationRunner, "start_simulation",
                        classmethod(lambda cls, **kw: SimpleNamespace(to_dict=lambda: {"simulation_id": kw["simulation_id"]})))

    def post(body):
        return api.post("/api/simulation/start", json={"simulation_id": "sim_s", **body})

    return SimpleNamespace(post=post, ledger=ledger)


def test_first_run_of_a_session_is_covered(start):
    start.ledger.session = {"id": "sess1", "simulation_count": 0}
    res = start.post({"session_id": "sess1"})
    assert res.status_code == 200 and res.get_json()["data"]["credit_covered_by_session"] is True
    assert start.ledger.deducted == []
    assert start.ledger.session_updates == [
        ("sess1", {"simulation_id": "sim_s", "status": "simulating", "simulation_count": 1})
    ]


def test_later_runs_of_a_session_cost_a_credit(start):
    start.ledger.session = {"id": "sess1", "simulation_count": 1}
    res = start.post({"session_id": "sess1"})
    assert res.get_json()["data"]["credit_covered_by_session"] is False
    assert start.ledger.deducted == ["Simulation run"]
    assert start.ledger.session_updates[0][1]["simulation_count"] == 2


def test_a_run_without_a_session_costs_a_credit(start):
    start.post({})
    assert start.ledger.deducted == ["Simulation run"]
    assert start.ledger.session_updates == []


def test_someone_elses_or_unknown_session_covers_nothing(start):
    start.ledger.session = None  # get_session filters by the caller, so a foreign session is not found
    start.post({"session_id": "not-mine"})
    assert start.ledger.deducted == ["Simulation run"]
    assert start.ledger.session_updates == []


def test_a_failed_start_does_not_use_up_the_covered_run(start, monkeypatch):
    def boom(cls, **kw):
        raise RuntimeError("OASIS failed to launch")

    monkeypatch.setattr(SimulationRunner, "start_simulation", classmethod(boom))
    start.ledger.session = {"id": "sess1", "simulation_count": 0}
    assert start.post({"session_id": "sess1"}).status_code == 500
    assert start.ledger.deducted == [] and start.ledger.session_updates == []


class _RecordingTable:
    def __init__(self, calls):
        self.calls = calls

    def update(self, fields):
        self.calls.append(("update", fields))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": "sess1"}])


@pytest.mark.parametrize("runner_status,session_status", [("completed", "completed"), ("failed", "sim_failed")])
def test_run_status_marks_the_session_finished(api, monkeypatch, runner_status, session_status):
    calls = []
    monkeypatch.setattr(SupabaseDB, "client", staticmethod(lambda: SimpleNamespace(table=lambda name: _RecordingTable(calls))))
    monkeypatch.setattr(SimulationRunner, "get_run_state", classmethod(lambda cls, sid: SimpleNamespace(
        runner_status=RunnerStatus(runner_status), to_dict=lambda: {"runner_status": runner_status})))
    assert api.get("/api/simulation/sim_s/run-status").status_code == 200
    assert calls == [("update", {"status": session_status}), ("eq", "simulation_id", "sim_s"), ("eq", "status", "simulating")]


def test_run_status_while_running_leaves_the_session_alone(api, monkeypatch):
    calls = []
    monkeypatch.setattr(simulation_api, "_mark_session_finished", lambda *a: calls.append(a))
    monkeypatch.setattr(SimulationRunner, "get_run_state", classmethod(lambda cls, sid: SimpleNamespace(
        runner_status=RunnerStatus.RUNNING, to_dict=lambda: {"runner_status": "running"})))
    api.get("/api/simulation/sim_s/run-status")
    assert calls == []
