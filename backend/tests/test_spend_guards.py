"""Spend and load guards: concurrent-run cap, site-wide daily free-run cap, LLM balance floor.

Uses the in-memory Supabase of test_free_run_and_refunds, so the ledger counts are real.
Config is patched on the object the app code reads (spend_guards.Config): test_config_tavily
re-imports app.config, after which "app.config.Config" is a different class from the app's.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import simulation as simulation_api
from app.services import spend_guards
from app.services.simulation_runner import RunnerStatus, SimulationRunner, SimulationRunState
from app.services.supabase_client import FREE_RUN_DESCRIPTION, SupabaseDB
from tests.test_free_run_and_refunds import USER, db, research, start  # noqa: F401 (fixtures)

REAL_FETCH = spend_guards._fetch_llm_balance_usd  # conftest replaces it in every test
Config = spend_guards.Config


def _active_run(sim_id, status=RunnerStatus.RUNNING):
    SimulationRunner._run_states[sim_id] = SimulationRunState(simulation_id=sim_id, runner_status=status)
    SimulationRunner._processes[sim_id] = SimpleNamespace(pid=2, poll=lambda: None)


@pytest.fixture
def processes(monkeypatch):
    monkeypatch.setattr(SimulationRunner, "_processes", {})


def _free_runs_today(db, n):  # noqa: F811
    rows = db.tables.setdefault("credit_transactions", [])
    now = datetime.now(UTC).isoformat()
    for i in range(n):
        rows.append(
            {"user_id": f"other_{i}", "type": "usage", "amount": 0, "description": FREE_RUN_DESCRIPTION, "created_at": now}
        )


def _balance(monkeypatch, usd):
    monkeypatch.setattr(spend_guards, "_fetch_llm_balance_usd", lambda: usd)


# ---------- concurrency cap ----------


def test_busy_at_cap_gets_429_and_nothing_is_charged(start, db, processes):  # noqa: F811
    db.profile()["credits"] = 1
    _active_run("sim_a")
    _active_run("sim_b", RunnerStatus.PAUSED)
    res = start.post()
    assert res.status_code == 429
    assert res.get_json()["error"] == "server_busy"
    assert db.profile()["credits"] == 1 and db.txs() == [] and start.launched == []


def test_below_cap_and_finished_or_stale_runs_do_not_count(start, db, processes):  # noqa: F811
    db.profile()["credits"] = 1
    _active_run("sim_a")
    _active_run("sim_done", RunnerStatus.COMPLETED)  # process kept alive for interviews
    # Read from disk after a crash: says running, but this server holds no process for it
    SimulationRunner._run_states["sim_stale"] = SimulationRunState("sim_stale", runner_status=RunnerStatus.RUNNING)
    assert SimulationRunner.count_active_runs() == 1
    assert start.post().status_code == 200
    assert db.profile()["credits"] == 0


def test_forced_restart_of_the_same_simulation_does_not_count_itself(api, start, db, processes, monkeypatch):  # noqa: F811
    monkeypatch.setattr(Config, "MAX_CONCURRENT_SIMULATIONS", 1)
    db.profile()["credits"] = 1
    _active_run("sim_s")  # the run being restarted is the only one, so the server is "full"
    state_file = Path(SimulationRunner.RUN_STATE_DIR) / "sim_s" / "state.json"
    state_file.write_text('{"project_id": "proj_x", "status": "running"}', encoding="utf-8")
    monkeypatch.setattr(simulation_api, "_check_simulation_prepared", lambda sim_id: (True, {}))
    monkeypatch.setattr(SimulationRunner, "cleanup_simulation_logs", classmethod(lambda cls, sim_id: {"success": True}))
    stopped = []

    def fake_stop(cls, sim_id):
        stopped.append(sim_id)
        SimulationRunner._run_states[sim_id].runner_status = RunnerStatus.STOPPED
        SimulationRunner._processes.pop(sim_id, None)

    monkeypatch.setattr(SimulationRunner, "stop_simulation", classmethod(fake_stop))
    res = api.post("/api/simulation/start", json={"simulation_id": "sim_s", "force": True})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["force_restarted"] is True
    assert stopped == ["sim_s"] and len(start.launched) == 1


# ---------- site-wide daily free-run cap ----------


def test_daily_free_cap_pauses_free_runs(start, db):  # noqa: F811
    _free_runs_today(db, 5)
    res = start.post()
    assert res.status_code == 429
    assert res.get_json()["error"] == "free_runs_paused"
    assert len(db.txs("usage")) == 5 and start.launched == []


def test_daily_free_cap_does_not_touch_paid_runs(start, db):  # noqa: F811
    _free_runs_today(db, 5)
    db.profile()["credits"] = 1
    assert start.post().status_code == 200
    assert db.profile()["credits"] == 0


def test_daily_count_is_today_utc_free_rows_only(db):  # noqa: F811
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    db.tables["credit_transactions"] = [
        {"type": "usage", "amount": 0, "description": FREE_RUN_DESCRIPTION, "created_at": yesterday},
        {"type": "usage", "amount": -1, "description": "Simulation run", "created_at": datetime.now(UTC).isoformat()},
        {"type": "research_usage", "amount": 0, "description": "Free monthly briefing", "created_at": yesterday},
    ]
    _free_runs_today(db, 2)
    assert SupabaseDB.count_free_runs_today() == 2


# ---------- LLM balance floor ----------


def test_low_balance_refuses_free_run(start, db, monkeypatch):  # noqa: F811
    _balance(monkeypatch, 4.99)
    res = start.post()
    assert res.status_code == 429 and res.get_json()["error"] == "free_runs_paused"
    assert db.txs() == [] and start.launched == []


def test_low_balance_leaves_paid_runs_alone(start, db, monkeypatch):  # noqa: F811
    _balance(monkeypatch, 0.5)
    db.profile()["credits"] = 1
    assert start.post().status_code == 200


def test_unknown_balance_does_not_block_free_run(start, db, monkeypatch):  # noqa: F811
    _balance(monkeypatch, None)
    assert start.post().status_code == 200
    assert [t["description"] for t in db.txs("usage")] == [FREE_RUN_DESCRIPTION]


def test_low_balance_refuses_free_briefing_but_not_paid(research, db, monkeypatch):  # noqa: F811
    _balance(monkeypatch, 1.0)
    res = research()
    assert res.status_code == 402 and res.get_json()["error"] == "free_research_paused"
    assert db.txs("research_usage") == []
    db.profile()["research_credits"] = 1
    assert research().status_code == 200
    assert db.profile()["research_credits"] == 0


# ---------- /api/billing/can-simulate ----------


def _can_simulate(api):
    res = api.get("/api/billing/can-simulate")
    assert res.status_code == 200
    return res.get_json()["data"]


def test_can_simulate_free_user_not_paused(api, db):  # noqa: F811
    data = _can_simulate(api)
    assert (data["can_simulate"], data["free_runs_paused"], data["paused_reason"]) == (True, False, None)


def test_can_simulate_reports_daily_cap(api, db):  # noqa: F811
    _free_runs_today(db, 5)
    data = _can_simulate(api)
    assert (data["can_simulate"], data["free_run_left"]) == (False, True)
    assert (data["free_runs_paused"], data["paused_reason"]) == (True, "daily_cap")


def test_can_simulate_reports_low_balance(api, db, monkeypatch):  # noqa: F811
    _balance(monkeypatch, 2.0)
    data = _can_simulate(api)
    assert (data["can_simulate"], data["free_runs_paused"], data["paused_reason"]) == (False, True, "low_balance")


def test_can_simulate_paid_plan_is_never_paused(api, db, monkeypatch):  # noqa: F811
    db.profile().update(plan="pro", credits=3)
    _balance(monkeypatch, 0.0)
    data = _can_simulate(api)
    assert (data["can_simulate"], data["free_runs_paused"], data["paused_reason"]) == (True, False, None)


# ---------- the balance helper ----------


@pytest.fixture
def deepseek(monkeypatch):
    monkeypatch.setattr(spend_guards, "_fetch_llm_balance_usd", REAL_FETCH)
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://api.deepseek.com")
    calls = []

    def respond(body=None, error=None):
        def get(url, headers=None, timeout=None):
            calls.append((url, headers))
            if error:
                raise error
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

        monkeypatch.setattr(spend_guards.requests, "get", get)

    return SimpleNamespace(calls=calls, respond=respond)


def test_balance_is_read_once_and_cached(deepseek):
    deepseek.respond(
        {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "1"}, {"currency": "USD", "total_balance": "19.95"}]}
    )
    assert spend_guards.llm_balance_usd() == 19.95
    assert spend_guards.llm_balance_usd() == 19.95
    assert len(deepseek.calls) == 1
    assert deepseek.calls[0][0] == spend_guards.DEEPSEEK_BALANCE_URL


def test_balance_is_none_when_the_call_fails(deepseek):
    deepseek.respond(error=ConnectionError("down"))
    assert spend_guards.llm_balance_usd() is None
    assert len(deepseek.calls) == 1
    assert spend_guards.llm_balance_low() is False


def test_balance_is_none_and_not_called_for_other_providers(deepseek, monkeypatch):
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://api.openai.com/v1")
    deepseek.respond({"balance_infos": [{"currency": "USD", "total_balance": "0"}]})
    assert spend_guards.llm_balance_usd() is None
    assert deepseek.calls == []
