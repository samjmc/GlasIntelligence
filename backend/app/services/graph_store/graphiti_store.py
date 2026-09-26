"""Graphiti (graphiti-core) on Neo4j: the self-hosted GraphStore (GRAPH_BACKEND=graphiti).

The design and every measured fact behind it are in the G0 section of
docs/superpowers/plans/2026-09-22-zep-to-graphiti-migration.md. In short:
- One process-wide instance (``shared()``): one Neo4j driver, one embedding model,
  one event loop (async_bridge). Graphiti is async-only; callers are sync.
- ``add_episodes`` ingests synchronously, one episode at a time, so the callers'
  poll loops see every episode as processed at once. Sequential ``add_episode``
  (not ``add_episode_bulk``) keeps Graphiti's fact invalidation.
- Graphiti stores no ontology, so ours is kept on a ``GlasGraph`` node per graph and
  passed on every add.
- The embedding model and dimension are recorded on a ``GlasStoreMeta`` node. A
  different model on an existing database fails loud: mixed vectors fail silently.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from typing import Any

# Both are read when graphiti_core is imported, so they must be set before that.
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from ...config import Config  # noqa: E402

os.environ.setdefault("EMBEDDING_DIM", str(Config.GRAPHITI_EMBED_DIM))

from graphiti_core import Graphiti  # noqa: E402
from graphiti_core.edges import EntityEdge  # noqa: E402
from graphiti_core.errors import GroupsEdgesNotFoundError, NodeNotFoundError  # noqa: E402
from graphiti_core.nodes import EntityNode, EpisodeType, Node  # noqa: E402
from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_RRF, NODE_HYBRID_SEARCH_RRF  # noqa: E402

from ...utils.logger import get_logger  # noqa: E402
from .async_bridge import AsyncBridge  # noqa: E402
from .base import (  # noqa: E402
    AddNodesResult,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
    NewNode,
    Reranker,
    SearchScope,
    TaskState,
)
from .graphiti_clients import LocalEmbedder, NoReranker, SchemaCheckedLLMClient, UsageCounter  # noqa: E402
from .ontology import build_graphiti_types  # noqa: E402

logger = get_logger("glas.graph_store.graphiti")

# Short reads and writes. Episode ingestion has its own, longer timeout (config).
_QUERY_TIMEOUT = 120


def _iso(value: Any) -> Any:
    # Zep returns ISO strings; Graphiti returns datetimes. Callers put these straight
    # into JSON (reports, the snapshot cache), so match Zep.
    return value.isoformat() if isinstance(value, datetime) else value


def _node(n: Any) -> GraphNode:
    return GraphNode(
        uuid=n.uuid,
        name=n.name,
        labels=list(n.labels or []),
        summary=n.summary,
        attributes=dict(n.attributes or {}),
        created_at=_iso(n.created_at),
    )


def _edge(e: Any) -> GraphEdge:
    return GraphEdge(
        uuid=e.uuid,
        name=e.name,
        fact=e.fact,
        source_node_uuid=e.source_node_uuid,
        target_node_uuid=e.target_node_uuid,
        attributes=dict(e.attributes or {}),
        created_at=_iso(e.created_at),
        valid_at=_iso(e.valid_at),
        invalid_at=_iso(e.invalid_at),
        expired_at=_iso(e.expired_at),
        episodes=list(e.episodes or []),
    )


class GraphitiGraphStore:
    backend = "graphiti"
    _shared: GraphitiGraphStore | None = None
    _shared_lock = threading.Lock()

    @classmethod
    def shared(cls) -> GraphitiGraphStore:
        with cls._shared_lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    def __init__(self) -> None:
        self.usage = UsageCounter()
        self.bridge = AsyncBridge()
        self.embedder = LocalEmbedder(Config.GRAPHITI_EMBED_MODEL)
        if self.embedder.dim != Config.GRAPHITI_EMBED_DIM:
            raise ValueError(
                f"GRAPHITI_EMBED_DIM={Config.GRAPHITI_EMBED_DIM} but {Config.GRAPHITI_EMBED_MODEL} "
                f"makes {self.embedder.dim}-dim vectors; set GRAPHITI_EMBED_DIM={self.embedder.dim}"
            )
        llm = SchemaCheckedLLMClient(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL,
            model=Config.GRAPHITI_LLM_MODEL or Config.LLM_MODEL_NAME,
            usage=self.usage,
        )
        self.graphiti: Graphiti = self.bridge.run(self._connect(llm), _QUERY_TIMEOUT)
        self._types: dict[str, tuple[Any, Any, Any]] = {}
        self._types_lock = threading.Lock()

    async def _connect(self, llm: SchemaCheckedLLMClient) -> Graphiti:
        # Built inside the bridge loop: the async Neo4j driver binds to its creating loop.
        g = Graphiti(
            Config.NEO4J_URI,
            Config.NEO4J_USER,
            Config.NEO4J_PASSWORD,
            llm_client=llm,
            embedder=self.embedder,
            cross_encoder=NoReranker(),
            max_coroutines=Config.GRAPHITI_MAX_COROUTINES,
        )
        await g.build_indices_and_constraints()
        records, _, _ = await g.driver.execute_query(
            "MERGE (m:GlasStoreMeta {key: 'embedder'}) "
            "ON CREATE SET m.model = $model, m.dim = $dim "
            "RETURN m.model AS model, m.dim AS dim",
            model=self.embedder.model_name,
            dim=self.embedder.dim,
        )
        stored = (records[0]["model"], records[0]["dim"])
        if stored != (self.embedder.model_name, self.embedder.dim):
            raise RuntimeError(
                f"This Neo4j database holds {stored[0]} ({stored[1]}-dim) embeddings, but the app is set to "
                f"{self.embedder.model_name} ({self.embedder.dim}-dim). Mixed vectors break search silently."
            )
        return g

    def _run(self, coro: Any, timeout: float = _QUERY_TIMEOUT) -> Any:
        return self.bridge.run(coro, timeout)

    @property
    def _driver(self) -> Any:
        return self.graphiti.driver

    # ---- chunking ----
    def preferred_chunking(self) -> tuple[int, int] | None:
        # Cost scales with LLM calls per episode, not bytes: larger chunks are cheaper.
        return Config.GRAPHITI_CHUNK_SIZE, Config.GRAPHITI_CHUNK_OVERLAP

    # ---- ontology ----
    def _types_for(self, graph_id: str) -> tuple[Any, Any, Any]:
        with self._types_lock:
            cached = self._types.get(graph_id)
        if cached is not None:
            return cached
        records, _, _ = self._run(
            self._driver.execute_query("MATCH (g:GlasGraph {graph_id: $gid}) RETURN g.ontology_json AS o", gid=graph_id)
        )
        raw = records[0]["o"] if records and records[0]["o"] else None
        types = build_graphiti_types(json.loads(raw) if raw else None)
        with self._types_lock:
            self._types[graph_id] = types
        return types

    # ---- GraphStore: writes ----
    def create_graph(self, graph_id: str, name: str, description: str) -> None:
        self._run(
            self._driver.execute_query(
                "MERGE (g:GlasGraph {graph_id: $gid}) "
                "SET g.name = $name, g.description = $description, g.created_at = datetime()",
                gid=graph_id,
                name=name,
                description=description,
            )
        )

    def set_ontology(self, graph_id: str, ontology: dict[str, Any]) -> None:
        types = build_graphiti_types(ontology)  # validate before storing
        self._run(
            self._driver.execute_query(
                "MERGE (g:GlasGraph {graph_id: $gid}) SET g.ontology_json = $o",
                gid=graph_id,
                o=json.dumps(ontology),
            )
        )
        with self._types_lock:
            self._types[graph_id] = types

    async def _add_one(self, graph_id: str, name: str, text: str, description: str) -> Any:
        entity_types, edge_types, edge_type_map = self._types_for_async_safe(graph_id)
        return await self.graphiti.add_episode(
            name=name,
            episode_body=text,
            source_description=description,
            reference_time=datetime.now(UTC),
            source=EpisodeType.text,
            group_id=graph_id,
            entity_types=entity_types or None,
            edge_types=edge_types or None,
            edge_type_map=edge_type_map or None,
        )

    def _types_for_async_safe(self, graph_id: str) -> tuple[Any, Any, Any]:
        # Called on the loop thread, so it must not block on the bridge: only the cache.
        with self._types_lock:
            return self._types.get(graph_id) or ({}, {}, {})

    def _ingest(self, graph_id: str, text: str, name: str, description: str) -> Any:
        self._types_for(graph_id)  # warm the cache from the calling thread
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                return self._run(self._add_one(graph_id, name, text, description), Config.GRAPHITI_EPISODE_TIMEOUT_SEC)
            except Exception as e:  # one retry, then fail loud
                last = e
                logger.warning(f"Graphiti episode {name} attempt {attempt} failed: {type(e).__name__}: {e}")
        raise RuntimeError(f"Graphiti could not ingest episode {name} into {graph_id}: {last}") from last

    def add_episodes(self, graph_id: str, texts: list[str]) -> list[str]:
        before = self.usage.snapshot()
        ids, nodes, edges = [], 0, 0
        for i, text in enumerate(texts):
            res = self._ingest(graph_id, text, f"{graph_id}:{datetime.now(UTC):%H%M%S%f}:{i}", "document text")
            ids.append(res.episode.uuid)
            nodes += len(res.nodes)
            edges += len(res.edges)
        after = self.usage.snapshot()
        logger.info(
            f"Graphiti ingested {len(texts)} episodes into {graph_id}: {nodes} nodes, {edges} edges; "
            f"LLM calls {after['calls'] - before['calls']}, prompt tokens {after['prompt_tokens'] - before['prompt_tokens']}, "
            f"completion tokens {after['completion_tokens'] - before['completion_tokens']}, "
            f"replies repaired {after['repaired'] - before['repaired']}"
        )
        if texts and nodes == 0 and edges == 0:
            logger.warning(f"Graphiti extracted nothing from {len(texts)} episodes in {graph_id}")
        return ids

    def is_episode_processed(self, episode_id: str) -> bool:
        return True  # add_episodes returns only after extraction finished

    def add_nodes(self, graph_id: str, nodes: list[NewNode]) -> AddNodesResult:
        async def _save_all() -> int:
            saved = 0
            for n in nodes:
                labels = ["Entity"] if n.label == "Entity" else ["Entity", n.label]
                node = EntityNode(
                    name=n.name,
                    group_id=graph_id,
                    labels=labels,
                    summary=n.summary or "",
                    attributes=dict(n.attributes or {}),
                )
                await node.generate_name_embedding(self.embedder)
                await node.save(self._driver)
                saved += 1
            return saved

        return AddNodesResult(accepted=self._run(_save_all()))

    def get_task_status(self, task_id: str) -> TaskState:
        return TaskState(status="succeeded")  # add_nodes returns no task id

    def add_text(self, graph_id: str, text: str) -> None:
        self._ingest(graph_id, text, f"{graph_id}:memory:{datetime.now(UTC):%H%M%S%f}", "simulation activity")

    # ---- GraphStore: reads ----
    def list_nodes(self, graph_id: str, max_items: int = 2000) -> list[GraphNode]:
        nodes = self._run(EntityNode.get_by_group_ids(self._driver, [graph_id], limit=max_items))
        return [_node(n) for n in nodes]

    def list_edges(self, graph_id: str) -> list[GraphEdge]:
        try:
            edges = self._run(EntityEdge.get_by_group_ids(self._driver, [graph_id]))
        except GroupsEdgesNotFoundError:
            return []
        return [_edge(e) for e in edges]

    def get_node(self, node_uuid: str) -> GraphNode | None:
        try:
            return _node(self._run(EntityNode.get_by_uuid(self._driver, node_uuid)))
        except NodeNotFoundError:
            return None

    def get_node_edges(self, node_uuid: str) -> list[GraphEdge]:
        return [_edge(e) for e in self._run(EntityEdge.get_by_node_uuid(self._driver, node_uuid))]

    def search(
        self, graph_id: str, query: str, limit: int, scope: SearchScope, reranker: Reranker
    ) -> GraphSearchResult:
        # "cross_encoder" is served by RRF too: the local BGE reranker is a 2.2 GB download.
        recipe = NODE_HYBRID_SEARCH_RRF if scope == "nodes" else EDGE_HYBRID_SEARCH_RRF
        res = self._run(
            self.graphiti.search_(query, config=recipe.model_copy(update={"limit": limit}), group_ids=[graph_id])
        )
        return GraphSearchResult(edges=[_edge(e) for e in res.edges], nodes=[_node(n) for n in res.nodes])

    def delete_graph(self, graph_id: str) -> None:
        self._run(Node.delete_by_group_id(self._driver, graph_id))
        self._run(self._driver.execute_query("MATCH (g:GlasGraph {graph_id: $gid}) DELETE g", gid=graph_id))
        with self._types_lock:
            self._types.pop(graph_id, None)
