"""
Graph enrichment service.

After the initial graph build, compares the entity inventory against actual graph nodes
and feeds enrichment episodes to Zep to close the gap toward target_entities.
"""

import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

from zep_cloud import EpisodeData
from zep_cloud.client import Zep

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes
from ..utils.logger import get_logger

logger = get_logger('glas.graph_enrichment')


@dataclass
class EnrichmentRoundResult:
    """Outcome of a single enrichment round."""
    round_num: int = 0
    nodes_before: int = 0
    nodes_after: int = 0
    nodes_added: int = 0
    missing_entities_targeted: int = 0
    episodes_sent: int = 0


@dataclass
class EnrichmentResult:
    """Outcome of the full enrichment process."""
    initial_nodes: int = 0
    final_nodes: int = 0
    target_entities: int = 0
    rounds_executed: int = 0
    rounds: List[EnrichmentRoundResult] = field(default_factory=list)
    stopped_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_nodes": self.initial_nodes,
            "final_nodes": self.final_nodes,
            "target_entities": self.target_entities,
            "rounds_executed": self.rounds_executed,
            "stopped_reason": self.stopped_reason,
            "rounds": [
                {
                    "round": r.round_num,
                    "nodes_before": r.nodes_before,
                    "nodes_after": r.nodes_after,
                    "nodes_added": r.nodes_added,
                    "missing_targeted": r.missing_entities_targeted,
                    "episodes_sent": r.episodes_sent,
                }
                for r in self.rounds
            ],
        }


class GraphEnrichmentService:
    """Runs iterative enrichment cycles to push graph node count toward a target."""

    EPISODE_PROCESSING_TIMEOUT = 300
    EPISODE_POLL_INTERVAL = 3

    def __init__(
        self,
        zep_client: Zep,
        llm_client: Optional[LLMClient] = None,
    ):
        self.client = zep_client
        self.llm = llm_client or LLMClient()

    def enrich_graph(
        self,
        graph_id: str,
        source_text: str,
        entity_inventory: List[Dict[str, Any]],
        target_entities: int,
        max_rounds: int = 3,
        progress_callback: Optional[Callable] = None,
    ) -> EnrichmentResult:
        """
        Run enrichment cycles until node count >= target or max_rounds reached.

        Args:
            graph_id: Zep graph ID
            source_text: Original document text (used for context)
            entity_inventory: Pre-scanned entity list from ontology generator
            target_entities: Target node count
            max_rounds: Maximum enrichment iterations
            progress_callback: Optional (message, progress_ratio) callback

        Returns:
            EnrichmentResult with per-round details
        """
        current_nodes = self._get_node_names(graph_id)
        result = EnrichmentResult(
            initial_nodes=len(current_nodes),
            target_entities=target_entities,
        )

        if len(current_nodes) >= target_entities:
            result.final_nodes = len(current_nodes)
            result.stopped_reason = "already_at_target"
            logger.info(f"Graph already has {len(current_nodes)} nodes (target: {target_entities}), skipping enrichment")
            return result

        logger.info(
            f"Starting enrichment: {len(current_nodes)} nodes, target {target_entities}, "
            f"inventory has {len(entity_inventory)} entities"
        )

        for round_num in range(1, max_rounds + 1):
            if progress_callback:
                progress_callback(
                    f"Enrichment round {round_num}/{max_rounds} ({len(current_nodes)} nodes)...",
                    (round_num - 1) / max_rounds,
                )

            round_result = self._run_enrichment_round(
                graph_id=graph_id,
                source_text=source_text,
                entity_inventory=entity_inventory,
                existing_node_names=current_nodes,
                round_num=round_num,
            )
            result.rounds.append(round_result)
            result.rounds_executed = round_num

            current_nodes = self._get_node_names(graph_id)
            round_result.nodes_after = len(current_nodes)
            round_result.nodes_added = round_result.nodes_after - round_result.nodes_before

            logger.info(
                f"Enrichment round {round_num}: {round_result.nodes_before} → {round_result.nodes_after} nodes "
                f"(+{round_result.nodes_added})"
            )

            if len(current_nodes) >= target_entities:
                result.stopped_reason = "target_reached"
                break

            if round_result.nodes_added == 0:
                result.stopped_reason = "no_new_nodes"
                logger.info("Enrichment stopped: round added 0 nodes")
                break

            if round_result.missing_entities_targeted == 0:
                result.stopped_reason = "no_missing_entities"
                break
        else:
            result.stopped_reason = "max_rounds"

        result.final_nodes = len(current_nodes)

        if progress_callback:
            progress_callback(
                f"Enrichment complete: {result.final_nodes} nodes (target: {target_entities})",
                1.0,
            )

        logger.info(
            f"Enrichment finished: {result.initial_nodes} → {result.final_nodes} nodes "
            f"in {result.rounds_executed} rounds ({result.stopped_reason})"
        )
        return result

    # ───────────────────────────────────────────────────────────
    # Single enrichment round
    # ───────────────────────────────────────────────────────────

    def _run_enrichment_round(
        self,
        graph_id: str,
        source_text: str,
        entity_inventory: List[Dict[str, Any]],
        existing_node_names: set,
        round_num: int,
    ) -> EnrichmentRoundResult:
        round_result = EnrichmentRoundResult(
            round_num=round_num,
            nodes_before=len(existing_node_names),
        )

        missing = self._find_missing_entities(entity_inventory, existing_node_names)
        round_result.missing_entities_targeted = len(missing)

        if not missing:
            return round_result

        episodes = self._generate_enrichment_episodes(
            missing_entities=missing,
            existing_node_names=existing_node_names,
            source_text=source_text,
        )

        if not episodes:
            return round_result

        episode_uuids = self._send_episodes(graph_id, episodes)
        round_result.episodes_sent = len(episode_uuids)

        self._wait_for_episodes(episode_uuids)

        return round_result

    # ───────────────────────────────────────────────────────────
    # Gap analysis
    # ───────────────────────────────────────────────────────────

    def _get_node_names(self, graph_id: str) -> set:
        nodes = fetch_all_nodes(self.client, graph_id)
        names = set()
        for node in nodes:
            if node.name:
                names.add(node.name.strip().lower())
        return names

    def _find_missing_entities(
        self,
        entity_inventory: List[Dict[str, Any]],
        existing_node_names: set,
    ) -> List[Dict[str, Any]]:
        """Return inventory entries not yet present in the graph."""
        missing = []
        for entity in entity_inventory:
            name = entity.get("name", "").strip()
            if not name:
                continue
            name_lower = name.lower()
            if name_lower not in existing_node_names and not any(
                name_lower in existing for existing in existing_node_names
            ):
                missing.append(entity)
        return missing

    # ───────────────────────────────────────────────────────────
    # Enrichment episode generation (LLM)
    # ───────────────────────────────────────────────────────────

    def _generate_enrichment_episodes(
        self,
        missing_entities: List[Dict[str, Any]],
        existing_node_names: set,
        source_text: str,
        max_entities_per_batch: int = 10,
    ) -> List[str]:
        """Use LLM to generate natural language passages that describe missing entities."""
        batch = missing_entities[:max_entities_per_batch]

        entity_list = "\n".join(
            f"- {e.get('name', '?')} ({e.get('category', '?')}): {e.get('context', '')}"
            for e in batch
        )

        existing_sample = sorted(existing_node_names)[:20]
        existing_text = ", ".join(existing_sample)

        system_prompt = (
            "You are a knowledge graph data enrichment specialist.\n\n"
            "Given a list of entities that are MISSING from a knowledge graph, write 3-5 short "
            "natural language passages (each 100-200 words) that describe these entities and their "
            "relationships to each other and to the existing entities in the graph.\n\n"
            "Rules:\n"
            "- Each passage should mention 2-4 missing entities by name\n"
            "- Connect missing entities to existing graph entities where possible\n"
            "- Write in factual, encyclopedic style (like a Wikipedia paragraph)\n"
            "- Only state facts that are grounded in the entity descriptions provided\n"
            "- Do NOT invent relationships that aren't implied by the context\n"
            "- Mention each entity's full name clearly so a named entity recognizer can extract it\n\n"
            "Return JSON:\n"
            '{"passages": ["passage 1 text", "passage 2 text", ...]}'
        )

        user_prompt = (
            f"Entities MISSING from the graph (add these):\n{entity_list}\n\n"
            f"Entities ALREADY in the graph (reference these for connections):\n{existing_text}\n\n"
            f"Source document excerpt for context:\n{source_text[:3000]}"
        )

        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
            )
            passages = result.get("passages", [])
            return [p for p in passages if isinstance(p, str) and len(p.strip()) > 20]
        except Exception as e:
            logger.error(f"Enrichment episode generation failed: {e}")
            return []

    # ───────────────────────────────────────────────────────────
    # Send episodes to Zep
    # ───────────────────────────────────────────────────────────

    def _send_episodes(self, graph_id: str, passages: List[str]) -> List[str]:
        episodes = [EpisodeData(data=passage, type="text") for passage in passages]
        episode_uuids = []

        try:
            batch_result = self.client.graph.add_batch(
                graph_id=graph_id,
                episodes=episodes,
            )
            if batch_result and isinstance(batch_result, list):
                for ep in batch_result:
                    ep_uuid = getattr(ep, "uuid_", None) or getattr(ep, "uuid", None)
                    if ep_uuid:
                        episode_uuids.append(ep_uuid)
            logger.info(f"Sent {len(episodes)} enrichment episodes, got {len(episode_uuids)} UUIDs")
        except Exception as e:
            logger.error(f"Failed to send enrichment episodes: {e}")

        return episode_uuids

    def _wait_for_episodes(self, episode_uuids: List[str]) -> None:
        if not episode_uuids:
            return

        pending = set(episode_uuids)
        start = time.time()

        while pending and (time.time() - start) < self.EPISODE_PROCESSING_TIMEOUT:
            for ep_uuid in list(pending):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    if getattr(episode, "processed", False):
                        pending.remove(ep_uuid)
                except Exception:
                    pass

            if pending:
                time.sleep(self.EPISODE_POLL_INTERVAL)

        if pending:
            logger.warning(f"{len(pending)} enrichment episodes still pending after timeout")
