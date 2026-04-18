"""
Simulation Effect Engine

Applies mechanical state changes to the simulation based on agent tool
actions. When an agent calls a scenario tool (e.g. propose_sanction),
the tool queues one or more effects which are applied between rounds.

Supported mutations (validated in spike test):
- Config dict activity_level  -> changes scheduling probability (shared across platforms)
- SQLite follow table writes  -> changes what agents see in feeds (platform-isolated)
- AgentGraph edge mutations   -> keeps in-memory graph in sync (platform-isolated)
"""

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("glas.simulation_effects")

ACTIVITY_FLOOR = 0.1
ACTIVITY_CEILING = 1.0
MAX_MAGNITUDE = 0.7
COOLDOWN_ROUNDS = 5
MAX_FOLLOW_CHANGES_PER_ROUND = 10


class EffectType(str, Enum):
    SUPPRESS_AGENT = "suppress_agent"
    BOOST_AGENT = "boost_agent"
    CREATE_LINK = "create_link"
    BREAK_LINK = "break_link"
    BROADCAST = "broadcast"


@dataclass
class StateEffect:
    """A single queued state mutation awaiting application."""

    effect_type: EffectType
    actor_id: int
    target_id: int | None = None
    target_name: str = ""
    magnitude: float = 0.4
    direction: str = "actor_to_target"
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    round_num: int = 0
    platform: str = ""
    broadcast_message: str = ""


@dataclass
class AppliedEffect:
    """Record of a state mutation that was successfully applied."""

    round_num: int
    effect_type: str
    actor_id: int
    actor_name: str
    target_id: int
    target_name: str
    before: dict
    after: dict
    caused_by_tool: str
    tool_args: dict
    timestamp: str = ""


class EffectEngine:
    """Queues and applies state mutations between simulation rounds.

    Platform-aware: stores per-platform env/agent_graph so that follow/graph
    mutations go to the correct platform's DB, while activity_level changes
    (shared config dict) apply regardless of platform.
    """

    def __init__(
        self,
        config: dict[str, Any],
        agent_names: dict[int, str],
        log_dir: str,
    ):
        self._config = config
        self._agent_names = agent_names
        self._queue: list[StateEffect] = []
        self._lock = threading.Lock()
        self._applied: list[AppliedEffect] = []
        self._cooldowns: dict[str, int] = {}
        self._follow_changes: dict[str, int] = {}
        self._log_path = os.path.join(log_dir, "state_changes.jsonl")

        self._envs: dict[str, Any] = {}
        self._agent_graphs: dict[str, Any] = {}

        self._agent_config_by_id: dict[int, dict] = {}
        for ac in config.get("agent_configs", []):
            self._agent_config_by_id[ac["agent_id"]] = ac

        self._name_lookup = self._build_name_lookup()

    def set_env(self, env, agent_graph, platform: str):
        """Set OASIS env and agent graph for a specific platform."""
        self._envs[platform] = env
        self._agent_graphs[platform] = agent_graph

    def _build_name_lookup(self) -> dict[str, int]:
        """Build lowercase entity_name -> agent_id mapping for target resolution."""
        lookup = {}
        for ac in self._config.get("agent_configs", []):
            name = ac.get("entity_name", "")
            if name:
                lookup[name.lower()] = ac["agent_id"]
        return lookup

    def resolve_target(self, action_description: str) -> int | None:
        """Find which known entity name appears in the action_description.

        Scans the text for mentions of known entity names (longest-first
        to prefer specific matches over partial ones). Returns agent_id
        of the first match, or None if no entity is mentioned.
        """
        if not action_description:
            return None
        text_lower = action_description.lower()

        sorted_names = sorted(self._name_lookup.keys(), key=len, reverse=True)
        for name in sorted_names:
            if name in text_lower:
                return self._name_lookup[name]

        return None

    def queue(self, effect: StateEffect):
        with self._lock:
            self._queue.append(effect)

    def apply_pending(self, current_round: int, platform: str) -> list[AppliedEffect]:
        """Apply queued effects for a given platform. Call between rounds.

        Activity_level effects apply regardless of originating platform
        (shared config). Follow/graph effects only apply if the effect's
        platform matches the requested platform.
        """
        with self._lock:
            pending = list(self._queue)
            self._queue.clear()

        self._follow_changes[platform] = 0
        results = []

        for effect in pending:
            is_graph_effect = effect.effect_type in (EffectType.CREATE_LINK, EffectType.BREAK_LINK)
            if is_graph_effect and effect.platform and effect.platform != platform:
                with self._lock:
                    self._queue.append(effect)
                continue

            if effect.target_id is None and effect.target_name:
                effect.target_id = self.resolve_target(effect.target_name)
                if effect.target_id is None:
                    logger.warning(
                        f"Could not resolve target from '{effect.target_name[:80]}' "
                        f"for {effect.effect_type} from {effect.tool_name}"
                    )
                    continue

            if effect.target_id is None and effect.effect_type != EffectType.BROADCAST:
                continue

            cooldown_key = f"{effect.effect_type}:{effect.actor_id}:{effect.target_id}"
            last_round = self._cooldowns.get(cooldown_key, -999)
            if current_round - last_round < COOLDOWN_ROUNDS:
                logger.info(f"Cooldown active for {cooldown_key}, skipping")
                continue

            applied = self._apply_effect(effect, current_round, platform)
            if applied:
                self._cooldowns[cooldown_key] = current_round
                for eff in applied:
                    results.append(eff)
                    self._applied.append(eff)
                    self._log_effect(eff)

        return results

    def _apply_effect(self, effect: StateEffect, current_round: int, platform: str) -> list[AppliedEffect]:
        """Apply a single effect. Returns list of AppliedEffects (may be >1 for bidirectional)."""
        try:
            if effect.effect_type == EffectType.SUPPRESS_AGENT:
                r = self._apply_suppress(effect, current_round)
                return [r] if r else []
            elif effect.effect_type == EffectType.BOOST_AGENT:
                r = self._apply_boost(effect, current_round)
                return [r] if r else []
            elif effect.effect_type == EffectType.CREATE_LINK:
                return self._apply_create_link(effect, current_round, platform)
            elif effect.effect_type == EffectType.BREAK_LINK:
                r = self._apply_break_link(effect, current_round, platform)
                return [r] if r else []
            elif effect.effect_type == EffectType.BROADCAST:
                r = self._apply_broadcast(effect, current_round)
                return [r] if r else []
        except Exception as e:
            logger.error(f"Failed to apply effect {effect.effect_type}: {e}")
        return []

    def _apply_suppress(self, effect: StateEffect, rnd: int) -> AppliedEffect | None:
        ac = self._agent_config_by_id.get(effect.target_id)
        if not ac:
            return None
        before_val = ac.get("activity_level", 0.5)
        magnitude = min(effect.magnitude, MAX_MAGNITUDE)
        new_val = max(before_val * (1 - magnitude), ACTIVITY_FLOOR)
        ac["activity_level"] = new_val
        return AppliedEffect(
            round_num=rnd,
            effect_type=effect.effect_type.value,
            actor_id=effect.actor_id,
            actor_name=self._agent_names.get(effect.actor_id, f"Agent_{effect.actor_id}"),
            target_id=effect.target_id,
            target_name=self._agent_names.get(effect.target_id, f"Agent_{effect.target_id}"),
            before={"activity_level": round(before_val, 4)},
            after={"activity_level": round(new_val, 4)},
            caused_by_tool=effect.tool_name,
            tool_args=effect.tool_args,
            timestamp=datetime.now().isoformat(),
        )

    def _apply_boost(self, effect: StateEffect, rnd: int) -> AppliedEffect | None:
        ac = self._agent_config_by_id.get(effect.target_id)
        if not ac:
            return None
        before_val = ac.get("activity_level", 0.5)
        magnitude = min(effect.magnitude, MAX_MAGNITUDE)
        new_val = min(before_val * (1 + magnitude), ACTIVITY_CEILING)
        ac["activity_level"] = new_val
        return AppliedEffect(
            round_num=rnd,
            effect_type=effect.effect_type.value,
            actor_id=effect.actor_id,
            actor_name=self._agent_names.get(effect.actor_id, f"Agent_{effect.actor_id}"),
            target_id=effect.target_id,
            target_name=self._agent_names.get(effect.target_id, f"Agent_{effect.target_id}"),
            before={"activity_level": round(before_val, 4)},
            after={"activity_level": round(new_val, 4)},
            caused_by_tool=effect.tool_name,
            tool_args=effect.tool_args,
            timestamp=datetime.now().isoformat(),
        )

    def _apply_create_link(self, effect: StateEffect, rnd: int, platform: str) -> list[AppliedEffect]:
        if self._follow_changes.get(platform, 0) >= MAX_FOLLOW_CHANGES_PER_ROUND:
            return []

        src, dst = effect.actor_id, effect.target_id
        if effect.direction == "target_to_actor":
            src, dst = dst, src

        env = self._envs.get(platform)
        if not env:
            return []

        cursor = getattr(env.platform, "db_cursor", None)
        db = getattr(env.platform, "db", None)
        if not cursor or not db:
            return []

        results = []
        try:
            cursor.execute("SELECT 1 FROM follow WHERE follower_id=? AND followee_id=?", (src, dst))
            if cursor.fetchone():
                return []

            cursor.execute(
                "INSERT INTO follow (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
                (src, dst, datetime.now().isoformat()),
            )
            cursor.execute("UPDATE user SET num_followings = num_followings + 1 WHERE agent_id = ?", (src,))
            cursor.execute("UPDATE user SET num_followers = num_followers + 1 WHERE agent_id = ?", (dst,))
            db.commit()

            agent_graph = self._agent_graphs.get(platform)
            if agent_graph:
                agent_graph.add_edge(src, dst)

            self._follow_changes[platform] = self._follow_changes.get(platform, 0) + 1

            results.append(
                AppliedEffect(
                    round_num=rnd,
                    effect_type=effect.effect_type.value,
                    actor_id=effect.actor_id,
                    actor_name=self._agent_names.get(effect.actor_id, f"Agent_{effect.actor_id}"),
                    target_id=effect.target_id,
                    target_name=self._agent_names.get(effect.target_id, f"Agent_{effect.target_id}"),
                    before={"follow_exists": False},
                    after={"follow_exists": True, "direction": f"{src}->{dst}"},
                    caused_by_tool=effect.tool_name,
                    tool_args=effect.tool_args,
                    timestamp=datetime.now().isoformat(),
                )
            )

            if effect.direction == "bidirectional":
                reverse = StateEffect(
                    effect_type=EffectType.CREATE_LINK,
                    actor_id=dst,
                    target_id=src,
                    direction="actor_to_target",
                    tool_name=effect.tool_name,
                    tool_args=effect.tool_args,
                    platform=effect.platform,
                )
                reverse_results = self._apply_create_link(reverse, rnd, platform)
                results.extend(reverse_results)

        except Exception as e:
            logger.error(f"CREATE_LINK failed ({src}->{dst}): {e}")

        return results

    def _apply_break_link(self, effect: StateEffect, rnd: int, platform: str) -> AppliedEffect | None:
        if self._follow_changes.get(platform, 0) >= MAX_FOLLOW_CHANGES_PER_ROUND:
            return None

        src, dst = effect.actor_id, effect.target_id
        if effect.direction == "target_to_actor":
            src, dst = dst, src

        env = self._envs.get(platform)
        if not env:
            return None

        cursor = getattr(env.platform, "db_cursor", None)
        db = getattr(env.platform, "db", None)
        if not cursor or not db:
            return None

        try:
            cursor.execute("DELETE FROM follow WHERE follower_id=? AND followee_id=?", (src, dst))
            if cursor.rowcount > 0:
                cursor.execute("UPDATE user SET num_followings = MAX(num_followings - 1, 0) WHERE agent_id = ?", (src,))
                cursor.execute("UPDATE user SET num_followers = MAX(num_followers - 1, 0) WHERE agent_id = ?", (dst,))
                db.commit()

                agent_graph = self._agent_graphs.get(platform)
                if agent_graph:
                    try:
                        agent_graph.remove_edge(src, dst)
                    except Exception:
                        pass

                self._follow_changes[platform] = self._follow_changes.get(platform, 0) + 1

                return AppliedEffect(
                    round_num=rnd,
                    effect_type=effect.effect_type.value,
                    actor_id=effect.actor_id,
                    actor_name=self._agent_names.get(effect.actor_id, f"Agent_{effect.actor_id}"),
                    target_id=effect.target_id,
                    target_name=self._agent_names.get(effect.target_id, f"Agent_{effect.target_id}"),
                    before={"follow_exists": True, "direction": f"{src}->{dst}"},
                    after={"follow_exists": False},
                    caused_by_tool=effect.tool_name,
                    tool_args=effect.tool_args,
                    timestamp=datetime.now().isoformat(),
                )
        except Exception as e:
            logger.error(f"BREAK_LINK failed ({src}->{dst}): {e}")
        return None

    def _apply_broadcast(self, effect: StateEffect, rnd: int) -> AppliedEffect | None:
        msg = (
            effect.broadcast_message or f"[{effect.tool_name.upper()}] {effect.tool_args.get('action_description', '')}"
        )
        return AppliedEffect(
            round_num=rnd,
            effect_type=effect.effect_type.value,
            actor_id=effect.actor_id,
            actor_name=self._agent_names.get(effect.actor_id, f"Agent_{effect.actor_id}"),
            target_id=effect.target_id or -1,
            target_name="all",
            before={},
            after={"message": msg[:300]},
            caused_by_tool=effect.tool_name,
            tool_args=effect.tool_args,
            timestamp=datetime.now().isoformat(),
        )

    def _log_effect(self, applied: AppliedEffect):
        entry = {
            "round": applied.round_num,
            "effect_type": applied.effect_type,
            "actor_id": applied.actor_id,
            "actor_name": applied.actor_name,
            "target_id": applied.target_id,
            "target_name": applied.target_name,
            "before": applied.before,
            "after": applied.after,
            "caused_by_tool": applied.caused_by_tool,
            "tool_args": applied.tool_args,
            "timestamp": applied.timestamp,
        }
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log effect: {e}")

    def get_applied_effects(self) -> list[AppliedEffect]:
        return list(self._applied)

    def to_action_dicts(self, effects: list[AppliedEffect], agent_names: dict[int, str]) -> list[dict]:
        """Convert applied effects to action dicts for the action stream."""
        actions = []
        for eff in effects:
            actions.append(
                {
                    "agent_id": eff.actor_id,
                    "agent_name": agent_names.get(eff.actor_id, eff.actor_name),
                    "action_type": f"STATE_{eff.effect_type.upper()}",
                    "action_args": {
                        "effect_type": eff.effect_type,
                        "target_name": eff.target_name,
                        "target_id": eff.target_id,
                        "before": eff.before,
                        "after": eff.after,
                        "caused_by_tool": eff.caused_by_tool,
                    },
                }
            )
        return actions
