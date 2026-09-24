"""Config values that merge f9f6e07 silently dropped from config.py.

Each test fails on main as of 837527d. See the PR that restored them for the
audit of that merge.
"""

import os

import pytest

from app.config import Config


def test_demo_mode_defaults_off():
    # simulation_interview_env_routes reads Config.DEMO_MODE on every batch
    # interview; without the attribute that request is an AttributeError (500).
    assert Config.DEMO_MODE is False or "DEMO_MODE" in os.environ


@pytest.mark.skipif("GRAPH_SNAPSHOT_TTL_SECONDS" in os.environ, reason="env overrides the default")
def test_graph_snapshot_ttl_default_is_seven_days():
    # 5106829 raised it from 24h to 7d on purpose (mutation-generation bumps are
    # the real invalidation; the TTL is only a safety net, and every miss is a
    # paid Zep read). docs/graph-cache.md documents 604800.
    assert Config.GRAPH_SNAPSHOT_TTL_SECONDS == 604800


_BATCH = {"simulation_id": "sim_does_not_exist", "interviews": [{"agent_id": 0, "prompt": "What about the caps?"}]}


def test_batch_interview_live_mode_reaches_env_guard(client):
    res = client.post("/api/simulation/interview/batch", json=_BATCH)
    body = res.get_json()
    assert "DEMO_MODE" not in str(body)
    # Not demo mode, and no OASIS subprocess for this id: the env-alive guard answers.
    assert res.status_code == 400, body
    assert "not running" in body["error"]


def test_batch_interview_demo_mode_serves_canned(client, monkeypatch):
    monkeypatch.setattr(Config, "DEMO_MODE", True)
    res = client.post("/api/simulation/interview/batch", json=_BATCH)
    body = res.get_json()
    assert res.status_code == 200, body
    assert "recorded response" in str(body).lower()
