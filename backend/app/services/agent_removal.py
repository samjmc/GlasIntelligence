"""
Remove agents from a prepared simulation before it starts.

The agent check in prepare (``simulation_manager.drop_irrelevant_agents``) cannot catch every
wrong agent, so the user can drop agents on the Environment Setup page. Everything the run
reads about agents lives in the simulation directory, and it must stay in step:

- ``reddit_profiles.json``: a list of profiles. The runner builds agent ``i`` from list item
  ``i`` (``scripts/lib/agent_graphs.py``: ``agent_id=i``), so a profile's place in the list IS
  its agent id; its ``user_id`` field says the same.
- ``simulation_config.json``: ``agent_configs[i].agent_id == i`` for the same agent (activation
  and agent names in the runner key on it), and ``event_config.initial_posts[].poster_agent_id``
  names the agent that publishes each opening post (``platform_runners._opening_actions``).
- ``twitter_profiles.csv``: only in runs made before twitter was dropped; row ``i`` is agent ``i``.
- ``state.json``: ``entities_count`` / ``profiles_count`` / ``entity_types`` shown by the UI.

So removal keeps the remaining agents in order and renumbers them 0..n-1 everywhere. An opening
post of a removed agent goes to a remaining agent of the same type (the posts were written for a
poster type, not a named agent, which is also how prepare assigned them); if no agent of that
type is left, the post is dropped.
"""

from __future__ import annotations

import csv
import io
import json
import os
import threading
from datetime import datetime
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("glas.agent_removal")

MIN_AGENTS = 2
READY_STATUS = "ready"

_PROFILES = "reddit_profiles.json"
_TWITTER_PROFILES = "twitter_profiles.csv"
_CONFIG = "simulation_config.json"
_STATE = "state.json"
_RUN_STATE = "run_state.json"
_POST_LISTS = ("initial_posts", "scheduled_events")

# One removal at a time: each is a read-modify-write of several files.
_lock = threading.Lock()


class AgentRemovalError(Exception):
    """A removal the caller must not make; ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.message = message
        self.status = status


def remove_agents(sim_dir: str, agent_ids: list[Any] | None = None, names: list[Any] | None = None) -> dict[str, Any]:
    """Remove agents (by agent id and/or name) from every stored artefact of a prepared run.

    Unknown or ambiguous ids/names are refused (400) and nothing is changed: a typo must not
    silently leave a wrong agent in the run. Returns the new profiles and config.
    """
    with _lock:
        state = _read_json(os.path.join(sim_dir, _STATE))
        if not isinstance(state, dict):
            raise AgentRemovalError("Simulation not found", 404)
        if state.get("status") != READY_STATUS or not state.get("config_generated"):
            raise AgentRemovalError(
                f"Agents can only be removed while the simulation is ready and not started "
                f"(status: {state.get('status') or 'unknown'})",
                409,
            )
        if os.path.exists(os.path.join(sim_dir, _RUN_STATE)):
            raise AgentRemovalError("This simulation has already been started; its agents can no longer change", 409)

        profiles = _read_json(os.path.join(sim_dir, _PROFILES))
        config = _read_json(os.path.join(sim_dir, _CONFIG))
        agent_configs = config.get("agent_configs") if isinstance(config, dict) else None
        if not isinstance(profiles, list) or not isinstance(agent_configs, list) or len(profiles) != len(agent_configs):
            raise AgentRemovalError("The agent files of this simulation do not match; prepare it again", 409)

        targets = _resolve_targets(profiles, agent_configs, agent_ids or [], names or [])
        if not targets:
            raise AgentRemovalError("Name at least one agent to remove (agent_ids or names)", 400)
        remaining = len(profiles) - len(targets)
        if remaining < MIN_AGENTS:
            raise AgentRemovalError(
                f"A simulation needs at least {MIN_AGENTS} agents; removing {len(targets)} would leave {remaining}",
                400,
            )

        keep = [i for i in range(len(profiles)) if i not in targets]
        new_id = {old: new for new, old in enumerate(keep)}
        removed_names = [_agent_name(profiles[i], agent_configs[i]) for i in sorted(targets)]

        new_profiles = [{**profiles[old], "user_id": new} for new, old in enumerate(keep)]
        new_configs = [{**agent_configs[old], "agent_id": new} for new, old in enumerate(keep)]
        config["agent_configs"] = new_configs
        event_config = config.get("event_config")
        if isinstance(event_config, dict):
            for key in _POST_LISTS:
                if isinstance(event_config.get(key), list):
                    event_config[key] = _reassign_posts(event_config[key], agent_configs, new_configs, new_id)
        _clamp_agents_per_round(config.get("time_config"), len(keep))

        writes: list[tuple[str, str]] = [
            (_CONFIG, json.dumps(config, ensure_ascii=False, indent=2)),
            (_PROFILES, json.dumps(new_profiles, ensure_ascii=False, indent=2)),
        ]
        twitter_path = os.path.join(sim_dir, _TWITTER_PROFILES)
        if os.path.exists(twitter_path):
            writes.append((_TWITTER_PROFILES, _renumbered_csv(twitter_path, keep, len(profiles))))

        state["entities_count"] = state["profiles_count"] = len(keep)
        state["entity_types"] = sorted({c.get("entity_type") for c in new_configs if c.get("entity_type")})
        state["updated_at"] = datetime.now().isoformat()
        writes.append((_STATE, json.dumps(state, ensure_ascii=False, indent=2)))  # last: it marks the change done

        _write_all(sim_dir, writes)

        for old in sorted(targets):
            logger.info(
                f"Removed agent before start: simulation={os.path.basename(sim_dir)}, agent_id={old}, "
                f"name={_agent_name(profiles[old], agent_configs[old])!r}"
            )
        logger.info(f"Simulation {os.path.basename(sim_dir)} now has {len(keep)} agents")

        return {"removed": removed_names, "count": len(keep), "profiles": new_profiles, "config": config}


def _resolve_targets(profiles: list, agent_configs: list, agent_ids: list, names: list) -> set[int]:
    if not isinstance(agent_ids, list) or not isinstance(names, list):
        raise AgentRemovalError("agent_ids and names must be lists", 400)
    targets: set[int] = set()
    for raw in agent_ids:
        if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw < len(profiles):
            raise AgentRemovalError(f"Unknown agent id: {raw}", 400)
        targets.add(raw)
    for raw in names:
        wanted = str(raw).strip().casefold() if isinstance(raw, str) else ""
        matches = [i for i in range(len(profiles)) if wanted and wanted in _labels(profiles[i], agent_configs[i])]
        if not matches:
            raise AgentRemovalError(f"Unknown agent name: {raw}", 400)
        if len(matches) > 1:
            raise AgentRemovalError(f"{len(matches)} agents are called {raw!r}; remove them by agent_ids", 400)
        targets.add(matches[0])
    return targets


def _reassign_posts(posts: list, old_configs: list, new_configs: list, new_id: dict[int, int]) -> list:
    """Renumber posters; a removed poster's post goes to a remaining agent of its type, or is dropped."""
    by_type: dict[str, list[int]] = {}
    for cfg in new_configs:
        by_type.setdefault(str(cfg.get("entity_type", "")).casefold(), []).append(cfg["agent_id"])
    turn: dict[str, int] = {}
    kept = []
    for post in posts:
        if not isinstance(post, dict) or "poster_agent_id" not in post:
            kept.append(post)
            continue
        old = post.get("poster_agent_id")
        if old in new_id:
            kept.append({**post, "poster_agent_id": new_id[old]})
            continue
        types = [str(post.get("poster_type", "")).casefold()]
        if isinstance(old, int) and 0 <= old < len(old_configs):
            types.append(str(old_configs[old].get("entity_type", "")).casefold())
        etype = next((t for t in types if by_type.get(t)), None)
        if etype is None:
            logger.info(f"Dropped an opening post of removed agent {old}: no {post.get('poster_type')!r} agent left")
            continue
        ids = by_type[etype]
        poster = ids[turn.get(etype, 0) % len(ids)]
        turn[etype] = turn.get(etype, 0) + 1
        kept.append({**post, "poster_agent_id": poster})
    return kept


def _clamp_agents_per_round(time_config: Any, count: int) -> None:
    if not isinstance(time_config, dict):
        return
    for prefix in ("agents_per_hour", "agents_per_round"):
        top = time_config.get(f"{prefix}_max")
        if not isinstance(top, int):
            continue
        if top > count:
            time_config[f"{prefix}_max"] = top = count
        low = time_config.get(f"{prefix}_min")
        if isinstance(low, int) and low > top:
            time_config[f"{prefix}_min"] = top


def _renumbered_csv(path: str, keep: list[int], expected_rows: int) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if len(rows) != expected_rows:
        raise AgentRemovalError("The agent files of this simulation do not match; prepare it again", 409)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for new, old in enumerate(keep):
        row = rows[old]
        if "user_id" in row:
            row["user_id"] = str(new)
        writer.writerow(row)
    return out.getvalue()


def _write_all(sim_dir: str, writes: list[tuple[str, str]]) -> None:
    """Write every file to a temp name first, then swap them in: a failed write changes nothing, and only a
    failed swap (rare: same directory, same disk) could leave the files partly updated."""
    temps = []
    try:
        for name, text in writes:
            tmp = os.path.join(sim_dir, f".{name}.removing")
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            temps.append((tmp, os.path.join(sim_dir, name)))
        for tmp, final in temps:
            os.replace(tmp, final)
    finally:
        for tmp, _ in temps:
            if os.path.exists(tmp):
                os.remove(tmp)


def _labels(profile: dict, agent_config: dict) -> set[str]:
    values = (profile.get("name"), profile.get("username"), agent_config.get("entity_name"))
    return {str(v).strip().casefold() for v in values if v}


def _agent_name(profile: dict, agent_config: dict) -> str:
    return str(profile.get("name") or agent_config.get("entity_name") or profile.get("username") or "agent")


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
