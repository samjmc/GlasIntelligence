"""API-level tests for the graph snapshot cache live read path.

Proves GET /api/graph/data/<graph_id> serves from the disk cache (MISS -> HIT)
and that mutation-generation invalidation forces a refetch after a rebuild.
"""

import pytest

from app.config import Config
from app.services.graph_builder import GraphBuilderService
from app.services import graph_snapshot_cache as gsc
from app.api import graph as graph_api


@pytest.fixture
def graph_cache_config(monkeypatch, tmp_path):
    """Point the disk cache at a temp dir with the cache enabled."""
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_CACHE_ENABLED", True)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_TTL_SECONDS", 3600)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS", 86400)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_MAX_DISK_MB", 0)
    monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_SINGLEFLIGHT", False)
    monkeypatch.setattr(graph_api, "_require_graph_ownership", lambda graph_id: None)
    yield str(tmp_path)


def _payload(graph_id: str, node_count: int) -> dict:
    return {
        "graph_id": graph_id,
        "nodes": [
            {"uuid": f"n{i}", "name": f"Stakeholder {i}", "labels": ["Organization"], "summary": "", "attributes": {}}
            for i in range(node_count)
        ],
        "edges": [],
        "node_count": node_count,
        "edge_count": 0,
    }


class TestGraphDataCacheHitAndMiss:
    def test_miss_then_hit_through_route(self, client, monkeypatch, graph_cache_config):
        gid = "api_graph_hit_01"
        calls = {"n": 0}

        def fake_fetch(self, graph_id):
            calls["n"] += 1
            return _payload(graph_id, 2)

        monkeypatch.setattr(GraphBuilderService, "get_graph_data", fake_fetch)

        r1 = client.get(f"/api/graph/data/{gid}")
        assert r1.status_code == 200
        assert r1.headers.get("X-Glas-Graph-Cache") == "MISS"
        assert calls["n"] == 1

        r2 = client.get(f"/api/graph/data/{gid}")
        assert r2.status_code == 200
        assert r2.headers.get("X-Glas-Graph-Cache") == "HIT"
        assert calls["n"] == 1, "second read must be served from cache, not Zep"

    def test_cache_disabled_always_fetches(self, client, monkeypatch, graph_cache_config):
        monkeypatch.setattr(Config, "GRAPH_SNAPSHOT_CACHE_ENABLED", False)
        gid = "api_graph_disabled_01"
        calls = {"n": 0}

        def fake_fetch(self, graph_id):
            calls["n"] += 1
            return _payload(graph_id, 1)

        monkeypatch.setattr(GraphBuilderService, "get_graph_data", fake_fetch)

        for _ in range(2):
            r = client.get(f"/api/graph/data/{gid}")
            assert r.status_code == 200
            assert r.headers.get("X-Glas-Graph-Cache") == "DISABLED"
        assert calls["n"] == 2


class TestGraphDataCacheRebuildInvalidation:
    def test_rebuild_does_not_serve_stale_snapshot(self, client, monkeypatch, graph_cache_config):
        """A rebuilt graph (generation bump) must refetch, never serve the old snapshot."""
        gid = "api_graph_rebuild_01"
        fetches: list[int] = []

        def fake_fetch(self, graph_id):
            count = len(fetches) + 1
            fetches.append(count)
            return _payload(graph_id, count)

        monkeypatch.setattr(GraphBuilderService, "get_graph_data", fake_fetch)

        r1 = client.get(f"/api/graph/data/{gid}")
        assert r1.headers.get("X-Glas-Graph-Cache") == "MISS"
        r2 = client.get(f"/api/graph/data/{gid}")
        assert r2.headers.get("X-Glas-Graph-Cache") == "HIT"
        assert r2.get_json()["data"]["node_count"] == 1

        # Simulate the rebuild: enrichment / memory updater bump the generation.
        gsc.bump_mutation_generation(gid)

        r3 = client.get(f"/api/graph/data/{gid}")
        assert r3.status_code == 200
        assert r3.headers.get("X-Glas-Graph-Cache") == "MISS"
        assert r3.get_json()["data"]["node_count"] == 2, "must serve the rebuilt graph, not the stale snapshot"

        r4 = client.get(f"/api/graph/data/{gid}")
        assert r4.headers.get("X-Glas-Graph-Cache") == "HIT"
        assert r4.get_json()["data"]["node_count"] == 2

    def test_delete_graph_invalidates_cache(self, client, monkeypatch, graph_cache_config):
        gid = "api_graph_delete_01"
        calls = {"n": 0}

        def fake_fetch(self, graph_id):
            calls["n"] += 1
            return _payload(graph_id, 1)

        monkeypatch.setattr(GraphBuilderService, "get_graph_data", fake_fetch)

        client.get(f"/api/graph/data/{gid}")
        assert calls["n"] == 1
        gsc.invalidate(gid)
        client.get(f"/api/graph/data/{gid}")
        assert calls["n"] == 2, "cache must be repopulated after invalidation"
