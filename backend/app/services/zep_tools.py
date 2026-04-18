"""
Zep Retrieval Tools Service
Wraps graph search, node reading, edge queries, etc. for use by the Report Agent.

Core retrieval tools (optimised):
1. InsightForge (deep insight retrieval) - most powerful hybrid retrieval, auto-generates sub-queries and searches multiple dimensions
2. PanoramaSearch (broad search) - get the full picture, including expired content
3. QuickSearch (simple search) - fast retrieval
"""

import time
import json
from typing import Any

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .zep_tools_models import (
    AgentInterview,
    EdgeInfo,
    InsightForgeResult,
    InterviewResult,
    NodeInfo,
    PanoramaResult,
    SearchResult,
)

logger = get_logger("glas.zep_tools")


class ZepToolsService:
    """
    Zep Retrieval Tools Service

    [Core retrieval tools - optimised]
    1. insight_forge - deep insight retrieval (most powerful, auto-generates sub-queries, multi-dimensional)
    2. panorama_search - broad search (full picture, including expired content)
    3. quick_search - simple search (fast retrieval)
    4. interview_agents - in-depth interview (interview simulated agents, gather multi-perspective views)

    [Basic tools]
    - search_graph - graph semantic search
    - get_all_nodes - get all nodes in the graph
    - get_all_edges - get all edges in the graph (with temporal info)
    - get_node_detail - get detailed node information
    - get_node_edges - get edges related to a node
    - get_entities_by_type - get entities by type
    - get_entity_summary - get relationship summary for an entity
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def __init__(self, api_key: str | None = None, llm_client: LLMClient | None = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY is not configured")

        self.client = Zep(api_key=self.api_key)
        self._llm_client = llm_client
        logger.info("ZepToolsService initialised successfully")

    @property
    def llm(self) -> LLMClient:
        """Lazily initialise the LLM client"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """API call with retry mechanism"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY

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
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name} still failing after {max_retries} attempts: {str(e)}")

        raise last_exception

    def search_graph(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges") -> SearchResult:
        """
        Graph semantic search

        Uses hybrid search (semantic + BM25) to find relevant information in the graph.
        Falls back to local keyword matching if the Zep Cloud search API is unavailable.

        Args:
            graph_id: Graph ID (Standalone Graph)
            query: Search query
            limit: Number of results to return
            scope: Search scope, "edges" or "nodes"

        Returns:
            SearchResult: Search result
        """
        logger.info(f"Graph search: graph_id={graph_id}, query={query[:50]}...")

        # Try using the Zep Cloud Search API
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id, query=query, limit=limit, scope=scope, reranker="cross_encoder"
                ),
                operation_name=f"graph_search(graph={graph_id})",
            )

            facts = []
            edges = []
            nodes = []

            # Parse edge search results
            if hasattr(search_results, "edges") and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, "fact") and edge.fact:
                        facts.append(edge.fact)
                    edges.append(
                        {
                            "uuid": getattr(edge, "uuid_", None) or getattr(edge, "uuid", ""),
                            "name": getattr(edge, "name", ""),
                            "fact": getattr(edge, "fact", ""),
                            "source_node_uuid": getattr(edge, "source_node_uuid", ""),
                            "target_node_uuid": getattr(edge, "target_node_uuid", ""),
                        }
                    )

            # Parse node search results
            if hasattr(search_results, "nodes") and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append(
                        {
                            "uuid": getattr(node, "uuid_", None) or getattr(node, "uuid", ""),
                            "name": getattr(node, "name", ""),
                            "labels": getattr(node, "labels", []),
                            "summary": getattr(node, "summary", ""),
                        }
                    )
                    # Node summaries also count as facts
                    if hasattr(node, "summary") and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")

            logger.info(f"Search complete: found {len(facts)} relevant facts")

            return SearchResult(facts=facts, edges=edges, nodes=nodes, query=query, total_count=len(facts))

        except Exception as e:
            logger.warning(f"Zep Search API failed, falling back to local search: {str(e)}")
            return self._local_search(graph_id, query, limit, scope)

    def _local_search(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges") -> SearchResult:
        """
        Local keyword matching search (fallback for Zep Search API)

        Fetches all edges/nodes and performs local keyword matching.

        Args:
            graph_id: Graph ID
            query: Search query
            limit: Number of results to return
            scope: Search scope

        Returns:
            SearchResult: Search result
        """
        logger.info(f"Using local search: query={query[:30]}...")

        facts = []
        edges_result = []
        nodes_result = []

        # Extract query keywords (simple tokenisation)
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(",", " ").replace("，", " ").split() if len(w.strip()) > 1]

        def match_score(text: str) -> int:
            """Calculate the match score between text and query"""
            if not text:
                return 0
            text_lower = text.lower()
            # Exact query match
            if query_lower in text_lower:
                return 100
            # Keyword match
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score

        try:
            if scope in ["edges", "both"]:
                # Fetch all edges and match
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))

                # Sort by score
                scored_edges.sort(key=lambda x: x[0], reverse=True)

                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append(
                        {
                            "uuid": edge.uuid,
                            "name": edge.name,
                            "fact": edge.fact,
                            "source_node_uuid": edge.source_node_uuid,
                            "target_node_uuid": edge.target_node_uuid,
                        }
                    )

            if scope in ["nodes", "both"]:
                # Fetch all nodes and match
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))

                scored_nodes.sort(key=lambda x: x[0], reverse=True)

                for score, node in scored_nodes[:limit]:
                    nodes_result.append(
                        {
                            "uuid": node.uuid,
                            "name": node.name,
                            "labels": node.labels,
                            "summary": node.summary,
                        }
                    )
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")

            logger.info(f"Local search complete: found {len(facts)} relevant facts")

        except Exception as e:
            logger.error(f"Local search failed: {str(e)}")

        return SearchResult(facts=facts, edges=edges_result, nodes=nodes_result, query=query, total_count=len(facts))

    def get_all_nodes(self, graph_id: str) -> list[NodeInfo]:
        """
        Get all nodes in the graph (paginated retrieval)

        Args:
            graph_id: Graph ID

        Returns:
            List of nodes
        """
        logger.info(f"Fetching all nodes for graph {graph_id}...")

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, "uuid_", None) or getattr(node, "uuid", None) or ""
            result.append(
                NodeInfo(
                    uuid=str(node_uuid) if node_uuid else "",
                    name=node.name or "",
                    labels=node.labels or [],
                    summary=node.summary or "",
                    attributes=node.attributes or {},
                )
            )

        logger.info(f"Fetched {len(result)} nodes")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> list[EdgeInfo]:
        """
        Get all edges in the graph (paginated retrieval, with temporal info)

        Args:
            graph_id: Graph ID
            include_temporal: Whether to include temporal info (default True)

        Returns:
            List of edges (with created_at, valid_at, invalid_at, expired_at)
        """
        logger.info(f"Fetching all edges for graph {graph_id}...")

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, "uuid_", None) or getattr(edge, "uuid", None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or "",
            )

            # Add temporal information
            if include_temporal:
                edge_info.created_at = getattr(edge, "created_at", None)
                edge_info.valid_at = getattr(edge, "valid_at", None)
                edge_info.invalid_at = getattr(edge, "invalid_at", None)
                edge_info.expired_at = getattr(edge, "expired_at", None)

            result.append(edge_info)

        logger.info(f"Fetched {len(result)} edges")
        return result

    def get_node_detail(self, node_uuid: str) -> NodeInfo | None:
        """
        Get detailed information for a single node

        Args:
            node_uuid: Node UUID

        Returns:
            Node info or None
        """
        logger.info(f"Fetching node detail: {node_uuid[:8]}...")

        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"get_node_detail(uuid={node_uuid[:8]}...)",
            )

            if not node:
                return None

            return NodeInfo(
                uuid=getattr(node, "uuid_", None) or getattr(node, "uuid", ""),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
            )
        except Exception as e:
            logger.error(f"Failed to fetch node detail: {str(e)}")
            return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> list[EdgeInfo]:
        """
        Get all edges related to a node

        Fetches all edges in the graph and filters those connected to the specified node.

        Args:
            graph_id: Graph ID
            node_uuid: Node UUID

        Returns:
            List of edges
        """
        logger.info(f"Fetching edges for node {node_uuid[:8]}...")

        try:
            # Fetch all graph edges, then filter
            all_edges = self.get_all_edges(graph_id)

            result = []
            for edge in all_edges:
                # Check whether the edge is connected to the specified node (as source or target)
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)

            logger.info(f"Found {len(result)} edges related to the node")
            return result

        except Exception as e:
            logger.warning(f"Failed to fetch node edges: {str(e)}")
            return []

    def get_entities_by_type(self, graph_id: str, entity_type: str) -> list[NodeInfo]:
        """
        Get entities by type

        Args:
            graph_id: Graph ID
            entity_type: Entity type (e.g. Student, PublicFigure, etc.)

        Returns:
            List of entities matching the type
        """
        logger.info(f"Fetching entities of type {entity_type}...")

        all_nodes = self.get_all_nodes(graph_id)

        filtered = []
        for node in all_nodes:
            # Check whether labels contain the specified type
            if entity_type in node.labels:
                filtered.append(node)

        logger.info(f"Found {len(filtered)} entities of type {entity_type}")
        return filtered

    def get_entity_summary(self, graph_id: str, entity_name: str) -> dict[str, Any]:
        """
        Get relationship summary for a specified entity

        Searches for all information related to the entity and generates a summary.

        Args:
            graph_id: Graph ID
            entity_name: Entity name

        Returns:
            Entity summary information
        """
        logger.info(f"Fetching relationship summary for entity {entity_name}...")

        # First search for information related to this entity
        search_result = self.search_graph(graph_id=graph_id, query=entity_name, limit=20)

        # Try to find this entity among all nodes
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break

        related_edges = []
        if entity_node:
            # Pass graph_id parameter
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)

        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges),
        }

    def get_graph_statistics(self, graph_id: str) -> dict[str, Any]:
        """
        Get graph statistics

        Args:
            graph_id: Graph ID

        Returns:
            Statistics dictionary
        """
        logger.info(f"Fetching statistics for graph {graph_id}...")

        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)

        # Count entity type distribution
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1

        # Count relationship type distribution
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1

        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types,
        }

    def get_simulation_context(self, graph_id: str, simulation_requirement: str, limit: int = 30) -> dict[str, Any]:
        """
        Get simulation-related context information

        Comprehensively searches for all information related to the simulation requirement.

        Args:
            graph_id: Graph ID
            simulation_requirement: Simulation requirement description
            limit: Limit for each category of information

        Returns:
            Simulation context information
        """
        logger.info(f"Fetching simulation context: {simulation_requirement[:50]}...")

        # Search for information related to the simulation requirement
        search_result = self.search_graph(graph_id=graph_id, query=simulation_requirement, limit=limit)

        # Get graph statistics
        stats = self.get_graph_statistics(graph_id)

        # Get all entity nodes
        all_nodes = self.get_all_nodes(graph_id)

        # Filter entities with actual types (not pure Entity nodes)
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({"name": node.name, "type": custom_labels[0], "summary": node.summary})

        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],
            "total_entities": len(entities),
        }

    # ========== Core retrieval tools (optimised) ==========

    def insight_forge(
        self, graph_id: str, query: str, simulation_requirement: str, report_context: str = "", max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        [InsightForge - Deep Insight Retrieval]

        The most powerful hybrid retrieval function; automatically decomposes the question and
        searches across multiple dimensions:
        1. Uses LLM to decompose the question into multiple sub-queries
        2. Performs semantic search for each sub-query
        3. Extracts related entities and fetches their details
        4. Traces relationship chains
        5. Consolidates all results into deep insights

        Args:
            graph_id: Graph ID
            query: User question
            simulation_requirement: Simulation requirement description
            report_context: Report context (optional, for more precise sub-query generation)
            max_sub_queries: Maximum number of sub-queries

        Returns:
            InsightForgeResult: Deep insight retrieval result
        """
        logger.info(f"InsightForge deep insight retrieval: {query[:50]}...")

        result = InsightForgeResult(query=query, simulation_requirement=simulation_requirement, sub_queries=[])

        # Step 1: Use LLM to generate sub-queries
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries,
        )
        result.sub_queries = sub_queries
        logger.info(f"Generated {len(sub_queries)} sub-queries")

        # Step 2: Perform semantic search for each sub-query
        all_facts = []
        all_edges = []
        seen_facts = set()

        for sub_query in sub_queries:
            search_result = self.search_graph(graph_id=graph_id, query=sub_query, limit=15, scope="edges")

            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)

            all_edges.extend(search_result.edges)

        # Also search for the original question
        main_search = self.search_graph(graph_id=graph_id, query=query, limit=20, scope="edges")
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)

        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)

        # Step 3: Extract related entity UUIDs from edges; fetch only these entities (not all nodes)
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get("source_node_uuid", "")
                target_uuid = edge_data.get("target_node_uuid", "")
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)

        # Fetch details for all related entities (no limit, full output)
        entity_insights = []
        node_map = {}

        for uuid in list(entity_uuids):
            if not uuid:
                continue
            try:
                # Fetch each related node individually
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "Entity")

                    related_facts = [f for f in all_facts if node.name.lower() in f.lower()]

                    entity_insights.append(
                        {
                            "uuid": node.uuid,
                            "name": node.name,
                            "type": entity_type,
                            "summary": node.summary,
                            "related_facts": related_facts,
                        }
                    )
            except Exception as e:
                logger.debug(f"Failed to fetch node {uuid}: {e}")
                continue

        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)

        # Step 4: Build all relationship chains (no limit)
        relationship_chains = []
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get("source_node_uuid", "")
                target_uuid = edge_data.get("target_node_uuid", "")
                relation_name = edge_data.get("name", "")

                source_name = node_map.get(source_uuid, NodeInfo("", "", [], "", {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo("", "", [], "", {})).name or target_uuid[:8]

                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)

        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)

        logger.info(
            f"InsightForge complete: {result.total_facts} facts, {result.total_entities} entities, {result.total_relationships} relationships"
        )
        return result

    def _generate_sub_queries(
        self, query: str, simulation_requirement: str, report_context: str = "", max_queries: int = 5
    ) -> list[str]:
        """
        Use LLM to generate sub-queries

        Decomposes a complex question into multiple independently searchable sub-queries.
        """
        system_prompt = """You are a professional question analysis expert. Your task is to decompose a complex question into multiple sub-questions that can be independently observed in the simulation world.

Requirements:
1. Each sub-question should be specific enough to find related agent behaviour or events in the simulation
2. Sub-questions should cover different dimensions of the original question (who, what, why, how, when, where)
3. Sub-questions should be relevant to the simulation scenario
4. Return JSON format: {"sub_queries": ["sub-question 1", "sub-question 2", ...]}
5. All sub-questions must be in English"""

        user_prompt = f"""Simulation requirement background:
{simulation_requirement}

{f"Report context: {report_context[:500]}" if report_context else ""}

Decompose the following question into {max_queries} sub-questions:
{query}

Return a JSON-formatted list of sub-questions in English."""

        try:
            response = self.llm.chat_json(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.3,
            )

            sub_queries = response.get("sub_queries", [])
            # Ensure it is a list of strings
            return [str(sq) for sq in sub_queries[:max_queries]]

        except Exception as e:
            logger.warning(f"Failed to generate sub-queries: {str(e)}, using default sub-queries")
            return [
                query,
                f"Key participants in {query}",
                f"Causes and effects of {query}",
                f"Development process of {query}",
            ][:max_queries]

    def panorama_search(
        self, graph_id: str, query: str, include_expired: bool = True, limit: int = 50
    ) -> PanoramaResult:
        """
        [PanoramaSearch - Broad Search]

        Gets the full-picture view, including all related content and historical/expired information:
        1. Fetches all related nodes
        2. Fetches all edges (including expired/invalidated ones)
        3. Categorises current active and historical information

        Suitable for scenarios that require understanding the full picture of events and
        tracking their evolution.

        Args:
            graph_id: Graph ID
            query: Search query (used for relevance ranking)
            include_expired: Whether to include expired content (default True)
            limit: Result count limit

        Returns:
            PanoramaResult: Broad search result
        """
        logger.info(f"PanoramaSearch broad search: {query[:50]}...")

        result = PanoramaResult(query=query)

        # Fetch all nodes
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)

        # Fetch all edges (with temporal info)
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)

        # Categorise facts
        active_facts = []
        historical_facts = []

        for edge in all_edges:
            if not edge.fact:
                continue

            # Add entity names to facts
            source_name = (
                node_map.get(edge.source_node_uuid, NodeInfo("", "", [], "", {})).name or edge.source_node_uuid[:8]
            )
            target_name = (
                node_map.get(edge.target_node_uuid, NodeInfo("", "", [], "", {})).name or edge.target_node_uuid[:8]
            )

            # Determine whether expired/invalidated
            is_historical = edge.is_expired or edge.is_invalid

            if is_historical:
                valid_at = edge.valid_at or "Unknown"
                invalid_at = edge.invalid_at or edge.expired_at or "Unknown"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                active_facts.append(edge.fact)

        # Relevance-based sorting by query
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(",", " ").replace("，", " ").split() if len(w.strip()) > 1]

        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score

        # Sort and limit count
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)

        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)

        logger.info(f"PanoramaSearch complete: {result.active_count} active, {result.historical_count} historical")
        return result

    def quick_search(self, graph_id: str, query: str, limit: int = 10) -> SearchResult:
        """
        [QuickSearch - Simple Search]

        Fast, lightweight retrieval tool:
        1. Directly calls Zep semantic search
        2. Returns the most relevant results
        3. Suitable for simple, straightforward retrieval needs

        Args:
            graph_id: Graph ID
            query: Search query
            limit: Number of results to return

        Returns:
            SearchResult: Search result
        """
        logger.info(f"QuickSearch simple search: {query[:50]}...")

        # Directly call the existing search_graph method
        result = self.search_graph(graph_id=graph_id, query=query, limit=limit, scope="edges")

        logger.info(f"QuickSearch complete: {result.total_count} results")
        return result

    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: list[str] = None,
    ) -> InterviewResult:
        """
        [InterviewAgents - In-Depth Interview]

        Calls the real OASIS interview API to interview agents running in the simulation:
        1. Automatically reads persona files to learn about all simulated agents
        2. Uses LLM to analyse interview requirements and intelligently select the most relevant agents
        3. Uses LLM to generate interview questions
        4. Calls /api/simulation/interview/batch endpoint for real interviews (dual-platform simultaneous)
        5. Consolidates all interview results and generates an interview report

        [Important] This feature requires the simulation environment to be running (OASIS not shut down)

        [Use cases]
        - Need to understand event perspectives from different roles
        - Need to gather opinions and viewpoints from multiple parties
        - Need to obtain real answers from simulated agents (not LLM-simulated)

        Args:
            simulation_id: Simulation ID (used to locate persona files and call interview API)
            interview_requirement: Interview requirement description (unstructured, e.g. "understand students' views on the event")
            simulation_requirement: Simulation requirement background (optional)
            max_agents: Maximum number of agents to interview
            custom_questions: Custom interview questions (optional; auto-generated if not provided)

        Returns:
            InterviewResult: Interview result
        """
        from .simulation_runner import SimulationRunner

        logger.info(f"InterviewAgents in-depth interview (real API): {interview_requirement[:50]}...")

        result = InterviewResult(interview_topic=interview_requirement, interview_questions=custom_questions or [])

        # Step 1: Load persona files
        profiles = self._load_agent_profiles(simulation_id)

        if not profiles:
            logger.warning(f"Persona files not found for simulation {simulation_id}")
            result.summary = "No agent persona files found for interview"
            return result

        result.total_agents = len(profiles)
        logger.info(f"Loaded {len(profiles)} agent personas")

        # Step 2: Use LLM to select agents for interview (returns agent_id list)
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents,
        )

        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"Selected {len(selected_agents)} agents for interview: {selected_indices}")

        # Step 3: Generate interview questions (if not provided)
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents,
            )
            logger.info(f"Generated {len(result.interview_questions)} interview questions")

        # Combine questions into a single interview prompt
        combined_prompt = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(result.interview_questions)])

        # Add optimisation prefix to constrain agent response format
        INTERVIEW_PROMPT_PREFIX = (
            "You are being interviewed. Drawing on your persona, all past memories and actions, "
            "answer the following questions directly in plain text.\n"
            "Response requirements:\n"
            "1. Answer directly in natural language; do not call any tools\n"
            "2. Do not return JSON format or tool call format\n"
            "3. Do not use Markdown headings (e.g. #, ##, ###)\n"
            "4. Answer each question in order, starting each answer with 'Question X:' (X = question number)\n"
            "5. Separate answers to different questions with blank lines\n"
            "6. Provide substantive answers, at least 2-3 sentences per question\n"
            "7. Answer in English\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"

        # Step 4: Call the real interview API (no platform specified, defaults to dual-platform)
        try:
            # Build batch interview list (no platform specified, dual-platform)
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({"agent_id": agent_idx, "prompt": optimized_prompt})

            logger.info(f"Calling batch interview API (dual-platform): {len(interviews_request)} agents")

            # Call SimulationRunner's batch interview method (no platform, dual-platform)
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id, interviews=interviews_request, platform=None, timeout=180.0
            )

            logger.info(
                f"Interview API returned: {api_result.get('interviews_count', 0)} results, success={api_result.get('success')}"
            )

            if not api_result.get("success", False):
                error_msg = api_result.get("error", "Unknown error")
                logger.warning(f"Interview API returned failure: {error_msg}")
                result.summary = (
                    f"Interview API call failed: {error_msg}. Please check the OASIS simulation environment status."
                )
                return result

            # Step 5: Parse API response and build AgentInterview objects
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}

            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "Unknown")
                agent_bio = agent.get("bio", "")

                # Get this agent's interview results from both platforms
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})

                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # Clean potential tool-call JSON wrappers
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                twitter_text = twitter_response if twitter_response else "(No response received from this platform)"
                reddit_text = reddit_response if reddit_response else "(No response received from this platform)"
                response_text = (
                    f"[Twitter Platform Response]\n{twitter_text}\n\n[Reddit Platform Response]\n{reddit_text}"
                )

                # Extract key quotes from both platform responses
                import re

                combined_responses = f"{twitter_response} {reddit_response}"

                # Clean response text: remove markers, numbering, Markdown, etc.
                clean_text = re.sub(r"#{1,6}\s+", "", combined_responses)
                clean_text = re.sub(r"\{[^}]*tool_name[^}]*\}", "", clean_text)
                clean_text = re.sub(r"[*_`|>~\-]{2,}", "", clean_text)
                clean_text = re.sub(r"\u95ee\u9898\d+[：:]\s*", "", clean_text)
                clean_text = re.sub(r"【[^】]+】", "", clean_text)

                # Strategy 1 (primary): extract complete substantive sentences
                sentences = re.split(r"[。！？]", clean_text)
                meaningful = [
                    s.strip()
                    for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r"^[\s\W，,；;：:、]+", s.strip())
                    and not s.strip().startswith(("{", "\u95ee\u9898"))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]

                # Strategy 2 (supplementary): long text inside properly paired CJK quotes
                if not key_quotes:
                    paired = re.findall(r"\u201c([^\u201c\u201d]{15,100})\u201d", clean_text)
                    paired += re.findall(r"\u300c([^\u300c\u300d]{15,100})\u300d", clean_text)
                    key_quotes = [q for q in paired if not re.match(r"^[，,；;：:、]", q)][:3]

                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5],
                )
                result.interviews.append(interview)

            result.interviewed_count = len(result.interviews)

        except ValueError as e:
            logger.warning(f"Interview API call failed (environment not running?): {e}")
            result.summary = f"Interview failed: {str(e)}. The simulation environment may be shut down; please ensure OASIS is running."
            return result
        except Exception as e:
            logger.error(f"Interview API call exception: {e}")
            import traceback

            logger.error(traceback.format_exc())
            result.summary = f"An error occurred during the interview: {str(e)}"
            return result

        # Step 6: Generate interview summary
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews, interview_requirement=interview_requirement
            )

        logger.info(f"InterviewAgents complete: interviewed {result.interviewed_count} agents (dual-platform)")
        return result

    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Clean JSON tool-call wrappers from agent responses and extract actual content"""
        if not response or not response.strip().startswith("{"):
            return response
        text = response.strip()
        if "tool_name" not in text[:80]:
            return response
        import re as _re

        try:
            data = json.loads(text)
            if isinstance(data, dict) and "arguments" in data:
                for key in ("content", "text", "body", "message", "reply"):
                    if key in data["arguments"]:
                        return str(data["arguments"][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace("\\n", "\n").replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> list[dict[str, Any]]:
        """Load agent persona files for the simulation"""
        import os
        import csv

        # Build persona file path
        sim_dir = os.path.join(os.path.dirname(__file__), f"../../uploads/simulations/{simulation_id}")

        profiles = []

        # Try Reddit JSON format first
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, encoding="utf-8") as f:
                    profiles = json.load(f)
                logger.info(f"Loaded {len(profiles)} personas from reddit_profiles.json")
                return profiles
            except Exception as e:
                logger.warning(f"Failed to read reddit_profiles.json: {e}")

        # Try Twitter CSV format
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        profiles.append(
                            {
                                "realname": row.get("name", ""),
                                "username": row.get("username", ""),
                                "bio": row.get("description", ""),
                                "persona": row.get("user_char", ""),
                                "profession": "Unknown",
                            }
                        )
                logger.info(f"Loaded {len(profiles)} personas from twitter_profiles.csv")
                return profiles
            except Exception as e:
                logger.warning(f"Failed to read twitter_profiles.csv: {e}")

        return profiles

    def _select_agents_for_interview(
        self, profiles: list[dict[str, Any]], interview_requirement: str, simulation_requirement: str, max_agents: int
    ) -> tuple:
        """
        Use LLM to select agents for interview

        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: Full info list of selected agents
                - selected_indices: Index list of selected agents (for API calls)
                - reasoning: Selection rationale
        """

        # Build agent summary list
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "Unknown"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", []),
            }
            agent_summaries.append(summary)

        system_prompt = """You are a professional interview planning expert. Your task is to select the most suitable interview subjects from the simulation agent list based on interview requirements.

Selection criteria:
1. Agent's identity/profession is relevant to the interview topic
2. Agent may hold unique or valuable perspectives
3. Select diverse viewpoints (e.g.: supporters, opponents, neutral parties, professionals)
4. Prioritise roles directly connected to the events

Return JSON format:
{
    "selected_indices": [list of selected agent indices],
    "reasoning": "explanation of selection rationale"
}"""

        user_prompt = f"""Interview requirement:
{interview_requirement}

Simulation background:
{simulation_requirement if simulation_requirement else "Not provided"}

Available agent list ({len(agent_summaries)} agents):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Select up to {max_agents} agents most suitable for interview, and explain the selection rationale."""

        try:
            response = self.llm.chat_json(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.3,
            )

            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "Auto-selected based on relevance")

            # Get full info for selected agents
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)

            return selected_agents, valid_indices, reasoning

        except Exception as e:
            logger.warning(f"LLM agent selection failed, using default selection: {e}")
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "Using default selection strategy"

    def _generate_interview_questions(
        self, interview_requirement: str, simulation_requirement: str, selected_agents: list[dict[str, Any]]
    ) -> list[str]:
        """Use LLM to generate interview questions"""

        agent_roles = [a.get("profession", "Unknown") for a in selected_agents]

        system_prompt = """You are a professional journalist/interviewer. Generate 3-5 in-depth interview questions based on interview requirements.

Question requirements:
1. Open-ended questions that encourage detailed responses
2. Questions that may elicit different answers from different roles
3. Cover multiple dimensions: facts, opinions, feelings
4. Natural language, like a real interview
5. Keep each question concise, under 30 words
6. Ask directly without background preamble
7. All questions must be in English

Return JSON format: {"questions": ["question 1", "question 2", ...]}"""

        user_prompt = f"""Interview requirement: {interview_requirement}

Simulation background: {simulation_requirement if simulation_requirement else "Not provided"}

Interviewee roles: {", ".join(agent_roles)}

Generate 3-5 interview questions in English."""

        try:
            response = self.llm.chat_json(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.5,
            )

            return response.get("questions", [f"What are your views on {interview_requirement}?"])

        except Exception as e:
            logger.warning(f"Failed to generate interview questions: {e}")
            return [
                f"What is your perspective on {interview_requirement}?",
                "How does this affect you or the group you represent?",
                "How do you think this issue should be resolved or improved?",
            ]

    def _generate_interview_summary(self, interviews: list[AgentInterview], interview_requirement: str) -> str:
        """Generate interview summary"""

        if not interviews:
            return "No interviews completed"

        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"[{interview.agent_name} ({interview.agent_role})]\n{interview.response[:500]}")

        system_prompt = """You are a professional news editor. Generate an interview summary based on multiple interviewees' responses.

Summary requirements:
1. Extract key viewpoints from each party
2. Identify consensus and disagreements
3. Highlight valuable quotes
4. Remain objective and neutral
5. Keep within 1000 words
6. Write in English

Format constraints (must follow):
- Use plain text paragraphs separated by blank lines
- Do not use Markdown headings (#, ##, ###)
- Do not use dividers (---, ***)
- Use quotation marks when citing interviewees
- You may use **bold** for keywords but no other Markdown syntax"""

        user_prompt = f"""Interview topic: {interview_requirement}

Interview content:
{"".join(interview_texts)}

Generate an interview summary in English."""

        try:
            summary = self.llm.chat(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            return summary

        except Exception as e:
            logger.warning(f"Failed to generate interview summary: {e}")
            return f"Interviewed {len(interviews)} respondents, including: " + ", ".join(
                [i.agent_name for i in interviews]
            )
