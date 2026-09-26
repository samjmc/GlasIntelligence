"""One GraphStore contract, run against every backend we can reach.

- FakeGraphStore: always.
- GraphitiGraphStore: only with RUN_GRAPHITI_IT=1 (real Neo4j + a real LLM, a few cents of
  DeepSeek). Needs NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD and LLM_* in the environment.
  NEO4J_URI alone is not enough, because it is often set on a dev machine.
- ZepGraphStore: never here. It is metered; tests/test_graph_store.py pins its SDK mapping.
"""

import json
import os
import uuid
from dataclasses import asdict

import pytest

from app import config as app_config
from app.services.graph_store import NewNode
from app.services.graph_store.fake_store import FakeGraphStore

RUN_IT = os.environ.get("RUN_GRAPHITI_IT") == "1"

ONTOLOGY = {
    "entity_types": [
        {"name": "Person", "description": "A named individual.", "attributes": [{"name": "role"}]},
        {"name": "Organization", "description": "A company or public body.", "attributes": [{"name": "sector"}]},
    ],
    "edge_types": [
        {
            "name": "WORKS_FOR",
            "description": "Employment.",
            "source_targets": [{"source": "Person", "target": "Organization"}],
        }
    ],
}
TEXT = (
    "Dr Leyla Hannbeck is the chief executive of the Independent Pharmacies Association. "
    "She said the NHS England payment caps on Pharmacy First will push small pharmacies to close."
)


def _graphiti_store(monkeypatch):
    pytest.importorskip("graphiti_core")
    for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"):
        # conftest replaces LLM_API_KEY with a placeholder; the live run needs the real ones.
        if os.environ.get(key):
            monkeypatch.setattr(app_config.Config, key, os.environ[key])
    from app.services.graph_store.graphiti_store import GraphitiGraphStore

    return GraphitiGraphStore.shared()


@pytest.fixture(params=["fake", "graphiti"])
def store(request, monkeypatch):
    if request.param == "fake":
        return FakeGraphStore()
    if not RUN_IT:
        pytest.skip("set RUN_GRAPHITI_IT=1 to run against real Neo4j + LLM")
    return _graphiti_store(monkeypatch)


@pytest.fixture
def graph_id(store):
    gid = f"it_{uuid.uuid4().hex[:12]}"
    store.create_graph(gid, "contract test", "GraphStore contract test graph")
    yield gid
    store.delete_graph(gid)


def test_add_nodes_then_read_them_back(store, graph_id):
    res = store.add_nodes(
        graph_id,
        [
            NewNode(
                name="Community Pharmacy England",
                label="Organization",
                summary="Negotiator.",
                attributes={"sector": "health"},
            ),
            NewNode(name="Jo Bloggs", label="Person"),
        ],
    )
    assert res.accepted == 2
    nodes = {n.name: n for n in store.list_nodes(graph_id)}
    assert {"Community Pharmacy England", "Jo Bloggs"} <= set(nodes)
    cpe = nodes["Community Pharmacy England"]
    assert "Organization" in cpe.labels and cpe.uuid_ == cpe.uuid
    assert cpe.attributes.get("sector") == "health"
    got = store.get_node(cpe.uuid)
    assert got is not None and got.name == "Community Pharmacy England"
    assert store.get_node(str(uuid.uuid4())) is None
    assert isinstance(store.get_node_edges(cpe.uuid), list)
    if res.task_id:
        assert store.get_task_status(res.task_id).status == "succeeded"


def test_empty_graph_reads_are_empty_not_errors(store, graph_id):
    assert store.list_nodes(graph_id) == []
    assert store.list_edges(graph_id) == []
    result = store.search(graph_id, "anything at all", 5, "edges", "rrf")
    assert result.edges == [] and result.nodes == []


def test_delete_graph_empties_it(store, graph_id):
    store.add_nodes(graph_id, [NewNode(name="Temporary Org", label="Organization")])
    assert store.list_nodes(graph_id)
    store.delete_graph(graph_id)
    assert store.list_nodes(graph_id) == []
    store.create_graph(graph_id, "recreated for teardown", "")  # teardown deletes it again


def test_episodes_are_processed_when_add_returns(store, graph_id):
    store.set_ontology(graph_id, ONTOLOGY)
    ids = store.add_episodes(graph_id, [TEXT])
    assert len(ids) == 1
    assert store.is_episode_processed(ids[0]) is True


@pytest.mark.skipif(not RUN_IT, reason="extraction needs the real Graphiti backend")
def test_graphiti_extracts_typed_entities_and_facts(monkeypatch):
    store = _graphiti_store(monkeypatch)
    gid = f"it_{uuid.uuid4().hex[:12]}"
    store.create_graph(gid, "extraction test", "")
    try:
        store.set_ontology(gid, ONTOLOGY)
        store.add_episodes(gid, [TEXT])
        nodes = store.list_nodes(gid)
        edges = store.list_edges(gid)
        names = " ".join(n.name for n in nodes).lower()
        assert "hannbeck" in names and "independent pharmacies association" in names
        assert any("Person" in n.labels for n in nodes)
        assert any("Organization" in n.labels for n in nodes)
        assert edges and all(e.fact for e in edges)
        # Callers put these straight into JSON, as they did with Zep's ISO strings.
        json.dumps([asdict(n) for n in nodes] + [asdict(e) for e in edges])
        hits = store.search(gid, "Who leads the Independent Pharmacies Association?", 5, "edges", "rrf")
        assert hits.edges, "search found no facts"
        hits_nodes = store.search(gid, "Hannbeck", 5, "nodes", "cross_encoder")  # served by RRF
        assert hits_nodes.nodes
        store.add_text(gid, "Agent Jo Bloggs posted: the caps are a disaster for rural pharmacies.")
        assert len(store.list_nodes(gid)) >= len(nodes)
    finally:
        store.delete_graph(gid)
    assert store.list_nodes(gid) == []
