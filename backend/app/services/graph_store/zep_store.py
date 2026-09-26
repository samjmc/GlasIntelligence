"""Zep Cloud implementation of GraphStore.

Every SDK call here was moved unchanged from the service that made it before G1
(graph_builder, graph_enrichment_service, zep_entity_reader, zep_tools,
oasis_profile_generator, zep_graph_memory_updater). Retries, polling and error
handling stay in those callers.
"""

from __future__ import annotations

from typing import Any, Optional

from zep_cloud import AddNodeItem, EntityEdgeSourceTarget, EpisodeData
from zep_cloud.client import Zep

from ...utils.zep_paging import fetch_all_edges, fetch_all_nodes
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


def _uuid(raw: Any) -> Any:
    return getattr(raw, "uuid_", None) or getattr(raw, "uuid", None)


def to_node(raw: Any) -> GraphNode:
    # Values pass through as Zep returned them (including None): callers apply
    # their own `or ""` / `or []` defaults, exactly as they did on SDK objects.
    return GraphNode(
        uuid=_uuid(raw),
        name=getattr(raw, "name", None),
        labels=getattr(raw, "labels", None),
        summary=getattr(raw, "summary", None),
        attributes=getattr(raw, "attributes", None),
        created_at=getattr(raw, "created_at", None),
    )


def to_edge(raw: Any) -> GraphEdge:
    return GraphEdge(
        uuid=_uuid(raw),
        name=getattr(raw, "name", None),
        fact=getattr(raw, "fact", None),
        source_node_uuid=getattr(raw, "source_node_uuid", None),
        target_node_uuid=getattr(raw, "target_node_uuid", None),
        attributes=getattr(raw, "attributes", None),
        created_at=getattr(raw, "created_at", None),
        valid_at=getattr(raw, "valid_at", None),
        invalid_at=getattr(raw, "invalid_at", None),
        expired_at=getattr(raw, "expired_at", None),
        episodes=getattr(raw, "episodes", None) or getattr(raw, "episode_ids", None),
        fact_type=getattr(raw, "fact_type", None),
    )


class ZepGraphStore:
    backend = "zep"

    def __init__(self, api_key: str | None):
        if not api_key:
            raise ValueError("ZEP_API_KEY is not configured")
        self.client = Zep(api_key=api_key)

    def preferred_chunking(self) -> tuple[int, int] | None:
        return None  # the project's own chunking (Config.DEFAULT_CHUNK_SIZE), as before

    def create_graph(self, graph_id: str, name: str, description: str) -> None:
        self.client.graph.create(graph_id=graph_id, name=name, description=description)

    def set_ontology(self, graph_id: str, ontology: dict[str, Any]) -> None:
        import warnings

        from pydantic import Field
        from zep_cloud.external_clients.ontology import EdgeModel, EntityModel, EntityText

        # Suppress Pydantic v2 warnings about Field(default=None)
        # Required by Zep SDK usage; safe to ignore
        warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

        # Zep reserved names that cannot be used as attribute names
        RESERVED_NAMES = {"uuid", "name", "group_id", "name_embedding", "summary", "created_at"}

        def safe_attr_name(attr_name: str) -> str:
            """Convert reserved names to safe alternatives"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name

        # Dynamically create entity types
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")

            # Build attribute dict and type annotations (Pydantic v2 required)
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                # Keep typing.Optional: Zep's ontology code inspects these at runtime.
                annotations[attr_name] = Optional[EntityText]  # noqa: UP045

            attrs["__annotations__"] = annotations

            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class

        # Dynamically create edge types
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")

            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # noqa: UP045 - see above

            attrs["__annotations__"] = annotations

            class_name = "".join(word.capitalize() for word in name.split("_"))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description

            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(source=st.get("source", "Entity"), target=st.get("target", "Entity"))
                )

            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)

        # Call Zep API to set ontology
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )

    def add_episodes(self, graph_id: str, texts: list[str]) -> list[str]:
        episodes = [EpisodeData(data=text, type="text") for text in texts]
        batch_result = self.client.graph.add_batch(graph_id=graph_id, episodes=episodes)
        episode_uuids = []
        if batch_result and isinstance(batch_result, list):
            for ep in batch_result:
                ep_uuid = _uuid(ep)
                if ep_uuid:
                    episode_uuids.append(ep_uuid)
        return episode_uuids

    def is_episode_processed(self, episode_id: str) -> bool:
        episode = self.client.graph.episode.get(uuid_=episode_id)
        return bool(getattr(episode, "processed", False))

    def add_nodes(self, graph_id: str, nodes: list[NewNode]) -> AddNodesResult:
        items = [AddNodeItem(name=n.name, summary=n.summary, label=n.label, attributes=n.attributes) for n in nodes]
        resp = self.client.graph.add_nodes(graph_id=graph_id, nodes=items)
        if not resp:
            return AddNodesResult(accepted=0)
        return AddNodesResult(accepted=len(resp.nodes or []), task_id=getattr(resp, "task_id", None))

    def get_task_status(self, task_id: str) -> TaskState:
        task = self.client.task.get(task_id=task_id)
        return TaskState(status=getattr(task, "status", None), error=getattr(task, "error", None))

    def add_text(self, graph_id: str, text: str) -> None:
        self.client.graph.add(graph_id=graph_id, type="text", data=text)

    def list_nodes(self, graph_id: str, max_items: int = 2000) -> list[GraphNode]:
        return [to_node(n) for n in fetch_all_nodes(self.client, graph_id, max_items=max_items)]

    def list_edges(self, graph_id: str) -> list[GraphEdge]:
        return [to_edge(e) for e in fetch_all_edges(self.client, graph_id)]

    def get_node(self, node_uuid: str) -> GraphNode | None:
        node = self.client.graph.node.get(uuid_=node_uuid)
        return to_node(node) if node else None

    def get_node_edges(self, node_uuid: str) -> list[GraphEdge]:
        return [to_edge(e) for e in (self.client.graph.node.get_entity_edges(node_uuid=node_uuid) or [])]

    def search(
        self, graph_id: str, query: str, limit: int, scope: SearchScope, reranker: Reranker
    ) -> GraphSearchResult:
        res = self.client.graph.search(graph_id=graph_id, query=query, limit=limit, scope=scope, reranker=reranker)
        return GraphSearchResult(
            edges=[to_edge(e) for e in (getattr(res, "edges", None) or [])],
            nodes=[to_node(n) for n in (getattr(res, "nodes", None) or [])],
        )

    def delete_graph(self, graph_id: str) -> None:
        self.client.graph.delete(graph_id=graph_id)
