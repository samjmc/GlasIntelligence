"""
Intelligent Simulation Configuration Generator
Uses LLM to automatically generate detailed simulation parameters based on simulation requirements,
document content, and graph information. Fully automated, no manual parameter setting required.

Uses a step-by-step generation strategy to avoid failures from generating overly long content at once:
1. Generate time configuration
2. Generate event configuration
3. Generate Agent configurations in batches
4. Generate platform configuration
"""

import json
import math
from typing import Any
from collections.abc import Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode

logger = get_logger("glas.simulation_config")


@dataclass
class AgentActivityConfig:
    """Activity configuration for a single Agent"""

    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str

    # Activity level (0.0-1.0)
    activity_level: float = 0.5  # Overall activity level

    # Posting frequency (expected posts per round)
    posts_per_round: float = 1.0
    comments_per_round: float = 2.0

    # Active hours (24-hour format, 0-23)
    active_hours: list[int] = field(default_factory=lambda: list(range(8, 23)))

    # Response speed (reaction delay to trending events, in simulated minutes)
    response_delay_min: int = 5
    response_delay_max: int = 60

    # Sentiment bias (-1.0 to 1.0, negative to positive)
    sentiment_bias: float = 0.0

    # Stance (attitude toward specific topics)
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # Influence weight (determines probability of posts being seen by other Agents)
    influence_weight: float = 1.0

    # Tool role for agent tool assignment (leader, diplomat, analyst, operative, observer, none)
    tool_role: str = "none"


@dataclass
class TimeScale:
    """Flexible time granularity — how much simulated time one round represents."""

    unit: str = "hour"  # "hour" | "day" | "week" | "month" | "year"
    per_round: int = 1  # units per round (e.g., 1 month per round)
    total_duration: int = 72  # total units (e.g., 60 months)
    start_date: str = ""  # ISO date anchor, e.g. "2026-04-01"


@dataclass
class ScenarioPhase:
    """A named phase of the simulation arc with its own activity multiplier."""

    name: str  # e.g. "Initial Reaction", "Escalation"
    start_round: int
    end_round: int
    activity_multiplier: float  # global volume multiplier during this phase


@dataclass
class TimeSimulationConfig:
    """Time simulation configuration (based on China timezone activity patterns)"""

    # Total simulation duration (in simulated hours)
    total_simulation_hours: int = 72  # Default: simulate 72 hours (3 days)

    # Time per round (simulated minutes) - default 60 minutes (1 hour), accelerated time flow
    minutes_per_round: int = 60

    # Range of Agents activated per round
    agents_per_round_min: int = 5
    agents_per_round_max: int = 20

    # Peak hours (19-22, most active time in China)
    peak_hours: list[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5

    # Off-peak hours (midnight 0-5am, almost no activity)
    off_peak_hours: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Extremely low activity in early morning

    # Morning hours
    morning_hours: list[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4

    # Working hours
    work_hours: list[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7

    # Flexible time scale (when unit != "hour", overrides hour-based scheduling)
    time_scale: TimeScale = field(default_factory=TimeScale)

    # Scenario phases (used at coarse time scales instead of peak/off-peak hours)
    phases: list[ScenarioPhase] = field(default_factory=list)


@dataclass
class EventConfig:
    """Event configuration"""

    # Initial events (trigger events at simulation start)
    initial_posts: list[dict[str, Any]] = field(default_factory=list)

    # Scheduled events (triggered at specific times)
    scheduled_events: list[dict[str, Any]] = field(default_factory=list)

    # Hot topic keywords
    hot_topics: list[str] = field(default_factory=list)

    # Narrative direction for public discourse
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Platform-specific configuration"""

    platform: str  # twitter or reddit

    # Recommendation algorithm weights
    recency_weight: float = 0.4  # Recency
    popularity_weight: float = 0.3  # Popularity
    relevance_weight: float = 0.3  # Relevance

    # Viral threshold (number of interactions to trigger viral spread)
    viral_threshold: int = 10

    # Echo chamber strength (degree of similar viewpoint clustering)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Complete simulation parameter configuration"""

    # Basic information
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str

    # Time configuration
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)

    # Agent configuration list
    agent_configs: list[AgentActivityConfig] = field(default_factory=list)

    # Event configuration
    event_config: EventConfig = field(default_factory=EventConfig)

    # Platform configuration
    twitter_config: PlatformConfig | None = None
    reddit_config: PlatformConfig | None = None

    # LLM configuration
    llm_model: str = ""
    llm_base_url: str = ""

    # Agent tools
    enable_agent_tools: bool = field(default_factory=lambda: Config.ENABLE_AGENT_TOOLS)

    # Generation metadata
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM reasoning explanation

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "enable_agent_tools": self.enable_agent_tools,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Intelligent Simulation Configuration Generator

    Uses LLM to analyse simulation requirements, document content, and graph entity information
    to automatically generate optimal simulation parameter configuration

    Step-by-step generation strategy:
    1. Generate time and event configurations (lightweight)
    2. Generate Agent configurations in batches (10-20 per batch)
    3. Generate platform configuration
    """

    # Maximum context character count
    MAX_CONTEXT_LENGTH = 50000
    # Number of Agents per batch
    AGENTS_PER_BATCH = 15

    # Context truncation length per step (character count)
    TIME_CONFIG_CONTEXT_LENGTH = 10000  # Time configuration
    EVENT_CONFIG_CONTEXT_LENGTH = 8000  # Event configuration
    ENTITY_SUMMARY_LENGTH = 300  # Entity summary
    AGENT_SUMMARY_LENGTH = 300  # Entity summary in Agent configuration
    ENTITIES_PER_TYPE_DISPLAY = 20  # Number of entities displayed per type

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model_name: str | None = None):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: list[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
        time_scale_override: dict | None = None,
    ) -> SimulationParameters:
        """
        Intelligently generate complete simulation configuration (step-by-step)

        Args:
            simulation_id: Simulation ID
            project_id: Project ID
            graph_id: Graph ID
            simulation_requirement: Simulation requirement description
            document_text: Original document content
            entities: Filtered entity list
            enable_twitter: Whether to enable Twitter
            enable_reddit: Whether to enable Reddit
            progress_callback: Progress callback function(current_step, total_steps, message)

        Returns:
            SimulationParameters: Complete simulation parameters
        """
        logger.info(
            f"Starting intelligent simulation config generation: simulation_id={simulation_id}, entity_count={len(entities)}"
        )

        # Calculate total steps
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Time config + event config + N Agent batches + platform config
        current_step = 0

        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")

        # 1. Build base context information
        num_entities = len(entities)
        type_dist = self._compute_entity_type_distribution(entities)
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities,
            type_dist=type_dist,
        )

        reasoning_parts = []

        # ========== Step 1: Generate time configuration ==========
        _ts_override = time_scale_override
        if _ts_override is not None and not isinstance(_ts_override, dict):
            _ts_override = {}
        if _ts_override:
            report_progress(1, "Using locked time configuration from first scenario...")
            time_config = self._parse_time_config(
                _ts_override,
                num_entities,
                type_dist,
                context,
                skip_geopolitical_time_retry=True,
            )
            reasoning_parts.append("Time config: Locked to first scenario's time scale for bundle consistency")
        else:
            report_progress(1, "Generating time configuration...")
            time_config_result = self._generate_time_config(context, num_entities, type_dist)
            time_config = self._parse_time_config(time_config_result, num_entities, type_dist, context)
            # Honor OASIS_DEFAULT_MAX_ROUNDS: clamp the LLM's chosen duration so
            # the run stays within a bounded round budget. total_rounds derives
            # from total_simulation_hours * 60 / minutes_per_round.
            from ..config import Config

            max_rounds = Config.OASIS_DEFAULT_MAX_ROUNDS
            minutes_per_round = max(int(time_config.minutes_per_round or 60), 30)
            hours_for_max = max_rounds * minutes_per_round / 60
            if int(time_config.total_simulation_hours or 72) > hours_for_max:
                time_config = TimeSimulationConfig(
                    **{**asdict(time_config), "total_simulation_hours": int(hours_for_max)}
                )
                reasoning_parts.append(
                    f"Capped to {max_rounds} rounds (OASIS_DEFAULT_MAX_ROUNDS={max_rounds})"
                )
            reasoning_parts.append(f"Time config: {time_config_result.get('reasoning', 'Success')}")

        # ========== Step 2: Generate event configuration ==========
        report_progress(2, "Generating event configuration and hot topics...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"Event config: {event_config_result.get('reasoning', 'Success')}")

        # ========== Steps 3-N: Generate Agent configurations in batches ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]

            report_progress(3 + batch_idx, f"Generating Agent configs ({start_idx + 1}-{end_idx}/{len(entities)})...")

            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement,
                time_scale_unit=time_config.time_scale.unit,
            )
            all_agent_configs.extend(batch_configs)

        reasoning_parts.append(f"Agent config: Successfully generated {len(all_agent_configs)}")

        # ========== Assign tool roles to Agents ==========
        if Config.ENABLE_AGENT_TOOLS:
            try:
                from .simulation_tools import assign_tool_roles

                agent_dicts = [asdict(ac) for ac in all_agent_configs]
                role_map = assign_tool_roles(agent_dicts, simulation_requirement)
                for ac in all_agent_configs:
                    ac.tool_role = role_map.get(ac.agent_id, "none")
                role_counts = {}
                for r in role_map.values():
                    role_counts[r] = role_counts.get(r, 0) + 1
                reasoning_parts.append(f"Tool roles: {role_counts}")
                logger.info(f"Tool roles assigned: {role_counts}")
            except Exception as e:
                logger.warning(f"Tool role assignment failed (non-fatal): {e}")
                reasoning_parts.append("Tool roles: skipped (error)")

        # ========== Assign publisher Agents to initial posts ==========
        logger.info("Assigning suitable publisher Agents to initial posts...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"Initial post assignment: {assigned_count} posts assigned to publishers")

        # ========== Final step: Generate platform configuration ==========
        report_progress(total_steps, "Generating platform configuration...")
        twitter_config = None
        reddit_config = None

        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5,
            )

        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6,
            )

        # Build final parameters
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts),
        )

        logger.info(f"Simulation config generation complete: {len(params.agent_configs)} Agent configs")

        return params

    GEOPOLITICAL_ENTITY_TYPES = frozenset(
        {
            "sovereign",
            "internationalorganization",
            "governmentbody",
            "militaryforce",
            "politicalparty",
            "governmentagency",
            "tradepartner",
            "tradebloc",
            "state",
            "country",
            "nation",
            "ministry",
            "foreignministry",
            "defenseagency",
            "securitycouncil",
            "intergovernmentalbody",
            "diplomaticmission",
            "government",
        }
    )

    @staticmethod
    def _normalize_type_name(t: str) -> str:
        import re

        return re.sub(r"[\s_\-]+", "", t).lower()

    @staticmethod
    def _compute_entity_type_distribution(entities: list[EntityNode]) -> dict[str, list[str]]:
        """Return {type: [entity_names]} grouped by entity type."""
        by_type: dict[str, list[str]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            by_type.setdefault(t, []).append(e.name)
        return by_type

    @staticmethod
    def _is_geopolitical_heavy(type_dist: dict[str, list[str]]) -> bool:
        """True when the majority of entities are geopolitical actor types."""
        geo_count = sum(
            len(names)
            for t, names in type_dist.items()
            if SimulationConfigGenerator._normalize_type_name(t) in SimulationConfigGenerator.GEOPOLITICAL_ENTITY_TYPES
        )
        total = sum(len(names) for names in type_dist.values())
        return total > 0 and geo_count / total >= 0.5

    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: list[EntityNode],
        type_dist: dict[str, list[str]] | None = None,
    ) -> str:
        """Build LLM context, truncated to maximum length"""

        if type_dist is None:
            type_dist = self._compute_entity_type_distribution(entities)

        type_dist_lines = []
        for t, names in type_dist.items():
            preview = ", ".join(names[:5])
            if len(names) > 5:
                preview += f" ... (+{len(names) - 5} more)"
            type_dist_lines.append(f"- {t}: {len(names)} ({preview})")
        type_dist_section = "\n".join(type_dist_lines)

        entity_summary = self._summarize_entities(entities)

        context_parts = [
            f"## Simulation Requirement\n{simulation_requirement}",
            f"\n## Entity Type Distribution ({len(entities)} entities)\n{type_dist_section}",
            f"\n## Entity Details\n{entity_summary}",
        ]

        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500

        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(document truncated)"
            context_parts.append(f"\n## Original Document Content\n{doc_text}")

        return "\n".join(context_parts)

    def _summarize_entities(self, entities: list[EntityNode]) -> str:
        """Generate entity summary"""
        lines = []

        # Group by type
        by_type: dict[str, list[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)

        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)} entities)")
            # Use configured display count and summary length
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... and {len(type_entities) - display_count} more")

        return "\n".join(lines)

    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        """LLM call with retry and JSON repair logic"""

        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1),  # Lower temperature on each retry
                    # No max_tokens set, letting the LLM generate freely
                )

                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

                # Check if output was truncated
                if finish_reason == "length":
                    logger.warning(f"LLM output truncated (attempt {attempt + 1})")
                    content = self._fix_truncated_json(content)

                # Try to parse JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed (attempt {attempt + 1}): {str(e)[:80]}")

                    # Try to fix JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed

                    last_error = e

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt + 1}): {str(e)[:80]}")
                last_error = e
                import time

                time.sleep(2 * (attempt + 1))

        raise last_error or Exception("LLM call failed")

    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON"""
        content = content.strip()

        # Count unclosed brackets
        open_braces = content.count("{") - content.count("}")
        open_brackets = content.count("[") - content.count("]")

        # Check for unclosed strings
        if content and content[-1] not in '",}]':
            content += '"'

        # Close brackets
        content += "]" * open_brackets
        content += "}" * open_braces

        return content

    def _try_fix_config_json(self, content: str) -> dict[str, Any] | None:
        """Attempt to fix configuration JSON"""
        import re

        # Fix truncation
        content = self._fix_truncated_json(content)

        # Extract JSON portion
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            json_str = json_match.group()

            # Remove newlines from strings
            def fix_string(match):
                s = match.group(0)
                s = s.replace("\n", " ").replace("\r", " ")
                s = re.sub(r"\s+", " ", s)
                return s

            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)

            try:
                return json.loads(json_str)
            except Exception:
                # Try removing all control characters
                json_str = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", json_str)
                json_str = re.sub(r"\s+", " ", json_str)
                try:
                    return json.loads(json_str)
                except Exception:
                    pass

        return None

    def _generate_time_config(
        self,
        context: str,
        num_entities: int,
        type_dist: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Generate time configuration with scenario-aware guidance."""
        context_truncated = context[: self.TIME_CONFIG_CONTEXT_LENGTH]

        max_agents_allowed = max(1, int(num_entities * 0.9))

        type_dist_block = ""
        if type_dist:
            lines = [f"- {t}: {len(names)} ({', '.join(names[:4])})" for t, names in type_dist.items()]
            type_dist_block = "\n## Entity Type Distribution\n" + "\n".join(lines)

        prompt = f"""Based on the following simulation requirements, generate a time simulation configuration.

{context_truncated}
{type_dist_block}

## Task
You MUST classify the scenario first, then choose the time scale, then generate the configuration.

### Step 0: Classify the scenario (THINK BEFORE CHOOSING)
Estimate how long this scenario would realistically play out in the real world.

**Entity type signals:**
- Nation-states, sovereigns, international organisations, military forces, trade blocs, government bodies → the scenario likely spans **weeks to years**
- Media outlets, social media users, individuals, students → the scenario likely spans **hours to days**
- Companies, products, markets, industry bodies → the scenario likely spans **days to weeks**

**Scenario keyword signals:**
- War, conflict, invasion, sanctions, diplomacy, geopolitical, treaty, alliance, embargo, territorial → **months or years**
- Breaking news, viral event, policy announcement, scandal, immediate reaction → **hours or days**
- Product launch, campaign, regulatory rollout, market entry → **days or weeks**

Use these signals together. If entities are nation-states discussing a war scenario, "hour" is almost certainly wrong — use "week" or "month".

### Step 1: Choose time scale
Based on your classification above, pick the granularity:
- "hour" — ONLY for short-term reactions (< 1 week). Each round = 1 hour of simulated time.
- "day" — for multi-week scenarios (1–8 weeks). Each round = 1 day.
- "week" — for multi-month scenarios (2–12 months). Each round = 1 week.
- "month" — for multi-year scenarios (1–10 years). Each round = 1 month.
- "year" — for decade-scale scenarios (10+ years). Each round = 1 year.

### Step 2: Configure accordingly

**If time_scale.unit is "hour"** (short-term):
- Provide hour-of-day scheduling fields: peak_hours, off_peak_hours, morning_hours, work_hours
- Set total_simulation_hours and minutes_per_round
- Do NOT provide "phases"

**If time_scale.unit is "day" or coarser** (long-term):
- Provide "phases" — 2-4 named phases of the scenario arc with activity multipliers
- Set time_scale.total_duration to the number of units (e.g., 60 for 60 months)
- Hour-based fields (peak_hours etc.) are ignored — set them to empty arrays
- Provide a start_date anchoring when the scenario begins (ISO format)

### Return JSON format (no markdown)

Example A (monthly — geopolitical conflict between nation-states):
{{
    "time_scale": {{ "unit": "month", "per_round": 1, "total_duration": 60, "start_date": "2026-01-01" }},
    "total_simulation_hours": 60,
    "minutes_per_round": 60,
    "agents_per_round_min": {max(1, num_entities // 5)},
    "agents_per_round_max": {max(3, num_entities)},
    "peak_hours": [],
    "off_peak_hours": [],
    "morning_hours": [],
    "work_hours": [],
    "phases": [
        {{ "name": "Initial Reaction", "start_round": 1, "end_round": 10, "activity_multiplier": 1.5 }},
        {{ "name": "Escalation", "start_round": 11, "end_round": 35, "activity_multiplier": 1.0 }},
        {{ "name": "Resolution", "start_round": 36, "end_round": 60, "activity_multiplier": 0.6 }}
    ],
    "reasoning": "Entities are nation-states and international orgs. Geopolitical conflict unfolds over years; monthly granularity captures strategic shifts."
}}

Example B (weekly — trade policy rollout over several months):
{{
    "time_scale": {{ "unit": "week", "per_round": 1, "total_duration": 26, "start_date": "2026-04-01" }},
    "total_simulation_hours": 26,
    "minutes_per_round": 60,
    "agents_per_round_min": {max(1, num_entities // 5)},
    "agents_per_round_max": {max(3, num_entities)},
    "peak_hours": [],
    "off_peak_hours": [],
    "morning_hours": [],
    "work_hours": [],
    "phases": [
        {{ "name": "Announcement & Reaction", "start_round": 1, "end_round": 4, "activity_multiplier": 1.5 }},
        {{ "name": "Implementation", "start_round": 5, "end_round": 18, "activity_multiplier": 1.0 }},
        {{ "name": "Adjustment", "start_round": 19, "end_round": 26, "activity_multiplier": 0.7 }}
    ],
    "reasoning": "Trade policy changes play out over months; weekly granularity captures negotiation cycles."
}}

Example C (hourly — breaking news / immediate social media reaction):
{{
    "time_scale": {{ "unit": "hour", "per_round": 1, "total_duration": 72, "start_date": "" }},
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_round_min": 5,
    "agents_per_round_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "phases": [],
    "reasoning": "Short-term social media reaction to breaking news; hourly granularity captures real-time discourse."
}}

Field descriptions:
- time_scale.unit (string): "hour", "day", "week", "month", or "year"
- time_scale.per_round (int): How many units per round (usually 1)
- time_scale.total_duration (int): Total number of units to simulate
- time_scale.start_date (string): ISO date when the scenario begins (empty string if not anchored)
- total_simulation_hours (int): For hourly mode: 24-168. For coarse mode: set equal to time_scale.total_duration
- minutes_per_round (int): For hourly mode: 30-120. For coarse mode: set to 60 (ignored)
- agents_per_round_min (int): Min agents per round (range: 1-{max_agents_allowed})
- agents_per_round_max (int): Max agents per round (range: 1-{max_agents_allowed})
- peak_hours, off_peak_hours, morning_hours, work_hours: Hour-of-day arrays (hourly mode only; empty for coarse)
- phases (array): Scenario phases with name, start_round, end_round, activity_multiplier (coarse mode only; empty for hourly)
- reasoning (string): First state your scenario classification and real-world duration estimate, then explain the chosen unit"""

        system_prompt = (
            "You are a simulation design expert. Return pure JSON format. "
            "IMPORTANT: First classify the scenario based on entity types and keywords, "
            "then choose the appropriate time granularity. Do NOT default to hourly — "
            "carefully consider the scenario duration. All output must be in English."
        )

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Time config LLM generation failed: {e}, using defaults")
            return self._get_default_time_config(num_entities, type_dist)

    def _get_default_time_config(
        self,
        num_entities: int,
        type_dist: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Get default time configuration, choosing coarser defaults for geopolitical scenarios."""
        if type_dist and self._is_geopolitical_heavy(type_dist):
            return {
                "time_scale": {"unit": "week", "per_round": 1, "total_duration": 52, "start_date": ""},
                "total_simulation_hours": 52,
                "minutes_per_round": 60,
                "agents_per_round_min": max(1, num_entities // 5),
                "agents_per_round_max": max(3, num_entities),
                "peak_hours": [],
                "off_peak_hours": [],
                "morning_hours": [],
                "work_hours": [],
                "phases": [
                    {"name": "Initial Phase", "start_round": 1, "end_round": 13, "activity_multiplier": 1.5},
                    {"name": "Development", "start_round": 14, "end_round": 39, "activity_multiplier": 1.0},
                    {"name": "Stabilisation", "start_round": 40, "end_round": 52, "activity_multiplier": 0.6},
                ],
                "reasoning": "Default: geopolitical actors detected, using weekly time scale (52 weeks)",
            }
        return {
            "time_scale": {"unit": "hour", "per_round": 1, "total_duration": 72, "start_date": ""},
            "total_simulation_hours": 72,
            "minutes_per_round": 60,
            "agents_per_round_min": max(1, num_entities // 15),
            "agents_per_round_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "phases": [],
            "reasoning": "Default: using hourly activity schedule",
        }

    def _parse_time_config(
        self,
        result: dict[str, Any],
        num_entities: int,
        type_dist: dict[str, list[str]] | None = None,
        context: str = "",
        *,
        skip_geopolitical_time_retry: bool = False,
    ) -> TimeSimulationConfig:
        """Parse time configuration result, validate, and optionally retry LLM if mismatch detected."""
        agents_per_round_min = result.get(
            "agents_per_round_min", result.get("agents_per_hour_min", max(1, num_entities // 15))
        )
        agents_per_round_max = result.get(
            "agents_per_round_max", result.get("agents_per_hour_max", max(5, num_entities // 5))
        )

        if agents_per_round_min > num_entities:
            logger.warning(
                f"agents_per_round_min ({agents_per_round_min}) exceeds total Agent count ({num_entities}), corrected"
            )
            agents_per_round_min = max(1, num_entities // 10)

        if agents_per_round_max > num_entities:
            logger.warning(
                f"agents_per_round_max ({agents_per_round_max}) exceeds total Agent count ({num_entities}), corrected"
            )
            agents_per_round_max = min(num_entities, max(agents_per_round_min + 1, num_entities // 2))

        if agents_per_round_min >= agents_per_round_max:
            agents_per_round_min = max(1, agents_per_round_max // 2)
            logger.warning(f"agents_per_round_min >= max, corrected to {agents_per_round_min}")

        ts_raw = result.get("time_scale", {})
        if not isinstance(ts_raw, dict):
            ts_raw = {}
        unit = ts_raw.get("unit", "hour")
        valid_units = ("hour", "day", "week", "month", "year")
        if unit not in valid_units:
            logger.warning(f"Invalid time_scale unit '{unit}', defaulting to 'hour'")
            unit = "hour"

        # Heuristic: if entities are geopolitical but LLM chose hourly, retry once (not for bundle-locked config)
        if not skip_geopolitical_time_retry and unit == "hour" and type_dist and self._is_geopolitical_heavy(type_dist):
            logger.warning(
                "LLM chose 'hour' but entity distribution is geopolitical-heavy — retrying with stronger guidance"
            )
            retry_result = self._retry_time_config_for_geopolitical(result, type_dist, num_entities, context)
            if retry_result:
                rr_ts = retry_result.get("time_scale", {})
                if not isinstance(rr_ts, dict):
                    rr_ts = {}
                retry_unit = rr_ts.get("unit", "hour")
                if retry_unit in valid_units and retry_unit != "hour":
                    logger.info(f"Retry succeeded: LLM changed time scale to '{retry_unit}'")
                    # type_dist=None suppresses a second retry loop
                    return self._parse_time_config(retry_result, num_entities, type_dist=None)
                else:
                    logger.info(f"Retry returned '{retry_unit}' (not a valid non-hourly unit) — keeping original")

        time_scale = TimeScale(
            unit=unit,
            per_round=max(1, ts_raw.get("per_round", 1)),
            total_duration=ts_raw.get("total_duration", result.get("total_simulation_hours", 72)),
            start_date=ts_raw.get("start_date", ""),
        )

        phases_raw = result.get("phases", [])
        phases = []
        for p in phases_raw:
            if isinstance(p, dict) and "name" in p:
                phases.append(
                    ScenarioPhase(
                        name=p["name"],
                        start_round=p.get("start_round", 1),
                        end_round=p.get("end_round", time_scale.total_duration),
                        activity_multiplier=max(0.1, min(3.0, p.get("activity_multiplier", 1.0))),
                    )
                )

        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),
            agents_per_round_min=agents_per_round_min,
            agents_per_round_max=agents_per_round_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5,
            time_scale=time_scale,
            phases=phases,
        )

    def _retry_time_config_for_geopolitical(
        self,
        original_result: dict[str, Any],
        type_dist: dict[str, list[str]],
        num_entities: int,
        context: str = "",
    ) -> dict[str, Any] | None:
        """Re-call the LLM with explicit geopolitical nudge when hourly was chosen inappropriately."""
        type_summary = ", ".join(f"{t} ({len(n)})" for t, n in type_dist.items())
        original_reasoning = original_result.get("reasoning", "none given")
        max_agents = max(1, int(num_entities * 0.9))

        context_snippet = context[: self.TIME_CONFIG_CONTEXT_LENGTH] if context else "(no context available)"

        prompt = f"""You previously chose "hour" as the time scale for a simulation, but the entity distribution
suggests this is a geopolitical scenario that unfolds over a longer time horizon.

## Simulation Context
{context_snippet}

## Entity Type Distribution
{type_summary}

## Your Original Choice
You chose unit="hour" with reasoning: "{original_reasoning}"

## Problem
These entities are primarily nation-states, international organisations, and government bodies.
Scenarios involving these actor types typically unfold over weeks, months, or years — not hours.

RECONSIDER your time scale choice. If you still believe "hour" is correct (e.g., the scenario
explicitly asks about the first 24-48 hours of immediate reactions), you may keep it.
Otherwise, choose "week" or "month" and regenerate the full time configuration.

## Required JSON format (return this exact structure, no markdown)
{{
    "time_scale": {{ "unit": "<hour|day|week|month|year>", "per_round": 1, "total_duration": <int>, "start_date": "<ISO date or empty>" }},
    "total_simulation_hours": <int: for hourly=24-168, for coarse=same as total_duration>,
    "minutes_per_round": <int: 60 for coarse, 30-120 for hourly>,
    "agents_per_round_min": <int: 1-{max_agents}>,
    "agents_per_round_max": <int: 1-{max_agents}>,
    "peak_hours": [<ints for hourly, empty [] for coarse>],
    "off_peak_hours": [<ints for hourly, empty [] for coarse>],
    "morning_hours": [<ints for hourly, empty [] for coarse>],
    "work_hours": [<ints for hourly, empty [] for coarse>],
    "phases": [<phase objects for coarse, empty [] for hourly>],
    "reasoning": "<your revised explanation>"
}}"""

        system_prompt = (
            "You are a simulation design expert reconsidering a time scale choice. "
            "Return pure JSON. All output must be in English."
        )

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Time config retry LLM call failed: {e}")
            return None

    def _generate_event_config(
        self, context: str, simulation_requirement: str, entities: list[EntityNode]
    ) -> dict[str, Any]:
        """Generate event configuration"""

        # Get available entity types for LLM reference
        entity_types_available = list(set(e.get_entity_type() or "Unknown" for e in entities))

        # List representative entity names for each type
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)

        type_info = "\n".join([f"- {t}: {', '.join(examples)}" for t, examples in type_examples.items()])

        # Use configured context truncation length
        context_truncated = context[: self.EVENT_CONFIG_CONTEXT_LENGTH]

        prompt = f"""Based on the following simulation requirements, generate an event configuration.

Simulation requirement: {simulation_requirement}

{context_truncated}

## Available Entity Types and Examples
{type_info}

## Task
Generate an event configuration JSON:
- Extract hot topic keywords
- Describe the direction of public discourse
- Design initial post content. **Each post must specify a poster_type (publisher type)**

**Important**: poster_type MUST be selected from the "Available Entity Types" above, so initial posts can be assigned to appropriate agents.
For example: official statements should be published by Official/GovernmentBody types, news by MediaOutlet, professional opinions by relevant professional types.

All content MUST be in English.

Return JSON format (no markdown):
{{
    "hot_topics": ["keyword1", "keyword2", ...],
    "narrative_direction": "<description of discourse direction>",
    "initial_posts": [
        {{"content": "Post content in English", "poster_type": "Entity type (must be from available types)"}},
        ...
    ],
    "reasoning": "<brief explanation>"
}}"""

        system_prompt = "You are a public discourse analysis expert. Return pure JSON format. poster_type must exactly match available entity types. All content must be in English."

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Event config LLM generation failed: {e}, using defaults")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Using default configuration",
            }

    def _parse_event_config(self, result: dict[str, Any]) -> EventConfig:
        """Parse event configuration result"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", ""),
        )

    def _assign_initial_post_agents(
        self, event_config: EventConfig, agent_configs: list[AgentActivityConfig]
    ) -> EventConfig:
        """
        Assign suitable publisher Agents to initial posts

        Match the most appropriate agent_id based on each post's poster_type
        """
        if not event_config.initial_posts:
            return event_config

        # Build agent index by entity type
        agents_by_type: dict[str, list[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)

        # Type alias mapping (handles different formats LLM may output)
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }

        # Track used agent indices per type to avoid reusing the same agent
        used_indices: dict[str, int] = {}

        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")

            # Try to find a matching agent
            matched_agent_id = None

            # 1. Direct match
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Match using aliases
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break

            # 3. If still not found, use the agent with highest influence
            if matched_agent_id is None:
                logger.warning(f"No matching Agent found for type '{poster_type}', using highest influence Agent")
                if agent_configs:
                    # Sort by influence and select highest
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0

            updated_posts.append(
                {
                    "content": content,
                    "poster_type": post.get("poster_type", "Unknown"),
                    "poster_agent_id": matched_agent_id,
                }
            )

            logger.info(f"Initial post assignment: poster_type='{poster_type}' -> agent_id={matched_agent_id}")

        event_config.initial_posts = updated_posts
        return event_config

    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: list[EntityNode],
        start_idx: int,
        simulation_requirement: str,
        time_scale_unit: str = "hour",
    ) -> list[AgentActivityConfig]:
        """Generate Agent configurations in batches"""

        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append(
                {
                    "agent_id": start_idx + i,
                    "entity_name": e.name,
                    "entity_type": e.get_entity_type() or "Unknown",
                    "summary": e.summary[:summary_len] if e.summary else "",
                }
            )

        is_coarse = time_scale_unit != "hour"

        if is_coarse:
            time_guidance = f"""- This simulation uses **{time_scale_unit}ly** time granularity (1 round = 1 {time_scale_unit})
- Do NOT set active_hours — set it to an empty list []
- activity_level represents the probability of this entity acting each {time_scale_unit}
- **Key actors** (major governments, institutions): high activity (0.6-0.9), high influence (2.5-3.0)
- **Secondary actors** (media, analysts): medium activity (0.4-0.6), medium influence (1.5-2.5)
- **Minor actors** (individuals, observers): low activity (0.1-0.3), low influence (0.8-1.2)
- response_delay_min/max are not meaningful at this time scale — set both to 0"""
        else:
            time_guidance = """- **Time patterns should reflect the stakeholder demographics** in the simulation
- **Official bodies** (GovernmentBody/RegulatoryAgency): low activity (0.1-0.3), work hours (9-17), slow response (60-240 min), high influence (2.5-3.0)
- **Media** (MediaOutlet): medium activity (0.4-0.6), all-day activity (8-23), fast response (5-30 min), high influence (2.0-2.5)
- **Individuals** (Professional/Patient/Person): high activity (0.6-0.9), mainly evening activity (18-23), fast response (1-15 min), low influence (0.8-1.2)
- **Industry bodies/experts**: medium activity (0.4-0.6), medium-high influence (1.5-2.0)"""

        AGENT_CONTEXT_BUDGET = 4000
        context_section = ""
        if context and len(context) > len(simulation_requirement) + 100:
            trimmed = context[:AGENT_CONTEXT_BUDGET]
            if len(context) > AGENT_CONTEXT_BUDGET:
                trimmed += "\n...(truncated)"
            context_section = f"\n## Background Research & Context\n{trimmed}\n"

        prompt = f"""Based on the following information, generate activity configurations for each entity.

Simulation requirement: {simulation_requirement}
{context_section}
## Entity List
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Task
Generate activity configurations for each entity. Use the background research context to inform realistic stances, sentiment biases, and influence weights for each entity. Guidelines:
{time_guidance}

Return JSON format (no markdown):
{{
    "agent_configs": [
        {{
            "agent_id": <must match input>,
            "activity_level": <0.0-1.0>,
            "posts_per_round": <posting frequency per round>,
            "comments_per_round": <commenting frequency per round>,
            "active_hours": [<list of active hours, or empty [] for coarse time scales>],
            "response_delay_min": <min response delay in minutes>,
            "response_delay_max": <max response delay in minutes>,
            "sentiment_bias": <-1.0 to 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <influence weight>
        }},
        ...
    ]
}}"""

        system_prompt = "You are a social media behaviour analysis expert. Return pure JSON. Configure activity patterns appropriate for the stakeholder demographics. All output must be in English."

        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            raw = result.get("agent_configs", [])
            if not isinstance(raw, list):
                raw = []
            valid_cfgs = [cfg for cfg in raw if isinstance(cfg, dict) and "agent_id" in cfg]
            dropped = len(raw) - len(valid_cfgs)
            if dropped:
                logger.warning(f"Dropped {dropped} invalid agent_config entr(y/ies) (non-dict or missing agent_id)")
            llm_configs = {cfg["agent_id"]: cfg for cfg in valid_cfgs}
        except Exception as e:
            logger.warning(f"Agent config batch LLM generation failed: {e}, falling back to rule-based")
            llm_configs = {}

        # Build AgentActivityConfig objects
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})

            # If LLM did not generate, use rule-based generation
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)

            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_round=cfg.get("posts_per_round", cfg.get("posts_per_hour", 0.5)),
                comments_per_round=cfg.get("comments_per_round", cfg.get("comments_per_hour", 1.0)),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0),
            )
            configs.append(config)

        return configs

    def _generate_agent_config_by_rule(self, entity: EntityNode) -> dict[str, Any]:
        """Generate a single Agent configuration using rules (China timezone activity patterns)"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()

        if entity_type in ["university", "governmentagency", "ngo"]:
            # Official institutions: active during work hours, low frequency, high influence
            return {
                "activity_level": 0.2,
                "posts_per_round": 0.1,
                "comments_per_round": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0,
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: active all day, moderate frequency, high influence
            return {
                "activity_level": 0.5,
                "posts_per_round": 0.8,
                "comments_per_round": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5,
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Experts/professors: work + evening activity, moderate frequency
            return {
                "activity_level": 0.4,
                "posts_per_round": 0.3,
                "comments_per_round": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0,
            }
        elif entity_type in ["student"]:
            # Students: mainly evening, high frequency
            return {
                "activity_level": 0.8,
                "posts_per_round": 0.6,
                "comments_per_round": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Morning + evening
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8,
            }
        elif entity_type in ["alumni"]:
            # Alumni: mainly evening
            return {
                "activity_level": 0.6,
                "posts_per_round": 0.4,
                "comments_per_round": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Lunch break + evening
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0,
            }
        else:
            # General public: evening peak
            return {
                "activity_level": 0.7,
                "posts_per_round": 0.5,
                "comments_per_round": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Daytime + evening
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0,
            }
