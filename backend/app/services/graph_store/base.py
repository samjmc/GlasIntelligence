"""The graph-store interface and the value types every backend returns.

Callers read results by attribute, the way they read Zep SDK objects before
G1. So the value types keep Zep's field names, and expose the id as both
``uuid`` and ``uuid_``.

The operations are small on purpose. Waiting for ingestion (episodes, add_nodes
tasks) stays in the callers, which poll ``is_episode_processed`` and
``get_task_status``. A backend that ingests synchronously returns True / a
finished status at once, so the same caller loops end immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

SearchScope = Literal["edges", "nodes"]
Reranker = Literal["rrf", "cross_encoder"]


@dataclass
class GraphNode:
    uuid: str
    name: str = ""
    labels: list[str] = field(default_factory=list)
    summary: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: Any = None

    @property
    def uuid_(self) -> str:
        return self.uuid


@dataclass
class GraphEdge:
    uuid: str
    name: str = ""
    fact: str = ""
    source_node_uuid: str = ""
    target_node_uuid: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: Any = None
    valid_at: Any = None
    invalid_at: Any = None
    expired_at: Any = None
    episodes: list[str] | None = None
    fact_type: str | None = None

    @property
    def uuid_(self) -> str:
        return self.uuid


@dataclass
class GraphSearchResult:
    edges: list[GraphEdge] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)


@dataclass
class NewNode:
    """A node to add directly, without extraction from text."""

    name: str
    label: str
    summary: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass
class AddNodesResult:
    accepted: int
    task_id: str | None = None


@dataclass
class TaskState:
    """``status`` is ``"succeeded"``, ``"failed"``, another backend value, or None."""

    status: str | None
    error: Any = None


class GraphStore(Protocol):
    backend: str

    def preferred_chunking(self) -> tuple[int, int] | None:
        """(chunk_size, overlap) in characters this backend builds best with, or None for the caller's own."""
        ...

    def create_graph(self, graph_id: str, name: str, description: str) -> None: ...

    def set_ontology(self, graph_id: str, ontology: dict[str, Any]) -> None: ...

    def add_episodes(self, graph_id: str, texts: list[str]) -> list[str]:
        """Queue text episodes for extraction. Returns the episode ids it can track."""
        ...

    def is_episode_processed(self, episode_id: str) -> bool: ...

    def add_nodes(self, graph_id: str, nodes: list[NewNode]) -> AddNodesResult: ...

    def get_task_status(self, task_id: str) -> TaskState: ...

    def add_text(self, graph_id: str, text: str) -> None:
        """Add one text episode (live graph memory). Fire and forget."""
        ...

    def list_nodes(self, graph_id: str, max_items: int = 2000) -> list[GraphNode]: ...

    def list_edges(self, graph_id: str) -> list[GraphEdge]: ...

    def get_node(self, node_uuid: str) -> GraphNode | None: ...

    def get_node_edges(self, node_uuid: str) -> list[GraphEdge]: ...

    def search(
        self, graph_id: str, query: str, limit: int, scope: SearchScope, reranker: Reranker
    ) -> GraphSearchResult: ...

    def delete_graph(self, graph_id: str) -> None: ...
