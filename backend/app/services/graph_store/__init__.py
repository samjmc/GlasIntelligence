"""Knowledge-graph storage behind one interface.

``Config.GRAPH_BACKEND`` chooses the store:
- ``zep`` (default): Zep Cloud (metered; free plan is 10k credits a month).
- ``graphiti``: self-hosted Graphiti on Neo4j, with DeepSeek extraction and a local
  embedder. No credits, pay only LLM tokens (G0: about $0.15 for a 58k-char dossier).
- ``fake``: in memory, for tests. It makes no network calls.

See docs/superpowers/plans/2026-09-22-zep-to-graphiti-migration.md.
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

_BACKENDS = ("zep", "graphiti", "fake")


def _backend() -> str:
    backend = (Config.GRAPH_BACKEND or "zep").strip().lower()
    if backend not in _BACKENDS:
        raise ValueError(f"Unknown GRAPH_BACKEND {backend!r}; expected one of {', '.join(_BACKENDS)}")
    return backend


def _missing_settings() -> list[str]:
    backend = _backend()
    if backend == "zep":
        return [] if Config.ZEP_API_KEY else ["ZEP_API_KEY"]
    if backend == "graphiti":
        return [k for k in ("NEO4J_URI", "NEO4J_PASSWORD", "LLM_API_KEY") if not getattr(Config, k, None)]
    return []


def graph_store_available() -> bool:
    """True when get_graph_store() can build a store (the backend's settings are present)."""
    return not _missing_settings()


def graph_store_unavailable_reason() -> str:
    missing = _missing_settings()
    if missing == ["ZEP_API_KEY"]:
        return "ZEP_API_KEY not configured"  # the historical API error text
    return f"{', '.join(missing)} not configured for GRAPH_BACKEND={_backend()}"


def get_graph_store(api_key: str | None = None) -> GraphStore:
    """Build (or, for graphiti and fake, return the shared) configured store.

    ``api_key`` overrides Config.ZEP_API_KEY for the Zep backend and is ignored otherwise.
    """
    backend = _backend()
    if backend == "fake":
        from .fake_store import FakeGraphStore

        return FakeGraphStore.shared()
    if backend == "graphiti":
        missing = _missing_settings()
        if missing:
            raise ValueError(graph_store_unavailable_reason())
        from .graphiti_store import GraphitiGraphStore  # heavy: loads graphiti, Neo4j, torch

        return GraphitiGraphStore.shared()
    from .zep_store import ZepGraphStore

    return ZepGraphStore(api_key or Config.ZEP_API_KEY)
