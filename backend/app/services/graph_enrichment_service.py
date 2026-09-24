"""
Graph enrichment service.

After the initial graph build, compares the entity inventory against actual graph nodes
and feeds enrichment episodes to Zep to close the gap toward target_entities.

Verified inventory entities are also materialized directly via Zep's add_nodes API
(no NER dependence), because episode extraction misses organisation names — observed
2026-08-18: only 2 of 12 verified expansion stakeholders became nodes via NER.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from zep_cloud import AddNodeItem, EpisodeData
from zep_cloud.client import Zep

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes
from .graph_snapshot_cache import bump_mutation_generation

logger = get_logger("glas.graph_enrichment")

# Inventory category -> Zep ontology entity type (label). add_nodes validates
# attributes against ontology types that declare properties, so every category
# maps to a type whose property keys we can populate from the inventory entry.
_CATEGORY_LABEL = {
    "government": "Organization",
    "industry_body": "Organization",
    "individual": "Person",
    "company": "Organization",
    "professional_association": "Organization",
    "regulator": "Organization",
    "community": "Organization",
    "ngo": "Organization",
    "media": "MediaOrJournalist",
    "research": "Organization",
    "association": "Organization",
}


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
    rounds: list[EnrichmentRoundResult] = field(default_factory=list)
    stopped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
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
        llm_client: LLMClient | None = None,
    ):
        self.client = zep_client
        self.llm = llm_client or LLMClient()

    def enrich_graph(
        self,
        graph_id: str,
        source_text: str,
        entity_inventory: list[dict[str, Any]],
        target_entities: int,
        max_rounds: int = 3,
        progress_callback: Callable | None = None,
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
        current_nodes, typed_count = self._get_node_stats(graph_id)
        result = EnrichmentResult(
            initial_nodes=len(current_nodes),
            target_entities=target_entities,
        )

        if typed_count >= target_entities:
            result.final_nodes = len(current_nodes)
            result.stopped_reason = "already_at_target"
            logger.info(f"Graph already has {typed_count} typed nodes (target: {target_entities}), skipping enrichment")
            return result

        logger.info(
            f"Starting enrichment: {len(current_nodes)} total nodes ({typed_count} typed), "
            f"target {target_entities}, inventory has {len(entity_inventory)} entities"
        )

        # Directly materialize verified inventory entities that NER would miss.
        # Episodes depend on Zep extracting organisation names; add_nodes is
        # deterministic. Fail-soft: a materialization error never blocks the build.
        if Config.GRAPH_MATERIALIZE_INVENTORY_ENABLED:
            if progress_callback:
                progress_callback("Materializing verified inventory entities...", 0.6)
            try:
                materialized = self._materialize_inventory_nodes(
                    graph_id=graph_id,
                    entity_inventory=entity_inventory,
                    existing_node_names=current_nodes,
                )
                if materialized:
                    logger.info(f"Materialized {materialized} verified inventory nodes directly")
                    current_nodes, typed_count = self._get_node_stats(graph_id)
            except Exception as e:
                logger.warning(f"Inventory materialization failed (non-fatal): {e}")

        if typed_count >= target_entities:
            result.final_nodes = len(current_nodes)
            result.stopped_reason = "target_reached"
            logger.info(
                f"Enrichment target reached after materialization: {typed_count} typed (target: {target_entities})"
            )
            return result

        for round_num in range(1, max_rounds + 1):
            if progress_callback:
                progress_callback(
                    f"Enrichment round {round_num}/{max_rounds} ({typed_count} typed nodes)...",
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

            current_nodes, typed_count = self._get_node_stats(graph_id)
            round_result.nodes_after = len(current_nodes)
            round_result.nodes_added = round_result.nodes_after - round_result.nodes_before

            logger.info(
                f"Enrichment round {round_num}: {round_result.nodes_before} → {round_result.nodes_after} nodes "
                f"({typed_count} typed, +{round_result.nodes_added})"
            )

            if typed_count >= target_entities:
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
                f"Enrichment complete: {result.final_nodes} nodes ({typed_count} typed, target: {target_entities})",
                1.0,
            )

        logger.info(
            f"Enrichment finished: {result.initial_nodes} → {result.final_nodes} nodes ({typed_count} typed) "
            f"in {result.rounds_executed} rounds ({result.stopped_reason})"
        )
        if result.rounds_executed > 0:
            bump_mutation_generation(graph_id)
        return result

    # ───────────────────────────────────────────────────────────
    # Single enrichment round
    # ───────────────────────────────────────────────────────────

    def _run_enrichment_round(
        self,
        graph_id: str,
        source_text: str,
        entity_inventory: list[dict[str, Any]],
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
    # Direct inventory materialization (add_nodes)
    # ───────────────────────────────────────────────────────────

    def _materialize_inventory_nodes(
        self,
        graph_id: str,
        entity_inventory: list[dict[str, Any]],
        existing_node_names: set,
    ) -> int:
        """Create Zep nodes directly for verified inventory entities.

        Zep's add_nodes API materializes nodes deterministically, bypassing the
        episode/NER path that reliably misses organisation names. Entries already
        present (by name) are skipped; up to 100 nodes per request. Returns the
        number of nodes added. Never raises (callers treat it as fail-soft).
        """
        missing = self._find_missing_entities(entity_inventory, existing_node_names)
        if not missing:
            return 0

        items = []
        for entity in missing:
            name = (entity.get("name") or "").strip()
            if not name:
                continue
            label = _CATEGORY_LABEL.get((entity.get("category") or "").lower(), "Organization")
            attrs = self._node_attributes_for(entity, label)
            items.append(
                AddNodeItem(
                    name=name[:50],
                    summary=(entity.get("context") or "")[:500] or None,
                    label=label,
                    attributes=attrs or None,
                )
            )

        added = 0
        for i in range(0, len(items), 100):
            batch = items[i : i + 100]
            try:
                resp = self.client.graph.add_nodes(graph_id=graph_id, nodes=batch)
                batch_added = len(resp.nodes or []) if resp else 0
                added += batch_added
                task_id = getattr(resp, "task_id", None)
                if resp and task_id:
                    self._wait_for_add_nodes_task(task_id)
                logger.info(f"add_nodes: {batch_added} nodes accepted")
            except Exception as e:
                logger.warning(f"add_nodes batch failed (non-fatal): {e}")
                break
        return added

    @staticmethod
    def _node_attributes_for(entity: dict[str, Any], label: str) -> dict[str, Any]:
        """Attributes matching the ontology type's declared properties."""
        name = (entity.get("name") or "").strip()[:50]
        if label == "Person":
            return {"full_name": name, "role": entity.get("category") or ""}
        if label == "MediaOrJournalist":
            return {"org_name": name, "focus": entity.get("category") or ""}
        if label == "HealthWorkforce":
            return {"group_name": name, "profession": entity.get("category") or ""}
        if label == "PharmacyChain":
            return {"company_name": name, "parent_company": ""}
        if label == "PharmacyAssociation":
            return {"org_name": name, "membership": ""}
        if label == "PatientGroup":
            return {"org_name": name, "constituency": entity.get("category") or ""}
        return {"org_name": name, "sector": entity.get("category") or ""}

    def _wait_for_add_nodes_task(self, task_id: str, timeout: float = 300.0) -> None:
        """Poll an add_nodes task until it succeeds or times out (fail-soft)."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                task = self.client.task.get(task_id=task_id)
                status = getattr(task, "status", None)
                if status == "succeeded":
                    return
                if status == "failed":
                    logger.warning(f"add_nodes task {task_id} failed: {getattr(task, 'error', None)}")
                    return
            except Exception as e:
                logger.debug(f"add_nodes task poll error (retrying): {e}")
            time.sleep(self.EPISODE_POLL_INTERVAL)
        logger.warning(f"add_nodes task {task_id} still pending after {timeout}s")

    # ───────────────────────────────────────────────────────────
    # Gap analysis
    # ───────────────────────────────────────────────────────────

    def _get_node_stats(self, graph_id: str) -> tuple[set, int]:
        """Return (all_node_names, typed_node_count) in a single pagination pass."""
        nodes = fetch_all_nodes(self.client, graph_id)
        names = set()
        typed = 0
        for node in nodes:
            if node.name:
                names.add(node.name.strip().lower())
            if any(label not in ("Entity", "Node") for label in (node.labels or [])):
                typed += 1
        return names, typed

    def _find_missing_entities(
        self,
        entity_inventory: list[dict[str, Any]],
        existing_node_names: set,
    ) -> list[dict[str, Any]]:
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
        missing_entities: list[dict[str, Any]],
        existing_node_names: set,
        source_text: str,
        max_entities_per_batch: int = 10,
    ) -> list[str]:
        """Use LLM to generate natural language passages that describe missing entities."""
        batch = missing_entities[:max_entities_per_batch]

        entity_list = "\n".join(
            f"- {e.get('name', '?')} ({e.get('category', '?')}): {e.get('context', '')}" for e in batch
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

    def _send_episodes(self, graph_id: str, passages: list[str]) -> list[str]:
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

    def _wait_for_episodes(self, episode_uuids: list[str]) -> None:
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
