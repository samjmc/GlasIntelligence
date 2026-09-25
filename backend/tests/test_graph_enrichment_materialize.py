"""Tests for direct inventory materialization via the graph store's add_nodes.

Verifies that verified inventory entities are materialized as graph nodes
deterministically (add_nodes), not left to the unreliable episode/NER path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.graph_enrichment_service import GraphEnrichmentService
from app.services.graph_store import AddNodesResult, NewNode, TaskState
from app.services.graph_store.zep_store import ZepGraphStore


def _inventory(names_with_cats):
    return [{"name": n, "category": c, "context": f"Context for {n}"} for n, c in names_with_cats]


def _add_nodes_resp(node_names, task_id="task-1"):
    return AddNodesResult(accepted=len(node_names), task_id=task_id)


@pytest.fixture
def svc():
    store = MagicMock(spec=ZepGraphStore)
    store.get_task_status.return_value = TaskState("succeeded")
    service = GraphEnrichmentService(store=store, llm_client=MagicMock())
    return service, store


def test_materializes_missing_inventory_nodes(svc):
    service, store = svc
    inv = _inventory([("PSNC", "association"), ("NPA", "industry_body"), ("RCGP", "association")])
    store.add_nodes.return_value = _add_nodes_resp(["PSNC", "NPA", "RCGP"])

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 3
    assert store.add_nodes.call_count == 1
    (graph_id, items), _ = store.add_nodes.call_args
    assert graph_id == "g1"
    assert all(isinstance(i, NewNode) for i in items)
    assert {i.name for i in items} == {"PSNC", "NPA", "RCGP"}
    psnc = next(i for i in items if i.name == "PSNC")
    assert psnc.label == "Organization"
    assert psnc.summary == "Context for PSNC"
    assert psnc.attributes == {"org_name": "PSNC", "sector": "association"}
    store.get_task_status.assert_called_once_with("task-1")


def test_skips_entities_already_in_graph(svc):
    service, store = svc
    inv = _inventory([("PSNC", "association"), ("NPA", "industry_body")])
    store.add_nodes.return_value = _add_nodes_resp(["PSNC"])

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names={"npa"},
    )

    assert added == 1
    (_, items), _ = store.add_nodes.call_args
    assert [i.name for i in items] == ["PSNC"]


def test_batches_over_one_hundred(svc):
    service, store = svc
    inv = [{"name": f"Org {i}", "category": "company", "context": "x"} for i in range(250)]

    # Simulate two batches of 100 and one of 50.
    def fake_add_nodes(graph_id, nodes):
        return _add_nodes_resp([n.name for n in nodes])

    store.add_nodes.side_effect = fake_add_nodes

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 250
    assert store.add_nodes.call_count == 3
    assert [len(c.args[1]) for c in store.add_nodes.call_args_list] == [100, 100, 50]


def test_no_task_id_skips_task_poll(svc):
    service, store = svc
    inv = _inventory([("PSNC", "association")])
    store.add_nodes.return_value = AddNodesResult(accepted=1, task_id=None)

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 1
    assert store.get_task_status.call_count == 0


def test_add_nodes_task_polls_until_succeeded(svc):
    service, store = svc
    store.get_task_status.side_effect = [TaskState("pending"), TaskState("succeeded")]

    with patch("app.services.graph_enrichment_service.time.sleep"):
        service._wait_for_add_nodes_task("task-1")

    assert store.get_task_status.call_count == 2


def test_add_nodes_task_failed_stops_polling(svc):
    service, store = svc
    store.get_task_status.return_value = TaskState("failed", error="bad attrs")

    service._wait_for_add_nodes_task("task-1")

    assert store.get_task_status.call_count == 1


def test_add_nodes_failure_is_fail_soft(svc):
    service, store = svc
    inv = _inventory([("PSNC", "association"), ("NPA", "industry_body")])
    store.add_nodes.side_effect = RuntimeError("boom")

    added = service._materialize_inventory_nodes(
        graph_id="g1",
        entity_inventory=inv,
        existing_node_names=set(),
    )

    assert added == 0  # never raises


def test_materialization_wired_into_enrich_graph(svc):
    service, store = svc
    inv = _inventory(
        [
            ("NHS", "government"),
            ("PSNC", "association"),
            ("NPA", "industry_body"),
        ]
    )
    # _get_node_stats returns the empty graph before add_nodes, then the
    # materialized nodes after (mirrors the async add_nodes task completing).
    materialized_nodes = [SimpleNamespace(name=n, labels=["Organization"]) for n in ("NHS", "PSNC", "NPA")]
    store.add_nodes.return_value = _add_nodes_resp(["NHS", "PSNC", "NPA"])
    store.list_nodes.side_effect = [[], materialized_nodes]

    result = service.enrich_graph(
        graph_id="g1",
        source_text="text",
        entity_inventory=inv,
        target_entities=3,
        max_rounds=2,
    )

    assert result.stopped_reason == "target_reached"
    assert store.add_nodes.call_count == 1
    (_, items), _ = store.add_nodes.call_args
    assert {i.name for i in items} == {"NHS", "PSNC", "NPA"}
    assert store.list_nodes.call_count == 2


def test_materialization_disabled_skips_add_nodes(svc):
    service, store = svc
    inv = _inventory([("PSNC", "association")])
    store.list_nodes.return_value = []
    with (
        patch.object(service.__class__, "EPISODE_PROCESSING_TIMEOUT", 0.1),
        patch("app.services.graph_enrichment_service.Config.GRAPH_MATERIALIZE_INVENTORY_ENABLED", False),
    ):
        # Round path finds nothing to send; enrich_graph returns without add_nodes.
        result = service.enrich_graph(
            graph_id="g1",
            source_text="text",
            entity_inventory=inv,
            target_entities=5,
            max_rounds=1,
        )
    assert store.add_nodes.call_count == 0
    assert result.stopped_reason == "no_new_nodes"
