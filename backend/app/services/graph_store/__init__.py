"""Knowledge-graph storage behind one interface.

``Config.GRAPH_BACKEND`` chooses the store:
- ``zep`` (default): Zep Cloud, the only production backend today.
- ``fake``: in memory, for tests. It makes no network calls.

Step G1 of docs/superpowers/plans/2026-09-22-zep-to-graphiti-migration.md.
G2 adds ``graphiti``.
"""

from __future__ import annotations

from ...config import Config
from .base import (
    AddNodesResult,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
    GraphStore,
    NewNode,
    TaskState,
)

__all__ = [
    "AddNodesResult",
    "GraphEdge",
    "GraphNode",
    "GraphSearchResult",
    "GraphStore",
    "NewNode",
    "TaskState",
    "get_graph_store",
    "graph_store_available",
    "graph_store_unavailable_reason",
]

_BACKENDS = ("zep", "fake")


def _backend() -> str:
    backend = (Config.GRAPH_BACKEND or "zep").strip().lower()
    if backend not in _BACKENDS:
        raise ValueError(f"Unknown GRAPH_BACKEND {backend!r}; expected one of {', '.join(_BACKENDS)}")
    return backend


def graph_store_available() -> bool:
    """True when get_graph_store() can build a store (the backend's credentials are set)."""
    return _backend() != "zep" or bool(Config.ZEP_API_KEY)


def graph_store_unavailable_reason() -> str:
    return "ZEP_API_KEY not configured"


def get_graph_store(api_key: str | None = None) -> GraphStore:
    """Build the configured store. ``api_key`` overrides Config.ZEP_API_KEY for the Zep backend."""
    backend = _backend()
    if backend == "fake":
        from .fake_store import FakeGraphStore

        return FakeGraphStore.shared()
    from .zep_store import ZepGraphStore

    return ZepGraphStore(api_key or Config.ZEP_API_KEY)
