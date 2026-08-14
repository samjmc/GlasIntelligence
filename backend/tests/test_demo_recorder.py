import json
from unittest import mock

import pytest
from flask import Flask

from app.middleware.demo_recorder import (
    canonical_query,
    init_recorder,
    normalise_path,
    scrub_body,
    _stable_demo_uuid,
)


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
        # MINOR 8: non-ASCII digits must not match [0-9] (Python \d was Unicode-aware)
        ("/api/x/٠١٢", "/api/x/٠١٢"),
        # MINOR 8: path ending with \n (from Werkzeug %0A decode) — $ would match before \n
        ("/api/simulation/create\n", "/api/simulation/create\n"),
    ],
)
def test_normalise_path(raw, expected):
    assert normalise_path(raw) == expected


# ── canonical_query ──────────────────────────────────────────────────────────
# These cases must be behaviourally identical to canonicalQuery() in
# frontend/src/demo/tape.js — change both or neither.

@pytest.mark.parametrize(
    "qs,expected",
    [
        ("", ""),
        ("from_line=0", "from_line=0"),
        ("z=1&a=2", "a=2&z=1"),
        ("key=hello%20world", "key=hello+world"),  # urllib re-encodes space as +
    ],
)
def test_canonical_query(qs, expected):
    assert canonical_query(qs) == expected


# ── scrub_body ───────────────────────────────────────────────────────────────

def test_scrub_body_redacts_bearer_token():
    body = {"authorization": "Bearer eyJhbGci.abc.def"}
    result = scrub_body(body)
    assert "<REDACTED>" in result["authorization"]
    assert "eyJhbGci" not in result["authorization"]


def test_scrub_body_redacts_api_key():
    body = {"key": "sk_live_ABC123defghij0000"}
    result = scrub_body(body)
    assert result["key"] == "<REDACTED>"


def test_scrub_body_redacts_stripe_customer():
    body = {"customer_id": "cus_abc123XYZfoo"}
    result = scrub_body(body)
    assert result["customer_id"] == "<REDACTED>"


def test_scrub_body_rewrites_uuid_stably():
    real = "550e8400-e29b-41d4-a716-446655440000"
    body = {"id": real, "ref": real}
    result = scrub_body(body)
    # Same UUID → same demo replacement
    assert result["id"] == result["ref"]
    # Demo replacement is not the original UUID
    assert result["id"] != real
    # Calling scrub_body again produces the same stable replacement
    assert scrub_body({"id": real})["id"] == result["id"]


def test_scrub_body_preserves_non_secret_strings():
    body = {"name": "NHS Pharmacy First", "count": 42, "ok": True}
    assert scrub_body(body) == body


def test_scrub_body_recurses_into_nested_structures():
    body = {"nested": {"deep": "Bearer abc123def456ghi"}, "items": ["Bearer xyz"]}
    result = scrub_body(body)
    assert "<REDACTED>" in result["nested"]["deep"]
    assert "<REDACTED>" in result["items"][0]


def test_recorder_writes_entries_in_tape_format(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/simulation/create", methods=["POST"])
    def create():
        return {"success": True, "data": {"id": "sim-1"}}

    close = init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.post("/api/simulation/create", json={})

    # call close() to flush the tail (in production, atexit does this)
    close()

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

    close = init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/healthz")

    close()

    assert json.loads(out.read_text())["entries"] == []


def test_recorder_skips_non_json_responses(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/report/download")
    def download():
        return "binary-ish", 200, {"Content-Type": "application/pdf"}

    close = init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/api/report/download")

    close()

    assert json.loads(out.read_text())["entries"] == []


def test_recorder_continues_on_flush_failure(tmp_path):
    """Verify that a failing flush does not crash the request pipeline.

    The in-request flush is guarded — it must not propagate OSError.
    The init-time flush is intentionally NOT patched here: we test the
    in-request path only, so the init flush completes normally.
    """
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/simulation/create", methods=["POST"])
    def create():
        return {"success": True, "data": {"id": "sim-1"}}, 200

    from app.middleware.demo_recorder import FLUSH_EVERY
    close = init_recorder(app, str(out), scenario="test-scenario")

    # Make exactly FLUSH_EVERY requests so the in-request flush fires,
    # then patch open only for that flush call.
    with app.test_client() as client:
        # First FLUSH_EVERY - 1 requests accumulate without flushing.
        for _ in range(FLUSH_EVERY - 1):
            client.post("/api/simulation/create", json={})
        # The FLUSH_EVERY-th request triggers the guarded in-request flush.
        with mock.patch(
            "app.middleware.demo_recorder.open", side_effect=OSError("Disk full")
        ):
            response = client.post("/api/simulation/create", json={})
            # Request should return 200, not 500 due to flush error
            assert response.status_code == 200
            assert response.json == {"success": True, "data": {"id": "sim-1"}}
    close()


def test_recorder_preserves_query_string_in_path(tmp_path):
    """Query params must be recorded so the browser replayer can disambiguate cursors."""
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/report/<report_id>/agent-log")
    def agent_log(report_id):
        from flask import request as req
        from_line = req.args.get("from_line", "0")
        return {"success": True, "data": {"logs": [], "from_line": int(from_line)}}

    close = init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/api/report/abc123/agent-log?from_line=0")
        client.get("/api/report/abc123/agent-log?from_line=5")

    close()

    tape = json.loads(out.read_text())
    paths = [e["path"] for e in tape["entries"]]

    # Normalised path segment (:id) plus the cursor query param must be recorded.
    assert any("from_line=0" in p for p in paths), f"from_line=0 not in {paths}"
    assert any("from_line=5" in p for p in paths), f"from_line=5 not in {paths}"


def test_recorder_scrubs_secrets_from_body(tmp_path):
    """Secrets in response bodies must be redacted before writing to tape."""
    out = tmp_path / "tape.json"
    app = Flask(__name__)
    real_uuid = "550e8400-e29b-41d4-a716-446655440000"

    @app.route("/api/user/me")
    def me():
        return {
            "success": True,
            "data": {
                "id": real_uuid,
                "token": "Bearer super-secret-token",
                "stripe_customer": "cus_ABC123secret",
            },
        }

    close = init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/api/user/me")

    close()

    tape = json.loads(out.read_text())
    body = tape["entries"][0]["body"]["data"]

    assert body["id"] != real_uuid, "Real UUID must be rewritten"
    assert body["id"].startswith("demo0000"), "Rewritten ID must have demo prefix"
    assert "<REDACTED>" in body["token"], "Bearer token must be redacted"
    assert "<REDACTED>" in body["stripe_customer"], "Stripe customer ID must be redacted"


def test_recorder_buffered_flush(tmp_path):
    """Tape is only flushed every FLUSH_EVERY entries, not on every response."""
    from app.middleware.demo_recorder import FLUSH_EVERY

    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/ping")
    def ping():
        return {"success": True}

    # Count how many times os.replace is called (the atomic rename that completes a flush).
    with mock.patch("app.middleware.demo_recorder.os.replace", wraps=__import__("os").replace) as m:
        close = init_recorder(app, str(out), scenario="test-scenario")
        # The init-time flush called replace once.
        assert m.call_count == 1, f"Expected 1 replace at init, got {m.call_count}"

        with app.test_client() as client:
            for _ in range(FLUSH_EVERY - 1):
                client.get("/api/ping")
        # No in-request flush yet (we have FLUSH_EVERY - 1 unflushed entries).
        assert m.call_count == 1, (
            f"Expected still 1 flush after {FLUSH_EVERY - 1} requests, got {m.call_count}"
        )

        with app.test_client() as client:
            client.get("/api/ping")  # The FLUSH_EVERY-th request triggers a batch flush
        assert m.call_count == 2, (
            f"Expected 2 flushes (init + one batch) after {FLUSH_EVERY} requests, got {m.call_count}"
        )

        close()
