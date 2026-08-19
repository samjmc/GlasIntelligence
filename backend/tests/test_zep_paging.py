"""Tests for Zep list pagination (page-size cap and full-read behaviour).

Regression for 2026-08-19: Zep caps list responses at 50 items per page even
when a larger limit is requested. With page_size=100 a full page (50) looked
like the last page and silently truncated the graph (674 nodes read as 50).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.utils.zep_paging import fetch_all_nodes, fetch_all_edges


def _nodes(n):
    return [SimpleNamespace(name=f"n{i}", uuid_=f"uuid-{i}", labels=["Organization"]) for i in range(n)]


def _edges(n):
    return [
        SimpleNamespace(
            name="E", uuid_=f"e{i}", fact="f", source_node_uuid=f"uuid-{i}", target_node_uuid=f"uuid-{i + 1}"
        )
        for i in range(n)
    ]


def _client_with(nodes_per_page, total, kind="node"):
    client = MagicMock()
    calls = []

    def fake_get_by_graph_id(graph_id, **kwargs):
        page = len(calls)
        calls.append(kwargs)
        limit = kwargs.get("limit", 50)
        start = page * limit
        remaining = total - start
        batch = _nodes(min(limit, remaining)) if kind == "node" else _edges(min(limit, remaining))
        return batch

    getattr(client.graph, kind).get_by_graph_id.side_effect = fake_get_by_graph_id
    return client, calls


def test_fetch_all_nodes_reads_past_one_page():
    # 120 nodes, 50/page: must return all 120, not stop at the first 50.
    client, calls = _client_with(50, 120, "node")
    nodes = fetch_all_nodes(client, "g")
    assert len(nodes) == 120
    assert len(calls) == 3


def test_fetch_all_nodes_clamps_page_size_to_cap():
    # A caller passing page_size=100 would previously see a 50-item page as the
    # last page and stop early. The clamp must force 50/page so pagination runs.
    client, calls = _client_with(50, 120, "node")
    nodes = fetch_all_nodes(client, "g", page_size=100)
    assert len(nodes) == 120
    assert calls[0]["limit"] == 50


def test_fetch_all_edges_reads_past_one_page():
    client, calls = _client_with(50, 120, "edge")
    edges = fetch_all_edges(client, "g")
    assert len(edges) == 120
    assert len(calls) == 3


def test_fetch_all_edges_clamps_page_size_to_cap():
    client, calls = _client_with(50, 120, "edge")
    edges = fetch_all_edges(client, "g", page_size=100)
    assert len(edges) == 120
    assert calls[0]["limit"] == 50
