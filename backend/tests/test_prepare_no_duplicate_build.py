"""Reopening Step 2 while personas are still being built must attach, not start a second build.

/prepare treated "not prepared yet" as "start preparing", including while a build for the
same simulation was running. A reload, or the history modal's "Environment Setup", started a
parallel persona build: double LLM cost, both threads writing the same profile files.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import simulation as simulation_api
from app.models.task import TaskManager, TaskStatus


@pytest.fixture
def preparing_sim(monkeypatch):
    state = SimpleNamespace(project_id="proj_x", entities_count=90, entity_types=["Company"], status="preparing")
    monkeypatch.setattr(simulation_api.SimulationManager, "get_simulation", lambda self, sid: state)
    monkeypatch.setattr(simulation_api, "_check_simulation_prepared", lambda sid: (False, {"reason": "building"}))
    project_lookups = []
    monkeypatch.setattr(
        simulation_api.ProjectManager, "get_project", staticmethod(lambda pid: project_lookups.append(pid))
    )
    tm = TaskManager()
    created = []
    yield tm, created, project_lookups
    with tm._task_lock:
        for tid in created:
            tm._tasks.pop(tid, None)


def _task(tm, created, sim_id, status):
    tid = tm.create_task("simulation_prepare", metadata={"simulation_id": sim_id})
    tm.update_task(tid, status=status)
    created.append(tid)
    return tid


def test_reopening_mid_build_attaches_to_the_running_task(api, preparing_sim):
    tm, created, project_lookups = preparing_sim
    running = _task(tm, created, "sim_x", TaskStatus.PROCESSING)

    res = api.post("/api/simulation/prepare", json={"simulation_id": "sim_x"})

    body = res.get_json()
    assert res.status_code == 200, body
    assert body["data"]["task_id"] == running
    assert body["data"]["already_running"] is True
    assert project_lookups == []  # returned before any new build was set up
    assert len([t for t in tm.list_tasks("simulation_prepare") if t["metadata"]["simulation_id"] == "sim_x"]) == 1


def test_a_finished_or_other_build_does_not_block_a_new_one(api, preparing_sim):
    tm, created, project_lookups = preparing_sim
    _task(tm, created, "sim_x", TaskStatus.FAILED)
    _task(tm, created, "sim_other", TaskStatus.PROCESSING)

    res = api.post("/api/simulation/prepare", json={"simulation_id": "sim_x"})

    # Falls through to the normal path; the fake project lookup returns None -> 404.
    assert res.status_code == 404
    assert project_lookups == ["proj_x"]
