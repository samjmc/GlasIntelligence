"""In-memory GraphStore for tests (GRAPH_BACKEND=fake). Makes no network calls.

It does no extraction: episodes are stored as text and count as processed at
once. Tests put nodes and edges in with ``add_nodes`` or ``seed_node`` /
``seed_edge``, and read what was written through ``episodes`` / ``texts``.
"""

from __future__ import annotations

import itertools
from typing import Any

from .base import (
    AddNodesResult,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
    NewNode,
    Reranker,
    SearchScope,
    TaskState,
)


class FakeGraphStore:
    backend = "fake"
    _shared: FakeGraphStore | None = None

    def __init__(self) -> None:
        self.graphs: dict[str, dict[str, Any]] = {}
        self.ontologies: dict[str, dict[str, Any]] = {}
        self.nodes: dict[str, list[GraphNode]] = {}
        self.edges: dict[str, list[GraphEdge]] = {}
        self.episodes: dict[str, list[str]] = {}  # graph_id -> texts from add_episodes
        self.texts: dict[str, list[str]] = {}  # graph_id -> texts from add_text
        self._ids = itertools.count(1)

    @classmethod
    def shared(cls) -> FakeGraphStore:
        """The one instance get_graph_store() returns, so services in a test share data."""
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        cls._shared = None

    def _id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    # ---- test helpers ----
    def seed_node(self, graph_id: str, name: str, labels: list[str] | None = None, **kw: Any) -> GraphNode:
        node = GraphNode(uuid=kw.pop("uuid", None) or self._id("n"), name=name, labels=labels or ["Entity"], **kw)
        self.nodes.setdefault(graph_id, []).append(node)
        return node

    def seed_edge(self, graph_id: str, source: GraphNode, target: GraphNode, fact: str, **kw: Any) -> GraphEdge:
        edge = GraphEdge(
            uuid=kw.pop("uuid", None) or self._id("e"),
            fact=fact,
            source_node_uuid=source.uuid,
            target_node_uuid=target.uuid,
            **kw,
        )
        self.edges.setdefault(graph_id, []).append(edge)
        return edge

    # ---- GraphStore ----
    def preferred_chunking(self) -> tuple[int, int] | None:
        return None

    def create_graph(self, graph_id: str, name: str, description: str) -> None:
        self.graphs[graph_id] = {"name": name, "description": description}

    def set_ontology(self, graph_id: str, ontology: dict[str, Any]) -> None:
        self.ontologies[graph_id] = ontology

    def add_episodes(self, graph_id: str, texts: list[str]) -> list[str]:
        self.episodes.setdefault(graph_id, []).extend(texts)
        return [self._id("ep") for _ in texts]

    def is_episode_processed(self, episode_id: str) -> bool:
        return True

    def add_nodes(self, graph_id: str, nodes: list[NewNode]) -> AddNodesResult:
        for n in nodes:
            self.seed_node(
                graph_id, n.name, ["Entity", n.label], summary=n.summary or "", attributes=dict(n.attributes or {})
            )
        return AddNodesResult(accepted=len(nodes))

    def get_task_status(self, task_id: str) -> TaskState:
        return TaskState(status="succeeded")

    def add_text(self, graph_id: str, text: str) -> None:
        self.texts.setdefault(graph_id, []).append(text)

    def list_nodes(self, graph_id: str, max_items: int = 2000) -> list[GraphNode]:
        return list(self.nodes.get(graph_id, []))[:max_items]

    def list_edges(self, graph_id: str) -> list[GraphEdge]:
        return list(self.edges.get(graph_id, []))

    def get_node(self, node_uuid: str) -> GraphNode | None:
        return next((n for ns in self.nodes.values() for n in ns if n.uuid == node_uuid), None)

    def get_node_edges(self, node_uuid: str) -> list[GraphEdge]:
        return [e for es in self.edges.values() for e in es if node_uuid in (e.source_node_uuid, e.target_node_uuid)]

    def search(
        self, graph_id: str, query: str, limit: int, scope: SearchScope, reranker: Reranker
    ) -> GraphSearchResult:
        words = {w for w in query.lower().split() if len(w) > 2}

        def hit(text: str | None) -> bool:
            return bool(text) and any(w in text.lower() for w in words)

        if scope == "nodes":
            nodes = [n for n in self.nodes.get(graph_id, []) if hit(n.name) or hit(n.summary)]
            return GraphSearchResult(nodes=nodes[:limit])
        edges = [e for e in self.edges.get(graph_id, []) if hit(e.fact) or hit(e.name)]
        return GraphSearchResult(edges=edges[:limit])

    def delete_graph(self, graph_id: str) -> None:
        for d in (self.graphs, self.ontologies, self.nodes, self.edges, self.episodes, self.texts):
            d.pop(graph_id, None)
