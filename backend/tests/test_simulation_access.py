"""Owner check on the simulation, graph and report APIs (app/api/simulation_access.py)."""

import json
import os
from types import SimpleNamespace

import pytest

import app as app_pkg
from app.middleware import auth
from app.models.project import ProjectManager
from app.services.report_agent import ReportManager
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner

OWNER, OTHER = "user-a", "user-b"
PROJECT = "<project>"  # replaced by the fixture's project id


def _sim(root, sim_id, project_id):
    sim_dir = root / "simulations" / sim_id
    sim_dir.mkdir(parents=True)
    (sim_dir / "state.json").write_text(json.dumps({"project_id": project_id, "status": "completed"}),
                                        encoding="utf-8")


def _as(user):
    return {"Authorization": f"Bearer {user}"} if user else {}


@pytest.fixture
def access(api):
    # Imported after ``api`` has patched a stale local zep_cloud (see conftest.py).
    from app.api import simulation_access

    return simulation_access


@pytest.fixture
def owned(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations"))
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path / "simulations"))
    # Auth on, patched on the Config auth_enabled() reads (test_config_tavily.py reloads
    # app.config, so a Config imported here may be a different object). A token is the user id.
    monkeypatch.setattr(auth.Config, "SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setattr(auth.Config, "SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr(auth, "_decode_supabase_jwt", lambda token: {"sub": token})

    project = ProjectManager.create_project("owned", user_id=OWNER)
    project.graph_id = "graph_a"
    ProjectManager.save_project(project)
    other = ProjectManager.create_project("someone else's", user_id=OTHER)
    legacy = ProjectManager.create_project("legacy, no owner recorded")
    _sim(tmp_path, "sim_a", project.project_id)
    _sim(tmp_path, "sim_b", other.project_id)
    _sim(tmp_path, "sim_legacy", legacy.project_id)
    reports = {"report_a": "sim_a", "report_b": "sim_b"}
    monkeypatch.setattr(ReportManager, "get_report", classmethod(
        lambda cls, rid: SimpleNamespace(report_id=rid, simulation_id=reports[rid], created_at="",
                                         to_dict=lambda: {"report_id": rid}) if rid in reports else None))
    monkeypatch.setattr(ReportManager, "list_reports", classmethod(
        lambda cls, simulation_id=None, limit=50: [cls.get_report(r) for r in reports]))
    return SimpleNamespace(root=tmp_path, project_id=project.project_id)


# ---------- ownership is recorded ----------


def test_project_records_its_owner(owned):
    assert ProjectManager.get_project(owned.project_id).user_id == OWNER
    assert json.loads((owned.root / "projects" / owned.project_id / "project.json").read_text())["user_id"] == OWNER


def test_projects_are_created_with_the_requesting_user():
    with open(os.path.join(os.path.dirname(app_pkg.__file__), "api", "graph.py"), encoding="utf-8") as f:
        src = f.read()
    assert "ProjectManager.create_project(name=project_name, user_id=g.user_id)" in src


def test_owners_resolve_through_the_project(access, owned):
    assert access.simulation_owner("sim_a") == OWNER
    assert access.report_owner("report_a") == OWNER
    assert access.graph_owners("graph_a") == {OWNER}
    assert access.graph_owners("graph_unknown") == set()
    assert access.simulation_owner("sim_legacy") is None


# ---------- routes naming an id ----------


def test_owner_passes(api, owned):
    assert api.get("/api/simulation/sim_a", headers=_as(OWNER)).status_code == 200
    res = api.post("/api/simulation/env-status", json={"simulation_id": "sim_a"}, headers=_as(OWNER))
    assert res.status_code == 200 and res.get_json()["success"] is True
    assert api.get(f"/api/graph/project/{owned.project_id}", headers=_as(OWNER)).status_code == 200


@pytest.mark.parametrize("method,path,body,label", [
    ("get", "/api/simulation/sim_a", None, "Simulation"),                               # path
    ("post", "/api/simulation/env-status", {"simulation_id": "sim_a"}, "Simulation"),   # JSON body
    ("post", "/api/simulation/interview/batch",
     {"simulation_id": "sim_a", "interviews": [{"agent_id": 0, "prompt": "Q"}]}, "Simulation"),
    ("get", f"/api/simulation/list?project_id={PROJECT}", None, "Project"),             # query string
    ("post", "/api/simulation/create", {"project_id": PROJECT}, "Project"),
    ("get", "/api/simulation/entities/graph_a", None, "Graph"),
    ("post", "/api/simulation/suggest-followups", {"report_id": "report_a"}, "Report"),
    ("get", f"/api/graph/project/{PROJECT}", None, "Project"),                          # graph blueprint
    ("get", "/api/graph/data/graph_a", None, "Graph"),
    ("get", "/api/report/report_a", None, "Report"),                                    # report blueprint
    ("get", "/api/report/by-simulation/sim_a", None, "Simulation"),
    ("post", "/api/report/compare", {"report_ids": ["report_b", "report_a"]}, "Report"),  # id list
])
def test_other_user_gets_404(api, owned, method, path, body, label):
    path = path.replace(PROJECT, owned.project_id)
    kwargs = {"json": {k: owned.project_id if v == PROJECT else v for k, v in body.items()}} if body else {}
    res = getattr(api, method)(path, headers=_as(OTHER), **kwargs)
    assert res.status_code == 404
    assert res.get_json()["error"].startswith(f"{label} not found: ")  # refused by the check, not the route


def test_run_with_no_recorded_owner_is_refused(api, owned):
    res = api.post("/api/simulation/env-status", json={"simulation_id": "sim_legacy"}, headers=_as(OWNER))
    assert res.status_code == 404


def test_missing_and_foreign_ids_look_the_same(api, owned):
    missing = api.get("/api/simulation/sim_missing", headers=_as(OTHER))
    foreign = api.get("/api/simulation/sim_a", headers=_as(OTHER))
    assert missing.status_code == foreign.status_code == 404
    assert missing.get_json()["error"] == "Simulation not found: sim_missing"
    assert not (owned.root / "simulations" / "sim_missing").exists()  # the check creates nothing


def test_unsafe_id_is_refused(api, owned):
    res = api.post("/api/simulation/env-status", json={"simulation_id": "../projects"}, headers=_as(OWNER))
    assert res.status_code == 404 and res.get_json()["error"] == "Simulation not found: ../projects"


def test_no_token_is_401(api, owned):
    assert api.get("/api/simulation/sim_a").status_code == 401


# ---------- list routes show only the caller's rows ----------


def test_lists_show_only_the_callers_rows(api, owned):
    sims = api.get("/api/simulation/list", headers=_as(OWNER)).get_json()["data"]
    assert [s["simulation_id"] for s in sims] == ["sim_a"]
    history = api.get("/api/simulation/history", headers=_as(OWNER)).get_json()["data"]
    assert [s["simulation_id"] for s in history] == ["sim_a"]
    projects = api.get("/api/graph/project/list", headers=_as(OWNER)).get_json()["data"]
    assert [p["project_id"] for p in projects] == [owned.project_id]
    reports = api.get("/api/report/list", headers=_as(OWNER)).get_json()["data"]
    assert [r["report_id"] for r in reports] == ["report_a"]


def test_task_list_route_is_gone(api, owned):
    assert api.get("/api/graph/tasks", headers=_as(OWNER)).status_code == 404


# ---------- tasks, sessions, bundles, deep research, dashboard ----------


def test_a_task_records_the_user_whose_request_created_it(api):
    from flask import g

    from app.models.task import TaskManager

    with api.application.test_request_context():
        g.user_id = OWNER
        in_request = TaskManager().create_task("t")
    outside = TaskManager().create_task("t", {"simulation_id": "sim_a"})
    assert TaskManager().get_task(in_request).metadata == {"user_id": OWNER}
    assert TaskManager().get_task(outside).metadata == {"simulation_id": "sim_a"}


def test_task_owner_is_recorded_or_derived(access, owned):
    from app.models.task import TaskManager

    tm = TaskManager()
    assert access.task_owners(tm.create_task("t", {"user_id": OWNER})) == {OWNER}
    assert access.task_owners(tm.create_task("t", {"simulation_id": "sim_a", "project_id": "x"})) == {OWNER}
    assert access.task_owners(tm.create_task("t", {})) == set()
    assert access.task_owners("no-such-task") == set()


@pytest.mark.parametrize("method,path_for,body_for,label", [
    ("get", lambda t: f"/api/graph/task/{t}", lambda t: None, "Task"),
    ("post", lambda t: "/api/simulation/prepare/status", lambda t: {"task_id": t}, "Task"),
    ("post", lambda t: "/api/report/generate/status", lambda t: {"task_id": t}, "Task"),
    ("get", lambda t: f"/api/source/deep-research/status/{t}", lambda t: None, "Task"),
    ("get", lambda t: f"/api/source/deep-research/result/{t}", lambda t: None, "Task"),
])
def test_other_users_task_is_404(api, owned, method, path_for, body_for, label):
    from app.models.task import TaskManager

    task_id = TaskManager().create_task("t", {"user_id": OWNER})
    body = body_for(task_id)
    res = getattr(api, method)(path_for(task_id), headers=_as(OTHER), **({"json": body} if body else {}))
    assert res.status_code == 404
    assert res.get_json()["error"] == f"{label} not found: {task_id}"
    assert api.get(f"/api/graph/task/{task_id}", headers=_as(OWNER)).status_code == 200


def test_session_patch_cannot_point_at_another_users_run(api, owned):
    res = api.patch("/api/session/some-session", json={"project_id": owned.project_id}, headers=_as(OTHER))
    assert res.status_code == 404 and res.get_json()["error"].startswith("Project not found: ")
    res = api.patch("/api/session/some-session", json={"simulation_id": "sim_a"}, headers=_as(OTHER))
    assert res.status_code == 404 and res.get_json()["error"] == "Simulation not found: sim_a"


def test_bundle_cannot_take_in_another_users_run(api, owned):
    res = api.post("/api/bundle/b1/complete-scenario", json={"simulation_id": "sim_a"}, headers=_as(OTHER))
    assert res.status_code == 404 and res.get_json()["error"] == "Simulation not found: sim_a"


def test_dashboard_lists_the_callers_projects_and_runs(api, owned):
    data = api.get("/api/dashboard/overview", headers=_as(OWNER)).get_json()["data"]
    assert [s["id"] for s in data["recent_simulations"]] == ["sim_a"]
    assert data["recent_simulations"][0]["title"] == "owned"
    assert data["recent_simulations"][0]["status"] == "completed"
    assert [p["id"] for p in data["recent_projects"]] == [owned.project_id]
    other = api.get("/api/dashboard/overview", headers=_as(OTHER)).get_json()["data"]
    assert [s["id"] for s in other["recent_simulations"]] == ["sim_b"]


def test_auth_off_checks_and_filters_nothing(api, owned, monkeypatch):
    monkeypatch.setattr(auth.Config, "SUPABASE_JWT_SECRET", "")
    assert api.get("/api/simulation/sim_b").status_code == 200
    sims = api.get("/api/simulation/list").get_json()["data"]
    assert {s["simulation_id"] for s in sims} == {"sim_a", "sim_b", "sim_legacy"}
