"""Config values that merge f9f6e07 silently dropped from config.py.

Each test fails on main as of 837527d. See the PR that restored them for the
audit of that merge.
"""

import os

import pytest

from app.config import Config


@pytest.mark.skipif("GRAPH_SNAPSHOT_TTL_SECONDS" in os.environ, reason="env overrides the default")
def test_graph_snapshot_ttl_default_is_seven_days():
    # 5106829 raised it from 24h to 7d on purpose (mutation-generation bumps are
    # the real invalidation; the TTL is only a safety net, and every miss is a
    # paid Zep read). docs/graph-cache.md documents 604800.
    assert Config.GRAPH_SNAPSHOT_TTL_SECONDS == 604800


_BATCH = {"simulation_id": "sim_does_not_exist", "interviews": [{"agent_id": 0, "prompt": "What about the caps?"}]}


def test_batch_interview_reaches_normal_path(client):
    res = client.post("/api/simulation/interview/batch", json=_BATCH)
    body = res.get_json()
    # The normal path answers: this simulation id does not exist.
    assert res.status_code == 404, body
    assert "does not exist" in body["error"]
