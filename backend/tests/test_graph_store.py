"""GraphStore selection, the Zep adapter's SDK mapping, and the in-memory fake.

ZepGraphStore tests replace the Zep client class with a MagicMock, so no network
call is possible (conftest also makes the real class raise if it is built).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from zep_cloud import AddNodeItem, EpisodeData

from app import config as app_config
from app.services import graph_store as gs
from app.services.graph_store import AddNodesResult, NewNode, TaskState, zep_store
from app.services.graph_store.fake_store import FakeGraphStore


@pytest.fixture
def zep(monkeypatch):
    """A ZepGraphStore whose SDK client is a MagicMock. Returns (store, client)."""
    client = MagicMock()
    monkeypatch.setattr(zep_store, "Zep", MagicMock(return_value=client))
    return zep_store.ZepGraphStore("zep-key"), client


# ---------- selection ----------


def test_test_suite_uses_the_fake_store():
    assert app_config.Config.GRAPH_BACKEND == "fake"
    assert gs.get_graph_store() is FakeGraphStore.shared()
    assert gs.graph_store_available() is True


def test_zep_backend_needs_a_key(monkeypatch):
    monkeypatch.setattr(app_config.Config, "GRAPH_BACKEND", "zep")
    monkeypatch.setattr(app_config.Config, "ZEP_API_KEY", "")
    assert gs.graph_store_available() is False
    assert gs.graph_store_unavailable_reason() == "ZEP_API_KEY not configured"
    with pytest.raises(ValueError, match="ZEP_API_KEY is not configured"):
        gs.get_graph_store()


def test_zep_backend_builds_a_zep_store(monkeypatch):
    monkeypatch.setattr(app_config.Config, "GRAPH_BACKEND", "Zep ")  # case and spaces are tolerated
    monkeypatch.setattr(app_config.Config, "ZEP_API_KEY", "from-config")
    made = MagicMock()
    monkeypatch.setattr(zep_store, "Zep", made)
    assert gs.graph_store_available() is True
    assert isinstance(gs.get_graph_store(), zep_store.ZepGraphStore)
    made.assert_called_once_with(api_key="from-config")
    gs.get_graph_store(api_key="explicit")
    made.assert_called_with(api_key="explicit")


def test_unknown_backend_fails_loud(monkeypatch):
    monkeypatch.setattr(app_config.Config, "GRAPH_BACKEND", "neo")
    with pytest.raises(ValueError, match="Unknown GRAPH_BACKEND"):
        gs.get_graph_store()
    with pytest.raises(ValueError, match="Unknown GRAPH_BACKEND"):
        gs.graph_store_available()


# ---------- ZepGraphStore: writes ----------


def test_create_add_text_delete_pass_through(zep):
    store, client = zep
    store.create_graph("g1", "Name", "Desc")
    store.add_text("g1", "agent did a thing")
    store.delete_graph("g1")
    client.graph.create.assert_called_once_with(graph_id="g1", name="Name", description="Desc")
    client.graph.add.assert_called_once_with(graph_id="g1", type="text", data="agent did a thing")
    client.graph.delete.assert_called_once_with(graph_id="g1")


def test_add_episodes_sends_text_episodes_and_returns_ids(zep):
    store, client = zep
    client.graph.add_batch.return_value = [
        SimpleNamespace(uuid_="a"),
        SimpleNamespace(uuid_=None, uuid="b"),
        SimpleNamespace(),  # no id: skipped, as before
    ]
    assert store.add_episodes("g1", ["one", "two", "three"]) == ["a", "b"]
    kwargs = client.graph.add_batch.call_args.kwargs
    assert kwargs["graph_id"] == "g1"
    assert all(isinstance(e, EpisodeData) for e in kwargs["episodes"])
    assert [(e.data, e.type) for e in kwargs["episodes"]] == [("one", "text"), ("two", "text"), ("three", "text")]


def test_add_episodes_non_list_result_gives_no_ids(zep):
    store, client = zep
    client.graph.add_batch.return_value = None
    assert store.add_episodes("g1", ["x"]) == []


def test_is_episode_processed(zep):
    store, client = zep
    client.graph.episode.get.return_value = SimpleNamespace(processed=True)
    assert store.is_episode_processed("ep1") is True
    client.graph.episode.get.assert_called_once_with(uuid_="ep1")
    client.graph.episode.get.return_value = SimpleNamespace()
    assert store.is_episode_processed("ep2") is False


def test_add_nodes_maps_new_nodes_to_add_node_items(zep):
    store, client = zep
    client.graph.add_nodes.return_value = SimpleNamespace(nodes=[1, 2], task_id="t1")
    res = store.add_nodes(
        "g1",
        [
            NewNode(name="NHS", label="Organization", summary="s", attributes={"org_name": "NHS"}),
            NewNode(name="Jo", label="Person"),
        ],
    )
    assert res == AddNodesResult(accepted=2, task_id="t1")
    items = client.graph.add_nodes.call_args.kwargs["nodes"]
    assert client.graph.add_nodes.call_args.kwargs["graph_id"] == "g1"
    assert all(isinstance(i, AddNodeItem) for i in items)
    assert (items[0].name, items[0].label, items[0].summary, items[0].attributes) == (
        "NHS",
        "Organization",
        "s",
        {"org_name": "NHS"},
    )
    assert (items[1].name, items[1].label, items[1].summary, items[1].attributes) == ("Jo", "Person", None, None)


def test_add_nodes_empty_response(zep):
    store, client = zep
    client.graph.add_nodes.return_value = None
    assert store.add_nodes("g1", [NewNode(name="x", label="Person")]) == AddNodesResult(accepted=0)
    client.graph.add_nodes.return_value = SimpleNamespace(nodes=None)
    assert store.add_nodes("g1", [NewNode(name="x", label="Person")]) == AddNodesResult(accepted=0, task_id=None)


def test_get_task_status(zep):
    store, client = zep
    client.task.get.return_value = SimpleNamespace(status="failed", error="boom")
    assert store.get_task_status("t1") == TaskState(status="failed", error="boom")
    client.task.get.assert_called_once_with(task_id="t1")


def test_set_ontology_builds_zep_models_and_renames_reserved_attributes(zep):
    store, client = zep
    ontology = {
        "entity_types": [
            {
                "name": "Person",
                "description": "A person.",
                "attributes": [{"name": "name", "description": "clashes"}, {"name": "role", "description": "r"}],
            }
        ],
        "edge_types": [
            {"name": "WORKS_FOR", "description": "d", "source_targets": [{"source": "Person", "target": "Org"}]},
            {"name": "NO_TARGETS", "description": "dropped: no source_targets"},
        ],
    }
    store.set_ontology("g1", ontology)
    kwargs = client.graph.set_ontology.call_args.kwargs
    assert kwargs["graph_ids"] == ["g1"]
    person = kwargs["entities"]["Person"]
    assert set(person.model_fields) == {"entity_name", "role"}
    assert set(kwargs["edges"]) == {"WORKS_FOR"}
    edge_cls, source_targets = kwargs["edges"]["WORKS_FOR"]
    assert edge_cls.__name__ == "WorksFor"
    assert [(st.source, st.target) for st in source_targets] == [("Person", "Org")]


def test_set_ontology_empty_makes_no_call(zep):
    store, client = zep
    store.set_ontology("g1", {})
    client.graph.set_ontology.assert_not_called()


# ---------- ZepGraphStore: reads ----------


def test_list_nodes_pages_and_converts_values_unchanged(zep, monkeypatch):
    store, client = zep
    raw = SimpleNamespace(uuid_="n1", name=None, labels=None, summary="s", attributes={"a": 1}, created_at="t")
    seen = {}

    def fake_fetch(c, graph_id, max_items):
        seen["args"] = (c, graph_id, max_items)
        return [raw]

    monkeypatch.setattr(zep_store, "fetch_all_nodes", fake_fetch)
    [node] = store.list_nodes("g1", max_items=7)
    assert seen["args"] == (client, "g1", 7)
    assert (node.uuid, node.uuid_, node.name, node.labels, node.summary, node.attributes, node.created_at) == (
        "n1",
        "n1",
        None,
        None,
        "s",
        {"a": 1},
        "t",
    )


def test_list_edges_converts_temporal_fields_and_episode_fallback(zep, monkeypatch):
    store, _client = zep
    raw = SimpleNamespace(
        uuid="e1",  # no uuid_: falls back to uuid
        name="WORKS_FOR",
        fact="Jo works for NHS",
        source_node_uuid="n1",
        target_node_uuid="n2",
        attributes=None,
        created_at="c",
        valid_at="v",
        invalid_at=None,
        expired_at="x",
        episode_ids=["ep1"],
        fact_type="WORKS_FOR",
    )
    monkeypatch.setattr(zep_store, "fetch_all_edges", lambda c, g: [raw])
    [edge] = store.list_edges("g1")
    assert edge.uuid_ == "e1"
    assert (edge.fact, edge.source_node_uuid, edge.target_node_uuid) == ("Jo works for NHS", "n1", "n2")
    assert (edge.created_at, edge.valid_at, edge.invalid_at, edge.expired_at) == ("c", "v", None, "x")
    assert edge.episodes == ["ep1"]
    assert edge.fact_type == "WORKS_FOR"


def test_get_node_and_node_edges(zep):
    store, client = zep
    client.graph.node.get.return_value = SimpleNamespace(uuid_="n1", name="NHS")
    assert store.get_node("n1").name == "NHS"
    client.graph.node.get.assert_called_once_with(uuid_="n1")
    client.graph.node.get.return_value = None
    assert store.get_node("missing") is None
    client.graph.node.get_entity_edges.return_value = [SimpleNamespace(uuid_="e1", fact="f")]
    assert [e.fact for e in store.get_node_edges("n1")] == ["f"]
    client.graph.node.get_entity_edges.assert_called_once_with(node_uuid="n1")
    client.graph.node.get_entity_edges.return_value = None
    assert store.get_node_edges("n1") == []


def test_search_passes_scope_and_reranker_and_converts(zep):
    store, client = zep
    client.graph.search.return_value = SimpleNamespace(edges=[SimpleNamespace(uuid_="e1", fact="f1")], nodes=None)
    res = store.search("g1", "who opposes", 30, "edges", "rrf")
    client.graph.search.assert_called_once_with(
        graph_id="g1", query="who opposes", limit=30, scope="edges", reranker="rrf"
    )
    assert [e.fact for e in res.edges] == ["f1"]
    assert res.nodes == []
    client.graph.search.return_value = SimpleNamespace()  # neither attribute present
    empty = store.search("g1", "q", 5, "nodes", "cross_encoder")
    assert (empty.edges, empty.nodes) == ([], [])


# ---------- FakeGraphStore ----------


def test_fake_store_round_trip():
    store = FakeGraphStore()
    store.create_graph("g", "n", "d")
    store.set_ontology("g", {"entity_types": []})
    assert store.add_nodes("g", [NewNode(name="NHS England", label="Organization", summary="regulator")]).accepted == 1
    nhs = store.list_nodes("g")[0]
    jo = store.seed_node("g", "Jo Bloggs", ["Entity", "Person"])
    edge = store.seed_edge("g", jo, nhs, "Jo Bloggs works for NHS England", name="WORKS_FOR")
    assert nhs.labels == ["Entity", "Organization"]
    assert store.get_node(jo.uuid) is jo
    assert store.get_node_edges(nhs.uuid) == [edge]
    assert store.search("g", "who works for NHS", 5, "edges", "rrf").edges == [edge]
    assert store.search("g", "regulator", 5, "nodes", "rrf").nodes == [nhs]
    ids = store.add_episodes("g", ["text one"])
    assert store.is_episode_processed(ids[0]) and store.episodes["g"] == ["text one"]
    assert store.get_task_status("any").status == "succeeded"
    store.add_text("g", "memory")
    assert store.texts["g"] == ["memory"]
    store.delete_graph("g")
    assert store.list_nodes("g") == [] and store.list_edges("g") == []


def test_conftest_blocks_a_real_zep_client():
    from zep_cloud.client import Zep

    with pytest.raises(AssertionError, match="real Zep client"):
        Zep(api_key="anything")
