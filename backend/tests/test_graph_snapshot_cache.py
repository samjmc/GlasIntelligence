"""Unit tests for graph snapshot cache."""

import json
import os

import pytest

from app.services import graph_snapshot_cache as gsc
from app.config import Config


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload))
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_CACHE_ENABLED", True)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_TTL_SECONDS", 3600)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS", 86400)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_MAX_DISK_MB", 0)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_SINGLEFLIGHT", False)
    yield str(upload)


def test_sanitize_graph_id():
    assert gsc.sanitize_graph_id("abc-123_X") == "abc-123_X"
    assert gsc.sanitize_graph_id("../etc/passwd") is None
    assert gsc.sanitize_graph_id("") is None


def test_write_read_hit(cache_dir):
    gid = "testgraph_01"
    payload = {
        "graph_id": gid,
        "nodes": [{"uuid": "n1", "name": "A", "labels": [], "summary": "", "attributes": {}}],
        "edges": [],
        "node_count": 1,
        "edge_count": 0,
    }
    assert gsc.write_snapshot(gid, payload) is True
    r = gsc.try_read_snapshot(gid)
    assert r.outcome == gsc.CacheOutcome.HIT
    assert r.data["node_count"] == 1
    assert r.data["nodes"][0]["name"] == "A"


def test_bump_invalidates(cache_dir):
    gid = "testgraph_02"
    payload = {
        "graph_id": gid,
        "nodes": [],
        "edges": [],
        "node_count": 0,
        "edge_count": 0,
    }
    gsc.write_snapshot(gid, payload)
    assert gsc.try_read_snapshot(gid).outcome == gsc.CacheOutcome.HIT
    gsc.bump_mutation_generation(gid)
    assert gsc.try_read_snapshot(gid).outcome == gsc.CacheOutcome.MISS


def test_invalidate_removes(cache_dir):
    gid = "testgraph_03"
    payload = {"graph_id": gid, "nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
    gsc.write_snapshot(gid, payload)
    gsc.invalidate(gid)
    assert gsc.try_read_snapshot(gid).outcome == gsc.CacheOutcome.MISS


def test_get_graph_data_cached_miss_then_hit(cache_dir):
    gid = "testgraph_04"
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {
            "graph_id": gid,
            "nodes": [],
            "edges": [],
            "node_count": 0,
            "edge_count": 0,
        }

    d1, o1, _ = gsc.get_graph_data_cached(gid, fetch, refresh=False)
    assert o1 == gsc.CacheOutcome.MISS
    d2, o2, _ = gsc.get_graph_data_cached(gid, fetch, refresh=False)
    assert o2 == gsc.CacheOutcome.HIT
    assert calls["n"] == 1
    assert d1["graph_id"] == d2["graph_id"]


def test_corrupt_snapshot_removed(cache_dir):
    gid = "testgraph_05"
    safe = gsc.sanitize_graph_id(gid)
    d = os.path.join(cache_dir, "graph_cache", safe)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "snapshot.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("not json")
    r = gsc.try_read_snapshot(gid)
    assert r.outcome == gsc.CacheOutcome.MISS
    assert not os.path.isfile(path)


def test_try_get_lists_for_entity_reader(cache_dir):
    gid = "testgraph_06"
    payload = {
        "graph_id": gid,
        "nodes": [
            {
                "uuid": "u1",
                "name": "N1",
                "labels": ["Person"],
                "summary": "s",
                "attributes": {"k": 1},
            }
        ],
        "edges": [
            {
                "uuid": "e1",
                "name": "rel",
                "fact": "f",
                "source_node_uuid": "u1",
                "target_node_uuid": "u2",
                "attributes": {},
            }
        ],
        "node_count": 1,
        "edge_count": 1,
    }
    gsc.write_snapshot(gid, payload)
    pair = gsc.try_get_lists_for_entity_reader(gid)
    assert pair is not None
    nodes, edges = pair
    assert len(nodes) == 1 and nodes[0]["uuid"] == "u1"
    assert len(edges) == 1 and edges[0]["fact"] == "f"
