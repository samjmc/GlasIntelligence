"""G4: one full product run on Graphiti, through the real HTTP API, with zero Zep calls.

    cd backend
    python ../docs/superpowers/plans/2026-10-02-graphiti-g4-e2e.py <document.md> <out_dir> [max_rounds]

Needs: Neo4j running, NEO4J_* and LLM_* in the environment. Costs DeepSeek tokens only
(well under $1). Zep cannot be reached: ZEP_API_KEY is removed, GRAPH_BACKEND=graphiti,
ZepGraphStore refuses to start on graphiti, and every attempt to build a zep_cloud
client is counted here and fails the run.

Supabase is stubbed IN THIS PROCESS ONLY: with no Supabase, /api/simulation/start cannot
take a credit (SupabaseDB.deduct_credit falls back to a client that raises). Billing is
not what G4 measures; the stub grants the run.

Steps: ontology/generate -> graph/build -> simulation create/prepare -> start (live graph
memory ON) -> report generate. Writes <out_dir>/g4_result.json.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import time

os.environ["GRAPH_BACKEND"] = "graphiti"
os.environ.pop("ZEP_API_KEY", None)
for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_JWT_SECRET"):
    os.environ[k] = ""  # anonymous mode: every request runs as user "anonymous"
sys.path.insert(0, os.getcwd())

DOC = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
MAX_ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 8
OUT.mkdir(parents=True, exist_ok=True)
REQUIREMENT = (
    "From March 2026 NHS England caps payments for Pharmacy First consultations, banded by each "
    "pharmacy's past volume. Over the following three months, how do community pharmacies, pharmacy "
    "chains, pharmacy bodies, patient groups, the NHS and the government react, and does the service shrink?"
)

# ---- zero-Zep tripwire ----
from zep_cloud.client import Zep  # noqa: E402

zep_attempts: list[str] = []


def _no_zep(self, *a, **k):
    import traceback

    zep_attempts.append("".join(traceback.format_stack(limit=6)))
    raise RuntimeError("G4: a Zep client was built during a GRAPH_BACKEND=graphiti run")


Zep.__init__ = _no_zep

# ---- Supabase stub (this process only) ----
from app.services import supabase_client as sc  # noqa: E402


class _Rows:
    data: list = []


class _Chain:
    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return _Rows()


class _Client:
    def table(self, _n):
        return _Chain()

    def rpc(self, *_a, **_k):
        return _Chain()


sc.SupabaseDB.client = staticmethod(lambda: _Client())
sc.SupabaseDB.deduct_credit = classmethod(lambda cls, user_id, description="": True)
sc.SupabaseDB.get_profile = classmethod(lambda cls, user_id: {"id": user_id, "plan": "pro", "credits": 99})

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402

assert Config.GRAPH_BACKEND == "graphiti", Config.GRAPH_BACKEND
app = create_app()
http = app.test_client()
log: dict = {"steps": {}, "max_rounds": MAX_ROUNDS}
T0 = time.time()


def step(name: str, t: float, **info) -> None:
    log["steps"][name] = {"seconds": round(time.time() - t), **info}
    print(f"[{time.time() - T0:6.0f}s] {name}: {json.dumps(info, default=str)[:400]}", flush=True)
    (OUT / "g4_result.json").write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")


def ok(resp) -> dict:
    body = resp.get_json(silent=True) or {}
    if resp.status_code >= 400 or not body.get("success", False):
        raise RuntimeError(f"{resp.request.method} {resp.request.path} -> {resp.status_code}: {str(body)[:500]}")
    return body.get("data", body)


def poll(fn, done, label: str, timeout: float, every: float = 10.0) -> dict:
    t = time.time()
    last = None
    while time.time() - t < timeout:
        data = fn()
        msg = str(data.get("message") or data.get("runner_status") or data.get("status"))
        if msg != last:
            print(
                f"    {label}: {data.get('status') or data.get('runner_status')} {data.get('progress', '')} {msg[:120]}",
                flush=True,
            )
            last = msg
        verdict = done(data)
        if verdict == "ok":
            return data
        if verdict == "fail":
            raise RuntimeError(f"{label} failed: {str(data)[:800]}")
        time.sleep(every)
    raise TimeoutError(f"{label} still running after {timeout:.0f}s")


try:
    # 1. project + ontology
    t = time.time()
    text = DOC.read_text(encoding="utf-8")
    d = ok(
        http.post(
            "/api/graph/ontology/generate",
            data={
                "simulation_requirement": REQUIREMENT,
                "project_name": "G4 Graphiti end-to-end",
                "files": (io.BytesIO(text.encode("utf-8")), DOC.name),
            },
            content_type="multipart/form-data",
        )
    )
    project_id = d["project_id"]
    step("ontology", t, project_id=project_id, entity_types=[e["name"] for e in d["ontology"]["entity_types"]])

    # 2. graph build (+ enrichment)
    t = time.time()
    task_id = ok(http.post("/api/graph/build", json={"project_id": project_id}))["task_id"]
    res = poll(
        lambda: ok(http.get(f"/api/graph/task/{task_id}")),
        lambda x: "ok" if x.get("status") == "completed" else "fail" if x.get("status") == "failed" else None,
        "graph build",
        timeout=3600,
    )
    graph_id = ok(http.get(f"/api/graph/project/{project_id}"))["graph_id"]
    gdata = ok(http.get(f"/api/graph/data/{graph_id}"))
    step(
        "graph_build",
        t,
        graph_id=graph_id,
        nodes=gdata["node_count"],
        edges=gdata["edge_count"],
        result=res.get("result"),
    )

    # 3. simulation create + prepare (profiles grounded on the graph)
    t = time.time()
    sim_id = ok(http.post("/api/simulation/create", json={"project_id": project_id}))["simulation_id"]
    prep = ok(http.post("/api/simulation/prepare", json={"simulation_id": sim_id}))
    ptask = prep.get("task_id")
    poll(
        lambda: ok(http.post("/api/simulation/prepare/status", json={"task_id": ptask, "simulation_id": sim_id})),
        lambda x: (
            "ok"
            if x.get("status") in ("completed", "ready") or x.get("already_prepared")
            else "fail"
            if x.get("status") == "failed"
            else None
        ),
        "prepare",
        timeout=3600,
    )
    profiles = ok(http.get(f"/api/simulation/{sim_id}/profiles")).get("profiles", [])
    step("prepare", t, simulation_id=sim_id, agents=len(profiles))

    # 4. run (live graph memory ON: before PR #18 the UI forced this, and it wrote to Zep)
    t = time.time()
    ok(
        http.post(
            "/api/simulation/start",
            json={
                "simulation_id": sim_id,
                "platform": "parallel",
                "max_rounds": MAX_ROUNDS,
                "enable_graph_memory_update": True,
                "force": True,
            },
        )
    )
    run = poll(
        lambda: ok(http.get(f"/api/simulation/{sim_id}/run-status")),
        lambda x: (
            "ok"
            if x.get("runner_status") == "completed"
            else "fail"
            if x.get("runner_status") in ("failed", "stopped")
            else None
        ),
        "simulation",
        timeout=3600,
        every=15,
    )
    time.sleep(20)  # let the memory updater flush its last batches
    gdata2 = ok(http.get(f"/api/graph/data/{graph_id}?refresh=true"))
    step(
        "simulate",
        t,
        rounds=run.get("current_round"),
        actions=run.get("total_actions_count") or run.get("twitter_actions_count"),
        graph_nodes_after=gdata2["node_count"],
        graph_edges_after=gdata2["edge_count"],
    )

    # 5. report
    t = time.time()
    rtask = ok(http.post("/api/report/generate", json={"simulation_id": sim_id})).get("task_id")
    rs = poll(
        lambda: ok(http.post("/api/report/generate/status", json={"task_id": rtask, "simulation_id": sim_id})),
        lambda x: "ok" if x.get("status") == "completed" else "fail" if x.get("status") == "failed" else None,
        "report",
        timeout=3600,
        every=15,
    )
    report_id = rs.get("report_id") or (rs.get("result") or {}).get("report_id")
    report = ok(http.get(f"/api/report/{report_id}"))
    md = report.get("markdown_content") or report.get("content") or ""
    (OUT / "g4_report.md").write_text(md, encoding="utf-8")
    agent_log = ok(http.get(f"/api/report/{report_id}/agent-log")).get("logs", [])
    tool_calls = [e for e in agent_log if e.get("action") in ("tool_call", "tool_result")]
    names = [n["name"] for n in gdata2.get("nodes", []) if n.get("name")]
    cited = sorted({n for n in names if len(n) > 4 and n in md})
    step(
        "report", t, report_id=report_id, chars=len(md), tool_log_entries=len(tool_calls), graph_names_cited=len(cited)
    )
    log["graph_names_cited_sample"] = cited[:25]
finally:
    log["zep_client_attempts"] = len(zep_attempts)
    log["zep_attempt_stacks"] = zep_attempts[:3]
    log["total_seconds"] = round(time.time() - T0)
    try:
        from app.services.graph_store.graphiti_store import GraphitiGraphStore

        if GraphitiGraphStore._shared is not None:
            log["graphiti_llm_usage"] = GraphitiGraphStore._shared.usage.snapshot()
    except Exception:
        pass
    (OUT / "g4_result.json").write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in log.items() if k != "zep_attempt_stacks"}, indent=1, default=str))
    if zep_attempts:
        raise SystemExit(f"FAIL: {len(zep_attempts)} Zep client construction attempt(s)")
