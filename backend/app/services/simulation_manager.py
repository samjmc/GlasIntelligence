"""
OASIS simulation manager
Manages Twitter and Reddit dual-platform parallel simulation
Uses preset scripts + LLM for intelligent config parameter generation
"""

import csv
import os
import json
import shutil
from collections.abc import Callable
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, EntityNode
from .oasis_profile_generator import OasisProfileGenerator
from .simulation_config_generator import SimulationConfigGenerator

logger = get_logger("glas.simulation")


class SimulationStatus(str, Enum):
    """Simulation status"""

    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"  # Simulation manually stopped
    COMPLETED = "completed"  # Simulation completed naturally
    FAILED = "failed"


@dataclass
class SimulationState:
    """Simulation state"""

    simulation_id: str
    project_id: str
    graph_id: str

    # Platform enable status
    enable_twitter: bool = True
    enable_reddit: bool = True

    # Status
    status: SimulationStatus = SimulationStatus.CREATED

    # Preparation phase data
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Config generation info
    config_generated: bool = False
    config_reasoning: str = ""

    # Runtime data
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Error info
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Full state dict (internal use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "warnings": self.warnings,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    def to_simple_dict(self) -> dict[str, Any]:
        """Simplified state dict (for API response)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "warnings": self.warnings,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Manages simulation lifecycle: persistent state (state.json), entity
    ingestion from Zep, OASIS profile generation (Reddit JSON / Twitter CSV),
    LLM-driven simulation_config.json, and helpers to read profiles/config and
    run instructions. Run scripts under backend/scripts/ are not bundled per
    simulation; the runner uses paths returned here.
    """

    # Simulation data storage directory
    SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), "../../uploads/simulations")

    def __init__(self):
        # Ensure directory exists
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)

        # In-memory simulation state cache
        self._simulations: dict[str, SimulationState] = {}

    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Get simulation data directory"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir

    def _save_simulation_state(self, state: SimulationState):
        """Save simulation state to file"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")

        state.updated_at = datetime.now().isoformat()

        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        except (OSError, TypeError) as e:
            logger.error(
                "Failed to save simulation state for %s at %s: %s",
                state.simulation_id,
                state_file,
                e,
            )
            state.status = SimulationStatus.FAILED
            raise

        self._simulations[state.simulation_id] = state

    def _load_simulation_state(self, simulation_id: str) -> SimulationState | None:
        """Load simulation state from file"""
        if simulation_id in self._simulations:
            # TODO: Validate cache freshness under multi-worker scenarios (stat mtime vs cached updated_at).
            return self._simulations[simulation_id]

        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")

        if not os.path.exists(state_file):
            return None

        try:
            with open(state_file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Failed to load simulation state for %s at %s: %s",
                simulation_id,
                state_file,
                e,
            )
            return None

        raw_status = str(data.get("status", "created"))
        try:
            loaded_status = SimulationStatus(raw_status)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid simulation status in state.json for %r: %r; using failed",
                simulation_id,
                raw_status,
            )
            loaded_status = SimulationStatus.FAILED

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=loaded_status,
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            warnings=data.get("warnings") or [],
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )

        self._simulations[simulation_id] = state
        return state

    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        Create new simulation

        Args:
            project_id: Project ID
            graph_id: Zep graph ID
            enable_twitter: Whether to enable Twitter simulation
            enable_reddit: Whether to enable Reddit simulation

        Returns:
            SimulationState
        """
        import uuid

        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )

        self._save_simulation_state(state)
        logger.info(f"Created simulation: {simulation_id}, project={project_id}, graph={graph_id}")

        return state

    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str = "",
        document_text: str = "",
        defined_entity_types: list[str] | None = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Callable | None = None,
        parallel_profile_count: int = 3,
        user_plan: str = "pro",
        time_scale_override: dict | None = None,
        profile_source_sim_id: str | None = None,
    ) -> SimulationState:
        """
        Prepare simulation environment (fully automated)

        Steps:
        1. Read and filter entities from Zep graph
        2. Generate OASIS Agent Profile for each entity (optional LLM enhancement, supports parallel)
        3. Use LLM to intelligently generate simulation config params (time, activity, posting frequency, etc.)
        4. Save simulation_config.json and platform profile files (Reddit: reddit_profiles.json, Twitter: twitter_profiles.csv) under the simulation directory
        Preset run scripts live in backend/scripts/ and are not copied here; simulation_runner invokes them with the saved config path.

        Args:
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description (for LLM config generation)
            document_text: Original document content (for LLM to understand context)
            defined_entity_types: Predefined entity types (optional)
            use_llm_for_profiles: Whether to use LLM for detailed persona generation
            progress_callback: Progress callback (stage, progress, message)
            parallel_profile_count: Number of parallel profile generations, default 3
            time_scale_override: Pre-determined time config dict to enforce consistent time scales across bundle scenarios

        Returns:
            SimulationState
        """
        if not time_scale_override:
            time_scale_override = None

        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)

            sim_dir = self._get_simulation_dir(simulation_id)

            entities_for_config: list[EntityNode] = []

            reuse_sim_id = profile_source_sim_id
            if reuse_sim_id:
                source_dir = self._get_simulation_dir(reuse_sim_id)
                entities_path = os.path.join(source_dir, "entities.json")
                if not os.path.exists(entities_path):
                    logger.warning(
                        "Fast path skipped: missing entities.json in %s (profile_source_sim_id=%s); "
                        "falling back to full preparation for %s",
                        source_dir,
                        reuse_sim_id,
                        simulation_id,
                    )
                    reuse_sim_id = None

            if reuse_sim_id:
                # ========== Fast path: copy profiles from a previous simulation ==========
                source_dir = self._get_simulation_dir(reuse_sim_id)
                entities_path = os.path.join(source_dir, "entities.json")
                logger.info(f"Reusing profiles from {reuse_sim_id} for {simulation_id}")

                if progress_callback:
                    progress_callback("reading", 0, "Copying profiles from previous scenario...")

                for fname in ("reddit_profiles.json", "twitter_profiles.csv"):
                    src = os.path.join(source_dir, fname)
                    if os.path.exists(src):
                        shutil.copy2(src, os.path.join(sim_dir, fname))

                reddit_dst = os.path.join(sim_dir, "reddit_profiles.json")
                twitter_dst = os.path.join(sim_dir, "twitter_profiles.csv")
                if not (os.path.exists(reddit_dst) and os.path.exists(twitter_dst)):
                    logger.warning(
                        "Fast path skipped: missing profile file(s) after copy — "
                        "expected %s and %s under %s (profile_source_sim_id=%s); "
                        "falling back to full preparation for %s",
                        os.path.basename(reddit_dst),
                        os.path.basename(twitter_dst),
                        sim_dir,
                        reuse_sim_id,
                        simulation_id,
                    )
                    reuse_sim_id = None

                # Residual (harden later): profile files — same TOCTOU class as entities.json below.
                # After os.path.exists passes on reddit_dst/twitter_dst, files may still be removed
                # before the runner reads them. Address in the same prepare-pipeline I/O hardening pass.

            if reuse_sim_id:
                # Residual (harden later): entities.json — exists check earlier vs open here is a TOCTOU
                # gap; json.load root is not validated as a list. Prefer atomic read + error handling
                # and validate list-of-dicts when tightening prepare pipeline file I/O.
                with open(entities_path, encoding="utf-8") as f:
                    entities_for_config = [EntityNode.from_dict(e) for e in json.load(f)]

                source_state = self._load_simulation_state(reuse_sim_id)
                if source_state:
                    state.entities_count = source_state.entities_count
                    state.entity_types = list(source_state.entity_types)
                    state.profiles_count = source_state.profiles_count

                self._save_simulation_state(state)

                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        100,
                        f"Reused {state.profiles_count} profiles from previous scenario",
                        current=state.profiles_count,
                        total=state.profiles_count,
                    )
            else:
                # ========== Full path: read entities and generate profiles ==========

                # ========== Phase 1: Read and filter entities ==========
                if progress_callback:
                    progress_callback("reading", 0, "Connecting to Zep graph...")

                reader = ZepEntityReader()

                if progress_callback:
                    progress_callback("reading", 30, "Reading node data...")

                filtered = reader.filter_defined_entities(
                    graph_id=state.graph_id, defined_entity_types=defined_entity_types, enrich_with_edges=True
                )

                max_agents, _ = Config.simulation_limits(user_plan)
                if len(filtered.entities) > max_agents:
                    logger.info(f"Capping agents: {len(filtered.entities)} -> {max_agents}")
                    filtered.entities = sorted(
                        filtered.entities,
                        key=lambda e: len(getattr(e, "related_edges", []) or []),
                        reverse=True,
                    )[:max_agents]
                    filtered.filtered_count = max_agents

                state.entities_count = filtered.filtered_count
                state.entity_types = list(filtered.entity_types)
                self._save_simulation_state(state)

                if progress_callback:
                    progress_callback(
                        "reading",
                        100,
                        f"Done, {filtered.filtered_count} entities total",
                        current=filtered.filtered_count,
                        total=filtered.filtered_count,
                    )

                if filtered.filtered_count == 0:
                    state.status = SimulationStatus.FAILED
                    state.error = "No entities matching criteria found, please check if graph is built correctly"
                    self._save_simulation_state(state)
                    return state

                MIN_RECOMMENDED_ENTITIES = 10
                if filtered.filtered_count < MIN_RECOMMENDED_ENTITIES:
                    msg = (
                        f"Only {filtered.filtered_count} agents found — simulation quality may be limited. "
                        "Upload more documents or run deep research for richer entity extraction."
                    )
                    logger.warning(f"[{simulation_id}] {msg}")
                    state.warnings.append(msg)
                    self._save_simulation_state(state)

                # ========== Phase 1.5: Representative voice agents from untyped nodes ==========
                remaining_slots = max_agents - len(filtered.entities)
                if remaining_slots > 0:
                    voice_entities = self._create_representative_voices(
                        reader=reader,
                        graph_id=state.graph_id,
                        existing_names={e.name.strip().lower() for e in filtered.entities},
                        remaining_slots=remaining_slots,
                        typed_entity_types=list(filtered.entity_types),
                        progress_callback=progress_callback,
                    )
                    if voice_entities:
                        filtered.entities.extend(voice_entities)
                        filtered.filtered_count = len(filtered.entities)
                        state.entities_count = filtered.filtered_count
                        self._save_simulation_state(state)
                        logger.info(
                            f"Added {len(voice_entities)} representative voice agents, "
                            f"total agents now: {filtered.filtered_count}"
                        )

                entities_for_config = filtered.entities

                # Save entity list for reuse by subsequent bundle scenarios
                try:
                    entities_path = os.path.join(sim_dir, "entities.json")
                    with open(entities_path, "w", encoding="utf-8") as f:
                        json.dump([e.to_dict() for e in filtered.entities], f, ensure_ascii=False)
                except Exception as e:
                    logger.warning(f"Failed to save entities.json: {e}")

                # ========== Phase 2: Generate Agent Profile ==========
                total_entities = len(filtered.entities)

                if progress_callback:
                    progress_callback(
                        "generating_profiles", 0, "Starting generation...", current=0, total=total_entities
                    )

                generator = OasisProfileGenerator(graph_id=state.graph_id)

                def profile_progress(current, total, msg):
                    if current % 5 == 0 or current == total:
                        state.profiles_count = current
                        self._save_simulation_state(state)
                    if progress_callback:
                        pct = 0 if total == 0 else int(current / total * 100)
                        progress_callback(
                            "generating_profiles",
                            pct,
                            msg,
                            current=current,
                            total=total,
                            item_name=msg,
                        )

                realtime_output_path = None
                realtime_platform = "reddit"
                if state.enable_reddit:
                    realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                    realtime_platform = "reddit"
                elif state.enable_twitter:
                    realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                    realtime_platform = "twitter"

                scenario_context = simulation_requirement or ""
                if document_text:
                    scenario_context += f"\n\nContext:\n{document_text[:5000]}"

                profiles = generator.generate_profiles_from_entities(
                    entities=filtered.entities,
                    use_llm=use_llm_for_profiles,
                    progress_callback=profile_progress,
                    graph_id=state.graph_id,
                    parallel_count=parallel_profile_count,
                    realtime_output_path=realtime_output_path,
                    output_platform=realtime_platform,
                    scenario_context=scenario_context,
                )

                state.profiles_count = len(profiles)
                self._save_simulation_state(state)

                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        95,
                        "Saving Profile files...",
                        current=total_entities,
                        total=total_entities,
                    )

                if state.enable_reddit:
                    generator.save_profiles(
                        profiles=profiles, file_path=os.path.join(sim_dir, "reddit_profiles.json"), platform="reddit"
                    )

                if state.enable_twitter:
                    generator.save_profiles(
                        profiles=profiles, file_path=os.path.join(sim_dir, "twitter_profiles.csv"), platform="twitter"
                    )

                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        100,
                        f"Done, {len(profiles)} profiles total",
                        current=len(profiles),
                        total=len(profiles),
                    )

            # ========== Phase 3: LLM intelligent simulation config generation ==========
            if progress_callback:
                progress_callback("generating_config", 0, "Analyzing simulation requirements...", current=0, total=3)

            config_generator = SimulationConfigGenerator()

            if progress_callback:
                progress_callback("generating_config", 30, "Calling LLM to generate config...", current=1, total=3)

            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=entities_for_config,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit,
                time_scale_override=time_scale_override,
            )

            if progress_callback:
                progress_callback("generating_config", 70, "Saving config file...", current=2, total=3)

            # Save config file
            config_path = os.path.join(sim_dir, "simulation_config.json")
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(sim_params.to_json())
            except (OSError, TypeError) as e:
                logger.error(
                    "Failed to save simulation config for %s at %s: %s",
                    simulation_id,
                    config_path,
                    e,
                )
                state.error = f"Failed to save simulation config: {e}"
                raise RuntimeError(state.error) from e

            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning

            if progress_callback:
                progress_callback("generating_config", 100, "Config generation complete", current=3, total=3)

            # Note: Run scripts stay in backend/scripts/, no longer copied to simulation dir
            # When starting simulation, simulation_runner runs scripts from scripts/ directory

            # Update state
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)

            logger.info(
                f"Simulation preparation complete: {simulation_id}, "
                f"entities={state.entities_count}, profiles={state.profiles_count}"
            )

            return state

        except Exception as e:
            logger.error(f"Simulation preparation failed: {simulation_id}, error={str(e)}")
            import traceback

            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise

    MAX_REPRESENTATIVE_VOICES = 15

    def _create_representative_voices(
        self,
        reader: ZepEntityReader,
        graph_id: str,
        existing_names: set[str],
        remaining_slots: int,
        typed_entity_types: list[str],
        progress_callback: Callable | None = None,
    ) -> list[EntityNode]:
        """Classify high-connectivity untyped nodes and create synthetic voice entities.

        Uses a single LLM call to batch-classify which untyped concepts should become
        domain-expert commentator agents in the simulation.
        """
        if progress_callback:
            progress_callback("reading", 85, "Scanning untyped nodes for representative voices...")

        untyped = reader.get_untyped_entities(
            graph_id=graph_id,
            min_connections=3,
            exclude_names=existing_names,
        )
        if not untyped:
            logger.info("No qualifying untyped nodes found for representative voices")
            return []

        voice_cap = min(self.MAX_REPRESENTATIVE_VOICES, remaining_slots)
        candidates = untyped[: voice_cap * 2]

        candidate_list = []
        for node in candidates:
            candidate_list.append(
                {
                    "name": node.name,
                    "summary": (node.summary or "")[:200],
                    "connections": len(node.related_edges),
                }
            )

        typed_names_str = ", ".join(typed_entity_types[:10])
        prompt = (
            "You are classifying entities for a social media opinion simulation.\n\n"
            f"The simulation already has typed agents for these entity types: {typed_names_str}\n\n"
            "Below are UNTYPED graph nodes that were not classified into any type. "
            "For each, decide whether it would add value to the simulation as a "
            "'representative voice' — a domain expert or analyst who comments on this topic.\n\n"
            "Rules:\n"
            "- Mark as 'voice' if the concept represents a real-world domain where an expert "
            "commentator would add unique perspective (e.g., 'oil markets' -> petroleum analyst)\n"
            "- Mark as 'skip' if the concept is too abstract, already well-covered by typed agents, "
            "or would not meaningfully contribute to the simulation\n"
            "- For 'voice' verdicts, provide a specific expert_role (e.g., 'petroleum industry analyst', "
            "'sanctions policy expert', 'cybersecurity researcher')\n\n"
            "Candidates:\n"
        )
        for c in candidate_list:
            prompt += f"- {c['name']} ({c['connections']} connections): {c['summary']}\n"

        prompt += '\nReturn JSON: {"verdicts": [{"name": "...", "verdict": "voice"|"skip", "expert_role": "..."}]}'

        try:
            llm = LLMClient()
            verdicts_raw = llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )
            verdicts = verdicts_raw.get("verdicts", [])
        except Exception as e:
            logger.warning(f"Voice classification LLM call failed, skipping: {e}")
            return []

        if not isinstance(verdicts, list):
            logger.error("LLM returned non-list verdicts: %s. Skipping representative voices.", type(verdicts))
            return []

        voice_map = {}
        for v in verdicts:
            if not isinstance(v, dict):
                logger.warning("Skipping non-dict verdict entry: %s", v)
                continue
            if v.get("verdict") == "voice" and v.get("name"):
                voice_map[v["name"].strip().lower()] = v.get("expert_role", "domain analyst")

        voice_entities: list[EntityNode] = []
        for node in candidates:
            if len(voice_entities) >= voice_cap:
                break
            role = voice_map.get(node.name.strip().lower())
            if not role:
                continue

            synthetic = EntityNode(
                uuid=node.uuid,
                name=node.name,
                labels=["Entity", "RepresentativeVoice"],
                summary=node.summary,
                attributes={**node.attributes, "expert_role": role},
                related_edges=node.related_edges,
                related_nodes=node.related_nodes,
            )
            voice_entities.append(synthetic)

        logger.info(
            f"Representative voices: {len(voice_entities)} created from {len(candidates)} candidates (cap={voice_cap})"
        )
        return voice_entities

    def get_simulation(self, simulation_id: str) -> SimulationState | None:
        """Get simulation state"""
        return self._load_simulation_state(simulation_id)

    def list_simulations(self, project_id: str | None = None) -> list[SimulationState]:
        """List all simulations"""
        simulations = []

        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Skip hidden files (e.g. .DS_Store) and non-directory files
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith(".") or not os.path.isdir(sim_path):
                    continue

                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)

        return simulations

    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> list[dict[str, Any]]:
        """Get simulation Agent Profile"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        platform = str(platform).lower()
        sim_dir = self._get_simulation_dir(simulation_id)
        if platform == "twitter":
            profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
            if not os.path.exists(profile_path):
                return []
            try:
                with open(profile_path, encoding="utf-8", newline="") as f:
                    return list(csv.DictReader(f))
            except (OSError, csv.Error) as e:
                logger.error(
                    "Failed to load Twitter profiles CSV for %s at %s: %s",
                    simulation_id,
                    profile_path,
                    e,
                )
                return []

        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")

        if not os.path.exists(profile_path):
            return []

        try:
            with open(profile_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Failed to load profiles for %s at %s: %s",
                simulation_id,
                profile_path,
                e,
            )
            return []

    def get_simulation_config(self, simulation_id: str) -> dict[str, Any] | None:
        """Load simulation_config.json for a simulation.

        Returns:
            None if the config file is missing.
            A dict of config data if the file exists and parses successfully.
            An empty dict {} if the file exists but cannot be read or parsed (I/O or JSON error);
            callers must treat {} as load failure, not as a valid empty config — distinguish from None.
        """
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if not os.path.exists(config_path):
            return None

        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Failed to load simulation config for %s at %s: %s",
                simulation_id,
                config_path,
                e,
            )
            return {}

    def get_run_instructions(self, simulation_id: str) -> dict[str, str]:
        """Get run instructions"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))

        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Activate conda env: conda activate glas\n"
                f"2. Run simulation (scripts in {scripts_dir}):\n"
                f"   - Twitter only: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Reddit only: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Both platforms in parallel: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            ),
        }
