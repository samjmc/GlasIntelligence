"""
Graph Building Service
Interface 2: Build Standalone Graph using Zep API
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .graph_store import GraphStore, get_graph_store


@dataclass
class GraphInfo:
    """Graph information"""

    graph_id: str
    node_count: int
    edge_count: int
    entity_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Graph Building Service
    Responsible for calling Zep API to build knowledge graphs
    """

    def __init__(self, api_key: str | None = None, store: GraphStore | None = None):
        self.store = store or get_graph_store(api_key)

    def create_graph(self, name: str) -> str:
        """Create a Zep graph"""
        graph_id = f"glas_{uuid.uuid4().hex[:16]}"

        self.store.create_graph(graph_id=graph_id, name=name, description="Glas Intelligence Simulation Graph")

        return graph_id

    def set_ontology(self, graph_id: str, ontology: dict[str, Any]):
        """Set the graph ontology definition"""
        self.store.set_ontology(graph_id, ontology)

    def add_text_batches(
        self, graph_id: str, chunks: list[str], batch_size: int = 3, progress_callback: Callable | None = None
    ) -> list[str]:
        """Add text to graph in batches, returns list of episode UUIDs"""
        episode_uuids = []
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"Sending batch {batch_num}/{total_batches} ({len(batch_chunks)} chunks)...", progress
                )

            try:
                episode_uuids.extend(self.store.add_episodes(graph_id, batch_chunks))

                time.sleep(1)

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Batch {batch_num} failed: {str(e)}", 0)
                raise

        return episode_uuids

    def _wait_for_episodes(
        self, episode_uuids: list[str], progress_callback: Callable | None = None, timeout: int = 600
    ):
        """Wait for all episodes to finish processing by polling their status"""
        if not episode_uuids:
            if progress_callback:
                progress_callback("No episodes to wait for", 1.0)
            return

        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)

        if progress_callback:
            progress_callback(f"Waiting for {total_episodes} chunks to process...", 0)

        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"Timed out — {completed_count}/{total_episodes} completed", completed_count / total_episodes
                    )
                break

            for ep_uuid in list(pending_episodes):
                try:
                    is_processed = self.store.is_episode_processed(ep_uuid)

                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1

                except Exception:
                    pass

            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"Zep processing... {completed_count}/{total_episodes} done, {len(pending_episodes)} pending ({elapsed}s)",
                    completed_count / total_episodes if total_episodes > 0 else 0,
                )

            if pending_episodes:
                time.sleep(3)

        if progress_callback:
            progress_callback(f"Processing complete: {completed_count}/{total_episodes}", 1.0)

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Get graph information"""
        nodes = self.store.list_nodes(graph_id)
        edges = self.store.list_edges(graph_id)

        # Collect entity types
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id, node_count=len(nodes), edge_count=len(edges), entity_types=list(entity_types)
        )

    def get_graph_data(self, graph_id: str) -> dict[str, Any]:
        """
        Get full graph data including nodes, edges, timestamps, and attributes.
        """
        nodes = self.store.list_nodes(graph_id)
        edges = self.store.list_edges(graph_id)

        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""

        nodes_data = []
        for node in nodes:
            created_at = getattr(node, "created_at", None)
            if created_at:
                created_at = str(created_at)

            nodes_data.append(
                {
                    "uuid": node.uuid_,
                    "name": node.name,
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                    "attributes": node.attributes or {},
                    "created_at": created_at,
                }
            )

        edges_data = []
        for edge in edges:
            created_at = getattr(edge, "created_at", None)
            valid_at = getattr(edge, "valid_at", None)
            invalid_at = getattr(edge, "invalid_at", None)
            expired_at = getattr(edge, "expired_at", None)

            # Get episodes
            episodes = getattr(edge, "episodes", None) or getattr(edge, "episode_ids", None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]

            # Get fact_type
            fact_type = getattr(edge, "fact_type", None) or edge.name or ""

            edges_data.append(
                {
                    "uuid": edge.uuid_,
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "fact_type": fact_type,
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "source_node_name": node_map.get(edge.source_node_uuid, ""),
                    "target_node_name": node_map.get(edge.target_node_uuid, ""),
                    "attributes": edge.attributes or {},
                    "created_at": str(created_at) if created_at else None,
                    "valid_at": str(valid_at) if valid_at else None,
                    "invalid_at": str(invalid_at) if invalid_at else None,
                    "expired_at": str(expired_at) if expired_at else None,
                    "episodes": episodes or [],
                }
            )

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        """Delete a graph"""
        self.store.delete_graph(graph_id)
