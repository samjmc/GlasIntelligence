"""Tests for the graph snapshot cache wiring (reader read-through, memory-updater bump, API route)."""

import pytest

from app.services.graph_snapshot_cache import CacheOutcome, CacheReadResult


class TestEntityReaderReadThrough:
    def test_hit_reuses_snapshot_without_zep(self, monkeypatch):
        from app.services import zep_entity_reader as er

        nodes = [
            {"uuid": "n1", "name": "NHS England", "labels": ["Entity", "Org"], "summary": "", "attributes": {}}
        ]
        edges = [
            {"uuid": "e1", "name": "regulates", "fact": "regulates", "source_node_uuid": "n1", "target_node_uuid": "n2", "attributes": {}}
        ]
        monkeypatch.setattr(er, "try_get_lists_for_entity_reader", lambda gid: (nodes, edges))

        def boom(*_a, **_k):
            raise AssertionError("Zep should not be called on cache HIT")

        monkeypatch.setattr(er, "fetch_all_nodes", boom)
        monkeypatch.setattr(er, "fetch_all_edges", boom)

        reader = er.ZepEntityReader(api_key="test-key")
        assert reader.get_all_nodes("graph_x") == nodes
        assert reader.get_all_edges("graph_x") == edges

    def test_miss_falls_through_to_zep(self, monkeypatch):
        from app.services import zep_entity_reader as er

        class FakeNode:
            uuid_ = "n1"
            name = "NHS England"
            labels = ["Entity", "Org"]
            summary = "summary"
            attributes = {"k": "v"}

        monkeypatch.setattr(er, "try_get_lists_for_entity_reader", lambda gid: None)
        monkeypatch.setattr(er, "fetch_all_nodes", lambda _c, _g: [FakeNode()])
        monkeypatch.setattr(er, "fetch_all_edges", lambda _c, _g: [])

        reader = er.ZepEntityReader(api_key="test-key")
        nodes = reader.get_all_nodes("graph_x")
        assert nodes[0]["uuid"] == "n1"
        assert nodes[0]["name"] == "NHS England"
        assert reader.get_all_edges("graph_x") == []


class TestMemoryUpdaterBump:
    def _updater(self, monkeypatch):
        from types import SimpleNamespace

        from app.services.zep_graph_memory_updater import ZepGraphMemoryUpdater

        bumped = []
        monkeypatch.setattr(
            "app.services.zep_graph_memory_updater.bump_mutation_generation",
            lambda gid: bumped.append(gid),
        )
        updater = ZepGraphMemoryUpdater(graph_id="graph_x", api_key="test-key")
        updater.client = SimpleNamespace(graph=SimpleNamespace(add=lambda **_kw: None))
        return updater, bumped

    def test_successful_batch_bumps_generation(self, monkeypatch):
        from app.services.zep_graph_memory_updater import AgentActivity

        updater, bumped = self._updater(monkeypatch)
        activity = AgentActivity(
            platform="twitter",
            agent_id=1,
            agent_name="NHS England",
            action_type="CREATE_POST",
            action_args={"content": "hello"},
            round_num=1,
            timestamp="2026-01-01T00:00:00Z",
        )
        updater._send_batch_activities([activity], "twitter")
        assert bumped == ["graph_x"]
        assert updater._total_items_sent == 1

    def test_failed_batch_does_not_bump(self, monkeypatch):
        from app.services.zep_graph_memory_updater import AgentActivity

        updater, bumped = self._updater(monkeypatch)

        def raise_error(**_kw):
            raise RuntimeError("zep down")

        updater.client.graph.add = raise_error
        updater.MAX_RETRIES = 1
        activity = AgentActivity(
            platform="twitter",
            agent_id=1,
            agent_name="NHS England",
            action_type="CREATE_POST",
            action_args={"content": "hello"},
            round_num=1,
            timestamp="2026-01-01T00:00:00Z",
        )
        updater._send_batch_activities([activity], "twitter")
        assert bumped == []
        assert updater._failed_count == 1


class TestGraphDataRouteCache:
    def _get_graph_data(self, client, monkeypatch):
        import app.api.graph as graph_mod

        monkeypatch.setattr(graph_mod.Config, "ZEP_API_KEY", "test-key")
        return graph_mod.get_graph_data

    def test_route_hit_sets_cache_headers(self, client, monkeypatch):
        import app.api.graph as graph_mod

        self._get_graph_data(client, monkeypatch)
        monkeypatch.setattr(
            graph_mod,
            "get_graph_data_cached",
            lambda gid, _fetch, refresh=False: ({"graph_id": gid, "nodes": [], "edges": []}, CacheOutcome.HIT, 12.0),
        )
        resp = client.get("/api/graph/data/graph_x")
        assert resp.status_code == 200
        assert resp.headers["X-Glas-Graph-Cache"] == "HIT"
        assert resp.headers["X-Glas-Graph-Cache-Age"] == "12"

    def test_route_refresh_forces_fetch(self, client, monkeypatch):
        import app.api.graph as graph_mod

        self._get_graph_data(client, monkeypatch)
        calls = []

        def fake_cached(gid, fetch, refresh=False):
            calls.append(refresh)
            return ({"graph_id": gid, "nodes": [], "edges": []}, CacheOutcome.BYPASS, None)

        monkeypatch.setattr(graph_mod, "get_graph_data_cached", fake_cached)
        client.get("/api/graph/data/graph_x?refresh=true")
        assert calls == [True]

    def test_route_serves_stale_on_zep_failure(self, client, monkeypatch):
        import app.api.graph as graph_mod

        self._get_graph_data(client, monkeypatch)

        def raise_error(*_a, **_k):
            raise RuntimeError("zep 429")

        monkeypatch.setattr(graph_mod, "get_graph_data_cached", raise_error)
        monkeypatch.setattr(
            graph_mod,
            "try_stale_fallback",
            lambda gid: CacheReadResult({"graph_id": gid, "nodes": [], "edges": []}, CacheOutcome.STALE, 3600.0),
        )
        resp = client.get("/api/graph/data/graph_x")
        assert resp.status_code == 200
        assert resp.headers["X-Glas-Graph-Cache"] == "STALE"

    def test_route_500_when_no_stale_and_zep_fails(self, client, monkeypatch):
        import app.api.graph as graph_mod

        self._get_graph_data(client, monkeypatch)

        def raise_error(*_a, **_k):
            raise RuntimeError("zep down")

        monkeypatch.setattr(graph_mod, "get_graph_data_cached", raise_error)
        monkeypatch.setattr(graph_mod, "try_stale_fallback", lambda gid: CacheReadResult(None, CacheOutcome.MISS, None))
        resp = client.get("/api/graph/data/graph_x")
        assert resp.status_code == 500
