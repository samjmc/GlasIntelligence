"""Time-label and agent-scheduling helpers for the parallel simulation runner."""

import contextlib
import random
from typing import Any, Dict, List  # noqa: UP035

# Jev activation gate (app.services.jev_simulation_gates). scripts/lib runs inside the
# OASIS subprocess with backend/ on sys.path (db_utils puts it there); if the import
# fails for any reason the round loop keeps today's Bernoulli scheduling.
try:
    from app.services.jev_simulation_gates import activation_gate as _jev_activation_gate
except Exception:  # pragma: no cover - only when app/ is not importable
    _jev_activation_gate = None  # type: ignore[assignment]


def compute_time_label(round_num: int, time_scale: Dict[str, Any]) -> Dict[str, str]:
    """Build a human-readable time label for the current round.

    Returns a dict with 'label' (combined), 'relative', and 'anchor' keys.
    """
    from dateutil.relativedelta import relativedelta
    from datetime import datetime as _dt

    unit = time_scale.get("unit", "hour")
    per_round = max(1, time_scale.get("per_round", 1))
    start_date_str = time_scale.get("start_date", "")
    elapsed = round_num * per_round

    unit_label = unit.title()
    relative = f"{unit_label} {elapsed}"

    anchor = ""
    if start_date_str:
        try:
            base = _dt.fromisoformat(start_date_str)
            delta_map = {
                "hour": {"hours": elapsed},
                "day": {"days": elapsed},
                "week": {"weeks": elapsed},
                "month": {"months": elapsed},
                "year": {"years": elapsed},
            }
            delta_kwargs = delta_map.get(unit, {"hours": elapsed})
            target = base + relativedelta(**delta_kwargs)

            fmt_map = {
                "hour": target.strftime("%b %d %Y, %H:%M"),
                "day": target.strftime("%b %d, %Y"),
                "week": f"w/c {target.strftime('%b %d, %Y')}",
                "month": target.strftime("%B %Y"),
                "year": target.strftime("%Y"),
            }
            anchor = fmt_map.get(unit, target.isoformat())
            return {"label": f"{relative} ({anchor})", "relative": relative, "anchor": anchor}
        except Exception:
            pass

    return {"label": relative, "relative": relative, "anchor": anchor}


def get_phase_multiplier(round_num: int, phases: List[Dict[str, Any]]) -> float:
    """Return the activity multiplier for the current round based on scenario phases."""
    for phase in phases:
        if phase.get("start_round", 0) <= round_num + 1 <= phase.get("end_round", 0):
            return phase.get("activity_multiplier", 1.0)
    return 1.0


def _activation_decision(gate: Any, agent_id: int, activity_level: float, rng: Any) -> bool:
    """One rng draw per agent, whichever path decides (keeps the rng stream identical to today)."""
    if gate is None:
        return bool(rng.random() < activity_level)
    return bool(gate.decide(agent_id, activity_level, rng))


def get_active_agents_for_round(
    env,
    config: Dict[str, Any],
    current_hour: int,
    round_num: int,
    recent_feed: "list[dict[str, Any]] | None" = None,
    rng: Any = random,
) -> List:
    """Decide which agents are active this round based on time and config

    Supports two modes:
    - Hour-based (unit == "hour"): uses active_hours, peak/off-peak multipliers
    - Phase-based (unit != "hour"): skips active_hours, uses ScenarioPhase multipliers

    ``recent_feed`` (the runner's rolling window of recent posts) enables the Jev
    "activation" gate: with Jev active each agent's Bernoulli weight becomes a weight
    derived from two Jev signals (addressed in the feed / interests at stake) times its
    activity_level, clamped 0.05-0.95; with Jev in shadow mode p is only measured
    against today's decision; with Jev off, or no feed yet (round 0), this is exactly
    today's logic. ``rng`` lets tests pin the stream.
    """
    time_config = config.get("time_config", {})
    agent_configs = config.get("agent_configs", [])

    base_min = time_config.get("agents_per_round_min", time_config.get("agents_per_hour_min", 5))
    base_max = time_config.get("agents_per_round_max", time_config.get("agents_per_hour_max", 20))

    time_scale = time_config.get("time_scale", {})
    unit = time_scale.get("unit", "hour")

    gate = None
    if _jev_activation_gate is not None and recent_feed:
        if unit != "hour":
            eligible = agent_configs
        else:
            eligible = [
                cfg for cfg in agent_configs if current_hour in cfg.get("active_hours", list(range(8, 23)))
            ]
        try:
            gate = _jev_activation_gate(eligible, recent_feed)
        except Exception:
            gate = None

    if unit != "hour":
        # Phase-based scheduling: no hour-of-day filtering
        phases = time_config.get("phases", [])
        multiplier = get_phase_multiplier(round_num, phases)

        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            if _activation_decision(gate, agent_id, cfg.get("activity_level", 0.5), rng):
                candidates.append(agent_id)

        target_count = int(rng.uniform(base_min, base_max) * multiplier)
    else:
        # Hour-based scheduling (existing logic)
        peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
        off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])

        if current_hour in peak_hours:
            multiplier = time_config.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
        else:
            multiplier = 1.0

        target_count = int(rng.uniform(base_min, base_max) * multiplier)

        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            activity_level = cfg.get("activity_level", 0.5)

            if current_hour not in active_hours:
                continue

            if _activation_decision(gate, agent_id, activity_level, rng):
                candidates.append(agent_id)

    if gate is not None:
        with contextlib.suppress(Exception):
            gate.finish(round_num)

    selected_ids = rng.sample(
        candidates,
        min(target_count, len(candidates))
    ) if candidates else []

    active_agents = []
    for agent_id in selected_ids:
        try:
            agent = env.agent_graph.get_agent(agent_id)
            active_agents.append((agent_id, agent))
        except Exception:
            pass

    return active_agents


