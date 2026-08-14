"""Time-label and agent-scheduling helpers for the parallel simulation runner."""

import random
from typing import Any, Dict, List  # noqa: UP035

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


def get_active_agents_for_round(
    env,
    config: Dict[str, Any],
    current_hour: int,
    round_num: int
) -> List:
    """Decide which agents are active this round based on time and config

    Supports two modes:
    - Hour-based (unit == "hour"): uses active_hours, peak/off-peak multipliers
    - Phase-based (unit != "hour"): skips active_hours, uses ScenarioPhase multipliers
    """
    time_config = config.get("time_config", {})
    agent_configs = config.get("agent_configs", [])

    base_min = time_config.get("agents_per_round_min", time_config.get("agents_per_hour_min", 5))
    base_max = time_config.get("agents_per_round_max", time_config.get("agents_per_hour_max", 20))

    time_scale = time_config.get("time_scale", {})
    unit = time_scale.get("unit", "hour")

    if unit != "hour":
        # Phase-based scheduling: no hour-of-day filtering
        phases = time_config.get("phases", [])
        multiplier = get_phase_multiplier(round_num, phases)

        candidates = []
        for cfg in agent_configs:
            if random.random() < cfg.get("activity_level", 0.5):
                candidates.append(cfg.get("agent_id", 0))

        target_count = int(random.uniform(base_min, base_max) * multiplier)
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

        target_count = int(random.uniform(base_min, base_max) * multiplier)

        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            activity_level = cfg.get("activity_level", 0.5)

            if current_hour not in active_hours:
                continue

            if random.random() < activity_level:
                candidates.append(agent_id)

    selected_ids = random.sample(
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


