import json

import pytest
from flask import Flask

from app.middleware.demo_recorder import init_recorder, normalise_path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/api/simulation/create", "/api/simulation/create"),
        ("/api/session/550e8400-e29b-41d4-a716-446655440000", "/api/session/:id"),
        ("/api/session/demo_MTc1NDY1MA_energy_ab12cd34", "/api/session/:id"),
        ("/api/graph/task/12345", "/api/graph/task/:id"),
        ("/api/graph/data/graph_abc123def456789?refresh=true", "/api/graph/data/:id"),
        # Regression: a long endpoint name is not an id. "suggest-followups" is
        # 17 characters, so a naive length-only rule collapses it to :id and
        # silently merges it with any sibling endpoint.
        ("/api/simulation/suggest-followups", "/api/simulation/suggest-followups"),
        ("/api/billing/can-research", "/api/billing/can-research"),
    ],
)
def test_normalise_path(raw, expected):
    assert normalise_path(raw) == expected


def test_recorder_writes_entries_in_tape_format(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/simulation/create", methods=["POST"])
    def create():
        return {"success": True, "data": {"id": "sim-1"}}

    init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.post("/api/simulation/create", json={})

    tape = json.loads(out.read_text())

    assert tape["schema_version"] == 1
    assert tape["scenario"] == "test-scenario"
    assert len(tape["entries"]) == 1

    entry = tape["entries"][0]
    assert entry["method"] == "POST"
    assert entry["path"] == "/api/simulation/create"
    assert entry["status"] == 200
    assert entry["body"] == {"success": True, "data": {"id": "sim-1"}}
    assert entry["t_ms"] >= 0


def test_recorder_ignores_non_api_routes(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/healthz")
    def health():
        return {"ok": True}

    init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/healthz")

    assert json.loads(out.read_text())["entries"] == []


def test_recorder_skips_non_json_responses(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/report/download")
    def download():
        return "binary-ish", 200, {"Content-Type": "application/pdf"}

    init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/api/report/download")

    assert json.loads(out.read_text())["entries"] == []
