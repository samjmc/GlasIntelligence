"""
Zep entity reading and filtering service
Reads nodes from a Zep graph and filters those matching predefined entity types

Note: get_all_nodes uses zep_paging.fetch_all_nodes, which enforces a default
max node cap (2000; see backend/app/utils/zep_paging.py, _MAX_NODES). Graphs
larger than that produce a truncated node list; callers must tolerate incomplete
graph views when interpreting context.
"""

import time
from typing import Any, TypeVar
from collections.abc import Callable
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .graph_snapshot_cache import try_get_lists_for_entity_reader

logger = get_logger("glas.zep_entity_reader")

# For generic return types
T = TypeVar("T")


@dataclass
class EntityNode:
    """Entity node data structure"""

    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict[str, Any]
    # Related edge information
    related_edges: list[dict[str, Any]] = field(default_factory=list)
    # Related node information
    related_nodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityNode":
        labels = data.get("labels", [])
        if not isinstance(labels, list):
            labels = []
        attributes = data.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}
        related_edges = data.get("related_edges", [])
        if not isinstance(related_edges, list):
            related_edges = []
        related_nodes = data.get("related_nodes", [])
        if not isinstance(related_nodes, list):
            related_nodes = []
        return cls(
            uuid=data.get("uuid", ""),
            name=data.get("name", ""),
            labels=labels,
            summary=data.get("summary", ""),
            attributes=attributes,
            related_edges=related_edges,
            related_nodes=related_nodes,
        )

    def get_entity_type(self) -> str | None:
        """Get entity type (excluding the default Entity label)"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Filtered entity collection"""

    entities: list[EntityNode]
    entity_types: set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Zep entity reading and filtering service

    Main features:
    1. Read all nodes from a Zep graph
    2. Filter nodes matching predefined entity types (nodes with labels beyond just Entity)
    3. Retrieve related edges and associated node information for each entity
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY not configured")

        self.client = Zep(api_key=self.api_key)

    def _call_with_retry(
        self, func: Callable[[], T], operation_name: str, max_retries: int = 3, initial_delay: float = 2.0
    ) -> T:
        """
        Zep API call with retry mechanism

        Args:
            func: Function to execute (parameterless lambda or callable)
            operation_name: Operation name for logging
            max_retries: Maximum number of retries (default 3)
            initial_delay: Initial delay in seconds

        Returns:
            API call result
        """
        last_exception = None
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} attempt {attempt + 1} failed: {str(e)[:100]}, "
                        f"retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= 2  # exponential backoff
                else:
                    logger.error(f"Zep {operation_name} still failed after {max_retries} attempts: {str(e)}")

        raise last_exception

    def get_all_nodes(self, graph_id: str) -> list[dict[str, Any]]:
        """
        Get all nodes from the graph (paginated)

        Args:
            graph_id: Graph ID

        Returns:
            List of nodes
        """
        if Config.GRAPH_SNAPSHOT_CACHE_ENABLED:
            cached = try_get_lists_for_entity_reader(graph_id)
            if cached:
                nodes_data, _ = cached
                logger.info(
                    "Using snapshot cache for nodes (graph_id=%s, %s nodes)",
                    graph_id,
                    len(nodes_data),
                )
                return nodes_data

        logger.info(f"Fetching all nodes for graph {graph_id}...")
        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append(
                {
                    "uuid": getattr(node, "uuid_", None) or getattr(node, "uuid", ""),
                    "name": node.name or "",
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                    "attributes": node.attributes or {},
                }
            )

        logger.info(f"Fetched {len(nodes_data)} nodes")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> list[dict[str, Any]]:
        """
        Get all edges from the graph (paginated)

        Args:
            graph_id: Graph ID

        Returns:
            List of edges
        """
        if Config.GRAPH_SNAPSHOT_CACHE_ENABLED:
            cached = try_get_lists_for_entity_reader(graph_id)
            if cached:
                _, edges_data = cached
                logger.info(
                    "Using snapshot cache for edges (graph_id=%s, %s edges)",
                    graph_id,
                    len(edges_data),
                )
                return edges_data

        logger.info(f"Fetching all edges for graph {graph_id}...")
        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append(
                {
                    "uuid": getattr(edge, "uuid_", None) or getattr(edge, "uuid", ""),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                }
            )

        logger.info(f"Fetched {len(edges_data)} edges")
        return edges_data

    def get_node_edges(self, node_uuid: str) -> list[dict[str, Any]]:
        """
        Get all related edges for a given node (with retry mechanism)

        Args:
            node_uuid: Node UUID

        Returns:
            List of edges
        """
        try:
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"get_node_edges(node={node_uuid[:8]}...)",
            )

            edges_data = []
            for edge in edges:
                edges_data.append(
                    {
                        "uuid": getattr(edge, "uuid_", None) or getattr(edge, "uuid", ""),
                        "name": edge.name or "",
                        "fact": edge.fact or "",
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                        "attributes": edge.attributes or {},
                    }
                )

            return edges_data
        except Exception as e:
            logger.error(f"Failed to get edges for node {node_uuid}: {str(e)}")
            raise

    def filter_defined_entities(
        self, graph_id: str, defined_entity_types: list[str] | None = None, enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Filter nodes matching predefined entity types

        Filtering logic:
        - If a node's labels only contain "Entity", it doesn't match our predefined types; skip it
        - If a node's labels include labels beyond "Entity" and "Node", it matches a predefined type; keep it

        Args:
            graph_id: Graph ID
            defined_entity_types: List of predefined entity types (optional; if provided, only these types are kept)
            enrich_with_edges: Whether to fetch related edge information for each entity

        Returns:
            FilteredEntities: Filtered entity collection
        """
        logger.info(f"Starting entity filtering for graph {graph_id}...")

        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        node_map: dict[str, dict[str, Any]] = {}
        uuid_counts: dict[str, int] = {}
        for n in all_nodes:
            uid = n.get("uuid", "")
            uuid_counts[uid] = uuid_counts.get(uid, 0) + 1
            node_map[uid] = n
        if any(count > 1 for count in uuid_counts.values()):
            logger.warning(
                "Duplicate node UUIDs detected: %s. Kept last occurrence.",
                [u for u, c in uuid_counts.items() if c > 1],
            )

        filtered_entities = []
        entity_types_found = set()

        for node in all_nodes:
            labels = node.get("labels", [])

            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]

            if not custom_labels:
                continue

            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = sorted(matching_labels, key=lambda x: list(defined_entity_types).index(x))[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "outgoing",
                                "edge_name": edge["name"],
                                "fact": edge["fact"],
                                "target_node_uuid": edge["target_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "incoming",
                                "edge_name": edge["name"],
                                "fact": edge["fact"],
                                "source_node_uuid": edge["source_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append(
                            {
                                "uuid": related_node["uuid"],
                                "name": related_node["name"],
                                "labels": related_node["labels"],
                                "summary": related_node.get("summary", ""),
                            }
                        )

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(
            f"Filtering complete: total nodes {total_count}, matching {len(filtered_entities)}, "
            f"entity types: {entity_types_found}"
        )

        filtered_entities = self._deduplicate_entities(filtered_entities)

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_untyped_entities(
        self,
        graph_id: str,
        min_connections: int = 3,
        exclude_names: set[str] | None = None,
    ) -> list[EntityNode]:
        """Return untyped nodes (labels only 'Entity'/'Node') with enough graph connections.

        These are nodes that Zep did not classify into any custom type but are still
        well-connected enough to be valuable as representative voice agents.

        Args:
            graph_id: Zep graph ID
            min_connections: Minimum number of edges to qualify (default 3)
            exclude_names: Optional set of entity names (lowered) to skip (e.g. already-typed ones)
        """
        all_nodes = self.get_all_nodes(graph_id)
        all_edges = self.get_all_edges(graph_id)
        node_map: dict[str, dict[str, Any]] = {}
        uuid_counts: dict[str, int] = {}
        for n in all_nodes:
            uid = n.get("uuid", "")
            uuid_counts[uid] = uuid_counts.get(uid, 0) + 1
            node_map[uid] = n
        if any(count > 1 for count in uuid_counts.values()):
            logger.warning(
                "Duplicate node UUIDs detected: %s. Kept last occurrence.",
                [u for u, c in uuid_counts.items() if c > 1],
            )
        exclude = exclude_names or set()

        edge_count: dict[str, int] = {}
        for edge in all_edges:
            edge_count[edge["source_node_uuid"]] = edge_count.get(edge["source_node_uuid"], 0) + 1
            edge_count[edge["target_node_uuid"]] = edge_count.get(edge["target_node_uuid"], 0) + 1

        untyped: list[EntityNode] = []
        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ("Entity", "Node")]
            if custom_labels:
                continue
            if node["name"].strip().lower() in exclude:
                continue
            if edge_count.get(node["uuid"], 0) < min_connections:
                continue

            related_edges = []
            related_node_uuids: set[str] = set()
            for edge in all_edges:
                if edge["source_node_uuid"] == node["uuid"]:
                    related_edges.append(
                        {
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["target_node_uuid"])
                elif edge["target_node_uuid"] == node["uuid"]:
                    related_edges.append(
                        {
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["source_node_uuid"])

            related_nodes = []
            for rid in related_node_uuids:
                if rid in node_map:
                    rn = node_map[rid]
                    related_nodes.append(
                        {
                            "uuid": rn["uuid"],
                            "name": rn["name"],
                            "labels": rn["labels"],
                            "summary": rn.get("summary", ""),
                        }
                    )

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            untyped.append(entity)

        untyped.sort(key=lambda e: len(e.related_edges), reverse=True)

        logger.info(
            f"Untyped entities with >={min_connections} connections: {len(untyped)} "
            f"(out of {len(all_nodes)} total nodes)"
        )
        return untyped

    @staticmethod
    def _deduplicate_entities(entities: list) -> list:
        """
        Deduplicate entities by normalised name to prevent near-duplicates
        like 'GP' vs 'GPs', 'PDA' vs 'PHARMACISTS DEFENCE ASSOCIATION'.
        Keeps the entity with the longest summary (most context).
        """
        import re

        def normalise(name: str) -> str:
            n = name.strip().lower()
            n = re.sub(r"[''`]s$", "", n)
            if n.endswith("s") and not n.endswith("ss"):
                n = n[:-1]
            n = re.sub(r"[^a-z0-9]", "", n)
            return n

        KNOWN_ALIASES = {
            "pharmacistsdefenceassociation": "pda",
            "pharmacistdefenceassociation": "pda",
            "communitypharmacyengland": "cpe",
            "nhsbusinessservicesauthority": "nhsbsa",
            "departmentofhealthandsocialcare": "dhsc",
            "nationalhealthservice": "nhs",
        }

        # Build dynamic acronym map: maps full-name keys to their acronym keys
        acronym_keys = {}
        full_name_keys = {}
        for entity in entities:
            raw = (entity.name or "").strip()
            key = normalise(raw)
            if raw.isupper() and 2 <= len(raw) <= 8 and raw.isalpha():
                acronym_keys[key] = raw
            else:
                full_name_keys[key] = raw

        dynamic_aliases: dict[str, str] = {}
        for full_key, full_raw in full_name_keys.items():
            words = full_raw.strip().split()
            initials = "".join(w[0] for w in words if w and w[0].isupper())
            if len(initials) >= 2:
                initials_key = normalise(initials)
                if initials_key in acronym_keys:
                    dynamic_aliases[full_key] = initials_key

        seen = {}
        for entity in entities:
            key = normalise((entity.name or "").strip())
            key = KNOWN_ALIASES.get(key, key)
            key = dynamic_aliases.get(key, key)

            if key in seen:
                existing = seen[key]
                if len(entity.summary or "") > len(existing.summary or ""):
                    seen[key] = entity
            else:
                seen[key] = entity

        deduped = list(seen.values())
        if len(deduped) < len(entities):
            logger.info(
                f"Entity deduplication: {len(entities)} -> {len(deduped)} "
                f"(removed {len(entities) - len(deduped)} duplicates)"
            )
        return deduped

    def get_entity_with_context(self, graph_id: str, entity_uuid: str) -> EntityNode | None:
        """
        Get a single entity with full context (edges and associated nodes, with retry mechanism)

        Fetch entity context including full node map. Note: calls get_all_nodes(graph_id) for every entity.
        For large graphs (>2000 nodes), this is truncated by fetch_all_nodes cap; consider caching at orchestration layer.

        Args:
            graph_id: Graph ID
            entity_uuid: Entity UUID

        Returns:
            EntityNode or None
        """
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"get_node_detail(uuid={entity_uuid[:8]}...)",
            )

            if not node:
                return None

            edges = self.get_node_edges(entity_uuid)

            all_nodes = self.get_all_nodes(graph_id)
            node_map: dict[str, dict[str, Any]] = {}
            uuid_counts: dict[str, int] = {}
            for n in all_nodes:
                uid = n.get("uuid", "")
                uuid_counts[uid] = uuid_counts.get(uid, 0) + 1
                node_map[uid] = n
            if any(count > 1 for count in uuid_counts.values()):
                logger.warning(
                    "Duplicate node UUIDs detected: %s. Kept last occurrence.",
                    [u for u, c in uuid_counts.items() if c > 1],
                )

            related_edges = []
            related_node_uuids = set()

            for edge in edges:
                source = edge["source_node_uuid"]
                target = edge["target_node_uuid"]
                if source == entity_uuid:
                    related_edges.append(
                        {
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["target_node_uuid"])
                elif target == entity_uuid:
                    related_edges.append(
                        {
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["source_node_uuid"])
                else:
                    logger.debug(
                        "Edge %s incident to neither source nor target of entity %s. Skipping.",
                        edge.get("uuid", "?"),
                        entity_uuid,
                    )

            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append(
                        {
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        }
                    )

            return EntityNode(
                uuid=getattr(node, "uuid_", None) or getattr(node, "uuid", ""),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )

        except Exception as e:
            logger.error(f"Failed to get entity {entity_uuid}: {str(e)}")
            return None

    def get_entities_by_type(self, graph_id: str, entity_type: str, enrich_with_edges: bool = True) -> list[EntityNode]:
        """
        Get all entities of a given type

        Args:
            graph_id: Graph ID
            entity_type: Entity type (e.g. "Student", "PublicFigure")
            enrich_with_edges: Whether to fetch related edge information

        Returns:
            List of entities
        """
        result = self.filter_defined_entities(
            graph_id=graph_id, defined_entity_types=[entity_type], enrich_with_edges=enrich_with_edges
        )
        return result.entities
