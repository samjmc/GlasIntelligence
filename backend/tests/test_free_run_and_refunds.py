"""Free plan's monthly simulation + briefing, and the automatic refund of a zero-action run.

SupabaseDB runs for real against an in-memory table store (FakeSupabase), so the credit
ledger rules (net free usage, optimistic credit refund) are exercised, not stubbed.
"""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api import source_agent
from app.services import simulation_runner
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import RunnerStatus, SimulationRunner, SimulationRunState
from app.services.supabase_client import SupabaseDB

USER = "anonymous"  # the request user when Supabase auth is not configured (middleware/auth.py)


class _Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.op, self.payload, self.want_count, self.filters = "select", None, False, []

    def select(self, *cols, count=None):
        self.want_count = count is not None
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, fields):
        self.op, self.payload = "update", fields
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def gte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and r.get(col) >= val)
        return self

    def execute(self):
        rows = self.store.tables.setdefault(self.table, [])
        if self.op == "insert":
            row = {"id": str(uuid.uuid4()), "created_at": datetime.now(UTC).isoformat(), **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[row], count=None)
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        return SimpleNamespace(data=[dict(r) for r in hit], count=len(hit) if self.want_count else None)


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _Query(self, name)

    def rpc(self, *a, **k):
        raise RuntimeError("no RPCs here")  # SupabaseDB then uses its table fallback

    def txs(self, tx_type=None):
        return [t for t in self.tables.get("credit_transactions", []) if tx_type is None or t["type"] == tx_type]

    def profile(self):
        return self.tables["profiles"][0]


@pytest.fixture
def db(monkeypatch):
    fake = FakeSupabase()
    fake.tables["profiles"] = [{"id": USER, "plan": "free", "credits": 0, "research_credits": 0}]
    monkeypatch.setattr(SupabaseDB, "client", staticmethod(lambda: fake))
    return fake


# ---------- /api/simulation/start ----------


@pytest.fixture
def start(api, db, tmp_path, monkeypatch):
    sim_dir = tmp_path / "sim_s"
    sim_dir.mkdir()
    (sim_dir / "state.json").write_text(json.dumps({"project_id": "proj_x", "status": "ready"}), encoding="utf-8")
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({"time_config": {"total_simulation_hours": 72, "minutes_per_round": 30}}), encoding="utf-8"
    )
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_run_states", {})
    launched = []
    # Real start_simulation (it applies the round cap), without launching OASIS or the monitor
    monkeypatch.setattr(
        simulation_runner.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or SimpleNamespace(pid=1)
    )
    monkeypatch.setattr(simulation_runner.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    yield SimpleNamespace(post=lambda: api.post("/api/simulation/start", json={"simulation_id": "sim_s"}), launched=launched)
    log = SimulationRunner._stdout_files.pop("sim_s", None)
    if log:
        log.close()
    SimulationRunner._processes.pop("sim_s", None)
    SimulationRunner._action_queues.pop("sim_s", None)
    SimulationRunner._graph_memory_enabled.pop("sim_s", None)


def test_free_user_with_no_credits_gets_the_monthly_run_capped_small(start, db):
    res = start.post()
    assert res.status_code == 200, res.get_json()
    assert [(t["amount"], t["description"]) for t in db.txs("usage")] == [(0, "Free monthly simulation")]
    assert db.profile()["credits"] == 0
    assert res.get_json()["data"]["total_rounds"] == 15  # FREE_SIMULATION_ROUNDS; the config has 144
    assert start.launched[0][-2:] == ["--max-rounds", "15"]
    with open(f"{SimulationRunner.RUN_STATE_DIR}/sim_s/run_state.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert (saved["charge"], saved["charged_user_id"]) == ("free", USER)


def test_free_user_who_used_this_months_run_gets_402(start, db):
    SupabaseDB.insert_credit_tx(USER, 0, "usage", "Free monthly simulation")
    res = start.post()
    assert res.status_code == 402 and res.get_json()["error"] == "insufficient_credits"
    assert len(db.txs("usage")) == 1 and start.launched == []


def test_a_given_back_free_run_can_be_used_again(start, db):
    SupabaseDB.insert_credit_tx(USER, 0, "usage", "Free monthly simulation")
    SupabaseDB.insert_credit_tx(USER, 0, "refund", "Refund: free simulation produced no agent actions")
    assert start.post().status_code == 200
    assert len(db.txs("usage")) == 2


def test_last_months_run_does_not_count(db):
    db.tables["credit_transactions"] = [
        {"user_id": USER, "type": "usage", "amount": 0, "created_at": "2000-01-15T00:00:00+00:00"}
    ]
    assert SupabaseDB.has_free_simulation_remaining(USER) is True


def test_a_free_user_with_a_credit_spends_the_credit(start, db):
    db.profile()["credits"] = 1
    assert start.post().status_code == 200
    assert db.profile()["credits"] == 0
    assert [(t["amount"], t["type"]) for t in db.txs()] == [(-1, "usage")]


# ---------- zero-action refund (monitor path) ----------


def _run_monitor(sim_id):
    SimulationRunner._processes[sim_id] = SimpleNamespace(poll=lambda: 0, returncode=0)
    SimulationRunner._monitor_simulation(sim_id)


@pytest.fixture
def zero_action_run(db, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_run_states", {})
    monkeypatch.setattr(SimulationRunner, "_refund_attempts", set())

    def make(charge):
        (tmp_path / "sim_z" / "reddit").mkdir(parents=True)
        (tmp_path / "sim_z" / "reddit" / "actions.jsonl").write_text(
            json.dumps({"event_type": "simulation_end", "total_rounds": 3, "total_actions": 0}) + "\n",
            encoding="utf-8",
        )
        SimulationRunner._save_run_state(
            SimulationRunState(
                simulation_id="sim_z", runner_status=RunnerStatus.RUNNING, charge=charge, charged_user_id=USER
            )
        )
        return "sim_z"

    return make


def test_zero_action_credit_run_is_refunded_exactly_once(db, zero_action_run):
    db.profile()["credits"] = 4
    sim = zero_action_run("credit")
    _run_monitor(sim)
    state = SimulationRunner.get_run_state(sim)
    assert state.runner_status == RunnerStatus.FAILED and state.refunded
    assert state.error.endswith("Your simulation credit was refunded.")

    # The monitor runs again on the saved state (e.g. after a restart): no second refund
    SimulationRunner._run_states.clear()
    SimulationRunner._refund_attempts.clear()
    _run_monitor(sim)

    assert db.profile()["credits"] == 5
    assert [(t["amount"], t["description"]) for t in db.txs("refund")] == [
        (1, "Refund: simulation produced no agent actions")
    ]


def test_zero_action_free_run_gives_the_free_run_back(db, zero_action_run):
    SupabaseDB.insert_credit_tx(USER, 0, "usage", "Free monthly simulation")
    assert SupabaseDB.has_free_simulation_remaining(USER) is False
    sim = zero_action_run("free")
    _run_monitor(sim)
    assert SupabaseDB.has_free_simulation_remaining(USER) is True
    assert SimulationRunner.get_run_state(sim).error.endswith("Your free run was given back.")
    assert db.profile()["credits"] == 0


def test_zero_action_session_run_is_not_refunded(db, zero_action_run):
    sim = zero_action_run("session")
    _run_monitor(sim)
    state = SimulationRunner.get_run_state(sim)
    assert state.runner_status == RunnerStatus.FAILED and not state.refunded
    assert db.txs() == [] and db.profile()["credits"] == 0


def test_a_refund_error_does_not_crash_the_monitor(db, zero_action_run, monkeypatch):
    def boom(cls, *a, **k):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(SupabaseDB, "refund_credit", classmethod(boom))
    sim = zero_action_run("credit")
    _run_monitor(sim)
    state = SimulationRunner.get_run_state(sim)
    assert state.runner_status == RunnerStatus.FAILED and not state.refunded
    assert "refunded" not in state.error


# ---------- /api/source/deep-research ----------


@pytest.fixture
def research(api, db, monkeypatch):
    monkeypatch.setattr(source_agent.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    return lambda prompt="What happens if the energy price cap goes?": api.post(
        "/api/source/deep-research", json={"prompt": prompt}
    )


def test_free_user_gets_two_free_briefings_a_month(research, db):
    assert research().status_code == 200
    assert research().status_code == 200
    third = research()
    assert third.status_code == 402 and third.get_json()["error"] == "no_research_credits"
    assert [(t["amount"], t["description"]) for t in db.txs("research_usage")] == [(0, "Free monthly briefing")] * 2
    assert db.profile()["research_credits"] == 0 and db.txs("research_refund") == []


def test_no_free_briefing_once_the_free_run_is_used(research, db):
    SupabaseDB.insert_credit_tx(USER, 0, "usage", "Free monthly simulation")
    assert research().status_code == 402
    assert db.txs("research_usage") == []


def test_invalid_prompt_on_the_free_path_uses_and_refunds_nothing(research, db):
    assert research("short").status_code == 400
    assert db.txs() == [] and db.profile()["research_credits"] == 0
