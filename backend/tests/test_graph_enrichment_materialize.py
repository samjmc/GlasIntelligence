"""Tests for direct inventory materialization via Zep add_nodes.

Verifies that verified inventory entities are materialized as graph nodes
deterministically (add_nodes), not left to the unreliable episode/NER path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.graph_enrichment_service import GraphEnrichmentService

from zep_cloud import AddNodeItem


def _inventory(names_with_cats):
    return [{"name": n, "category": c, "context": f"Context for {n}"} for n, c in names_with_cats]


def _add_nodes_resp(node_names, task_id="task-1"):
    nodes = [SimpleNamespace(name=n) for n in node_names]
    return SimpleNamespace(nodes=nodes, task_id=task_id)


def _task_resp(status="succeeded"):
    return SimpleNamespace(status=status, error=None)


@pytest.fixture
def svc():
    client = MagicMock()
    client.task.get.return_value = _task_resp("succeeded")
    service = GraphEnrichmentService(zep_client=client, llm_client=MagicMock())
    return service, client


def test_materializes_missing_inventory_nodes(svc):
    service, client = svc
    inv = _inventory([("PSNC", "association"), ("NPA", "industry_body"), ("RCGP", "association")])
    client.graph.add_nodes.return_value = _add_nodes_resp(["PSNC", "NPA", "RCGP"])

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 3
    assert client.graph.add_nodes.call_count == 1
    _, kwargs = client.graph.add_nodes.call_args
    assert kwargs["graph_id"] == "g1"
    items = kwargs["nodes"]
    assert all(isinstance(i, AddNodeItem) for i in items)
    assert {i.name for i in items} == {"PSNC", "NPA", "RCGP"}
    assert client.task.get.call_count == 1


def test_skips_entities_already_in_graph(svc):
    service, client = svc
    inv = _inventory([("PSNC", "association"), ("NPA", "industry_body")])
    client.graph.add_nodes.return_value = _add_nodes_resp(["PSNC"])

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names={"npa"},
    )

    assert added == 1
    _, kwargs = client.graph.add_nodes.call_args
    assert [i.name for i in kwargs["nodes"]] == ["PSNC"]


def test_batches_over_one_hundred(svc):
    service, client = svc
    inv = [{"name": f"Org {i}", "category": "company", "context": "x"} for i in range(250)]
    # Simulate two batches of 100 and one of 50.
    def fake_add_nodes(**kwargs):
        n = len(kwargs["nodes"])
        return _add_nodes_resp([f"Org {i}" for i in range(n)])

    client.graph.add_nodes.side_effect = fake_add_nodes

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 250
    assert client.graph.add_nodes.call_count == 3


def test_add_nodes_failure_is_fail_soft(svc):
    service, client = svc
    inv = _inventory([("PSNC", "association"), ("NPA", "industry_body")])
    client.graph.add_nodes.side_effect = RuntimeError("boom")

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 0  # never raises


def test_materialization_wired_into_enrich_graph(svc):
    service, client = svc
    inv = _inventory(
        [
            ("NHS", "government"),
            ("PSNC", "association"),
            ("NPA", "industry_body"),
        ]
    )
    # _get_node_stats returns the empty graph before add_nodes, then the
    # materialized nodes after (mirrors the async add_nodes task completing).
    materialized_nodes = [
        SimpleNamespace(name=n, labels=["Organization"]) for n in ("NHS", "PSNC", "NPA")
    ]
    service.client.task.get.return_value = _task_resp("succeeded")
    service.client.graph.add_nodes.return_value = _add_nodes_resp(["NHS", "PSNC", "NPA"])
    with patch(
        "app.services.graph_enrichment_service.fetch_all_nodes",
        side_effect=[[], materialized_nodes],
    ):
        result = service.enrich_graph(
            graph_id="g1",
            source_text="text",
            entity_inventory=inv,
            target_entities=3,
            max_rounds=2,
        )

    assert result.stopped_reason == "target_reached"
    assert client.graph.add_nodes.call_count == 1
    _, kwargs = client.graph.add_nodes.call_args
    assert {i.name for i in kwargs["nodes"]} == {"NHS", "PSNC", "NPA"}


def test_materialization_disabled_skips_add_nodes(svc):
    service, client = svc
    inv = _inventory([("PSNC", "association")])
    with patch("app.services.graph_enrichment_service.fetch_all_nodes", return_value=[]), patch.object(
        service.__class__, "EPISODE_PROCESSING_TIMEOUT", 0.1
    ), patch("app.services.graph_enrichment_service.Config.GRAPH_MATERIALIZE_INVENTORY_ENABLED", False):
        # Round path finds nothing to send; enrich_graph returns without add_nodes.
        result = service.enrich_graph(
                    graph_id="g1",
                    source_text="text",
                    entity_inventory=inv,
                    target_entities=5,
                    max_rounds=1,
                )
    assert client.graph.add_nodes.call_count == 0
    assert result.stopped_reason == "no_new_nodes"
