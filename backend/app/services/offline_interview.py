"""
Agent interviews that work whether or not the OASIS subprocess is still alive.

Live path (subprocess alive): unchanged, SimulationRunner's filesystem IPC.

Reconstructed path (subprocess gone: every finished run, a crash, a redeploy):
each agent is rebuilt from what the run saved on disk and answered in-process
with one LLM call per (agent, platform):

- persona: ``twitter_profiles.csv`` (``user_char``) / ``reddit_profiles.json``
  (``persona``, ``mbti``, ``gender``, ``age``, ``country``)
- stance and entity data: ``simulation_config.json`` ``agent_configs``
- memory: the agent's own last ``MAX_OWN_ACTIONS`` actions from
  ``<platform>/actions.jsonl`` (round-0 initial posts kept first), plus up to
  ``MAX_REPLIES`` things other agents said to or about it

The system prompt starts with the text OASIS's ``SocialAgent.perform_interview``
sends (``UserInfo.to_twitter_system_message`` / ``to_reddit_system_message`` in
camel-oasis 0.2.5) up to its ``# RESPONSE METHOD`` section, which is left out
because no tools are offered here. The live agent's CAMEL memory window
(feed observations and tool calls) is replaced by a compact record of the
agent's own recorded actions.

Every response dict has the live shape plus a ``mode`` field
(``"live"`` | ``"reconstructed"``).
"""

import csv
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .simulation_runner import SimulationRunner
from .zep_graph_memory_updater import AgentActivity

logger = get_logger("glas.offline_interview")

# Memory caps for a reconstructed agent: what the LLM sees besides the persona.
MAX_OWN_ACTIONS = 30  # the agent's own actions, round-0 initial posts first, then the most recent
MAX_REPLIES = 10  # most relevant things others said to or about the agent
MAX_MEMORY_LINE_CHARS = 600  # each rendered memory line is cut to this length
MIN_MENTION_NAME_CHARS = 3  # shorter names are too ambiguous to match inside free text

INTERVIEW_TEMPERATURE = 0.7
INTERVIEW_MAX_TOKENS = 2048
MAX_PARALLEL_LLM_CALLS = 8

PLATFORMS = ("twitter", "reddit")
PROFILE_FILES = {"twitter": "twitter_profiles.csv", "reddit": "reddit_profiles.json"}

# Actions that carry no opinion and would only spend the memory budget.
NON_MEMORY_ACTIONS = frozenset({"DO_NOTHING", "REFRESH", "TREND", "INTERVIEW", "SIGN_UP", "EXIT"})
# Actions by other agents that put words in front of this agent.
TEXT_ACTIONS = frozenset({"CREATE_POST", "CREATE_COMMENT", "QUOTE_POST"})
# action_args fields naming the author of the post/comment an action responds to (scripts/lib/db_utils.py).
TARGET_AUTHOR_FIELDS = ("post_author_name", "original_author_name", "comment_author_name")


class InterviewMode(StrEnum):
    LIVE = "live"
    RECONSTRUCTED = "reconstructed"


class SimulationNotFoundError(LookupError):
    """The simulation directory does not exist on disk."""


def _now() -> str:
    return datetime.now().isoformat()


def _require_sim_dir(simulation_id: str) -> str:
    # A bare directory name only: the id is caller-supplied and joined onto a path.
    if not simulation_id or os.path.basename(simulation_id) != simulation_id or simulation_id in (".", ".."):
        raise SimulationNotFoundError(f"Simulation does not exist: {simulation_id}")
    sim_dir = os.path.join(SimulationRunner.RUN_STATE_DIR, simulation_id)
    if not os.path.isdir(sim_dir):
        raise SimulationNotFoundError(f"Simulation does not exist: {simulation_id}")
    return sim_dir


class RecordedRun:
    """What a run saved on disk, read once per interview request."""

    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir
        config_path = os.path.join(sim_dir, "simulation_config.json")
        self.config: dict[str, Any] = {}
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                self.config = json.load(f)
        self.agent_configs = {
            c["agent_id"]: c for c in self.config.get("agent_configs", []) if c.get("agent_id") is not None
        }
        self._profiles: dict[str, list[dict[str, Any]]] = {}
        self._actions: dict[str, list[dict[str, Any]]] = {}

    def _has_profiles(self, platform: str) -> bool:
        return os.path.exists(os.path.join(self.sim_dir, PROFILE_FILES[platform]))

    def _has_actions(self, platform: str) -> bool:
        return os.path.exists(os.path.join(self.sim_dir, platform, "actions.jsonl"))

    def platforms(self) -> list[str]:
        """Platforms that ran (actions.jsonl exists, like SimulationRunner), else ones that were prepared."""
        ran = [p for p in PLATFORMS if self._has_profiles(p) and self._has_actions(p)]
        return ran or [p for p in PLATFORMS if self._has_profiles(p)]

    def profiles(self, platform: str) -> list[dict[str, Any]]:
        if platform not in self._profiles:
            path = os.path.join(self.sim_dir, PROFILE_FILES[platform])
            rows: list[dict[str, Any]] = []
            if os.path.exists(path):
                with open(path, newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f)) if platform == "twitter" else json.load(f)
            self._profiles[platform] = rows
        return self._profiles[platform]

    def profile(self, platform: str, agent_id: int) -> dict[str, Any] | None:
        # OASIS builds agents by row index (scripts/lib/agent_graphs.py), so agent_id IS the row index.
        rows = self.profiles(platform)
        return rows[agent_id] if 0 <= agent_id < len(rows) else None

    def actions(self, platform: str) -> list[dict[str, Any]]:
        if platform not in self._actions:
            path = os.path.join(self.sim_dir, platform, "actions.jsonl")
            entries: list[dict[str, Any]] = []
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:  # a run killed mid-write can leave a partial last line
                            continue
                        if "event_type" not in entry and "agent_id" in entry:
                            entries.append(entry)
            self._actions[platform] = entries
        return self._actions[platform]


def oasis_system_prompt(platform: str, profile: dict[str, Any]) -> str:
    """The persona part of the system prompt OASIS gives this agent, verbatim.

    Mirrors ``UserInfo.to_twitter_system_message`` / ``to_reddit_system_message``
    (camel-oasis 0.2.5, fed as in scripts/lib/agent_graphs.py) up to ``# RESPONSE METHOD``.
    """
    name = profile.get("username")
    if platform == "twitter":
        description = f"Your name is {name}.\nYour have profile: {profile.get('user_char')}."
        return (
            "\n# OBJECTIVE\n"
            "You're a Twitter user, and I'll present you with some posts. After you see the posts, "
            "choose some actions from the following functions.\n\n"
            "# SELF-DESCRIPTION\n"
            "Your actions should be consistent with your self-description and personality.\n"
            f"{description}\n\n"
        )
    description = (
        f"Your name is {name}.\nYour have profile: {profile.get('persona')}."
        f"You are a {profile.get('gender')}, {profile.get('age')} years old, with an MBTI "
        f"personality type of {profile.get('mbti')} from {profile.get('country')}."
    )
    return (
        "\n# OBJECTIVE\n"
        "You're a Reddit user, and I'll present you with some tweets. After you see the tweets, "
        "choose some actions from the following functions.\n\n"
        "# SELF-DESCRIPTION\n"
        "Your actions should be consistent with your self-description and personality.\n"
        f"{description}\n\n"
    )


def _render(entry: dict[str, Any], platform: str, agent_name: str) -> str:
    text = AgentActivity(
        platform=platform,
        agent_id=entry.get("agent_id"),
        agent_name=agent_name,
        action_type=entry.get("action_type", ""),
        action_args=entry.get("action_args") or {},
        round_num=entry.get("round", entry.get("round_num", 0)),
        timestamp=entry.get("timestamp", ""),
    ).to_episode_text()
    if len(text) > MAX_MEMORY_LINE_CHARS:
        text = text[: MAX_MEMORY_LINE_CHARS - 3] + "..."
    round_num = entry.get("round", entry.get("round_num"))
    return f"- Round {round_num}: {text}" if round_num is not None else f"- {text}"


def own_memory(run: RecordedRun, platform: str, agent_id: int) -> list[dict[str, Any]]:
    """The agent's own actions, capped at MAX_OWN_ACTIONS: round-0 initial posts first, then the latest."""
    acts = [
        a for a in run.actions(platform)
        if a.get("agent_id") == agent_id and a.get("action_type") not in NON_MEMORY_ACTIONS
    ]
    seeds, later = [], []
    for a in acts:
        (seeds if a.get("round") == 0 and a.get("action_type") == "CREATE_POST" else later).append(a)
    logged = {(a.get("action_args") or {}).get("content") for a in seeds}
    # Runs whose log predates round-0 logging: take the opening posts from the config instead.
    for post in run.config.get("event_config", {}).get("initial_posts", []):
        if post.get("poster_agent_id") == agent_id and post.get("content") not in logged:
            seeds.append({
                "round": 0, "agent_id": agent_id, "action_type": "CREATE_POST",
                "action_args": {"content": post.get("content", "")},
            })
    seeds = seeds[:MAX_OWN_ACTIONS]
    room = MAX_OWN_ACTIONS - len(seeds)
    return seeds + (later[-room:] if room > 0 else [])


def _self_names(run: RecordedRun, platform: str, agent_id: int, profile: dict[str, Any]) -> set[str]:
    names = {
        (run.agent_configs.get(agent_id) or {}).get("entity_name"),
        profile.get("name"),
        profile.get("username"),
    }
    names.update(a.get("agent_name") for a in run.actions(platform) if a.get("agent_id") == agent_id)
    return {n.strip() for n in names if isinstance(n, str) and n.strip()}


def replies_to(run: RecordedRun, platform: str, agent_id: int, names: set[str]) -> list[dict[str, Any]]:
    """Up to MAX_REPLIES things others said to or about the agent, in the order they happened.

    Direct responses (a comment or quote on the agent's own post/comment) outrank
    posts that only mention one of its names; ties go to the most recent.
    """
    mention_patterns = [
        re.compile(rf"(?<!\w){re.escape(n)}(?!\w)", re.IGNORECASE) for n in names if len(n) >= MIN_MENTION_NAME_CHARS
    ]
    scored = []
    for idx, entry in enumerate(run.actions(platform)):
        if entry.get("agent_id") == agent_id or entry.get("action_type") not in TEXT_ACTIONS:
            continue
        args = entry.get("action_args") or {}
        direct = any(args.get(field) in names for field in TARGET_AUTHOR_FIELDS)
        text = args.get("content") or args.get("quote_content") or ""
        mentioned = bool(text) and any(p.search(text) for p in mention_patterns)
        if direct or mentioned:
            scored.append((2 if direct else 1, idx, entry))
    top = sorted(scored, key=lambda s: (s[0], s[1]), reverse=True)[:MAX_REPLIES]
    return [entry for _, _, entry in sorted(top, key=lambda s: s[1])]


def build_interview_messages(
    run: RecordedRun, platform: str, agent_id: int, prompt: str
) -> list[dict[str, str]] | None:
    """System + user messages for one reconstructed interview, or None if the agent is unknown."""
    profile = run.profile(platform, agent_id)
    if profile is None:
        return None
    agent_config = run.agent_configs.get(agent_id) or {}
    names = _self_names(run, platform, agent_id, profile)

    parts = [oasis_system_prompt(platform, profile).rstrip("\n")]
    if agent_config:
        parts.append(
            "\n# YOUR ROLE IN THIS SIMULATION\n"
            f"You represent {agent_config.get('entity_name', profile.get('name'))} "
            f"({agent_config.get('entity_type', 'participant')}). "
            f"Your stance on the topic: {agent_config.get('stance', 'unspecified')}."
        )
    own = own_memory(run, platform, agent_id)
    parts.append(
        "\n# WHAT YOU DID IN THIS SIMULATION (oldest first)\n"
        + ("\n".join(_render(a, platform, "You") for a in own) if own else "(You took no recorded actions.)")
    )
    replies = replies_to(run, platform, agent_id, names)
    if replies:
        parts.append(
            "\n# WHAT OTHERS SAID TO OR ABOUT YOU (oldest first)\n"
            + "\n".join(_render(r, platform, r.get("agent_name") or f"Agent_{r.get('agent_id')}") for r in replies)
        )
    parts.append(
        "\n# INTERVIEW\n"
        "You are now being interviewed about this simulation. Stay in character, draw on the "
        "record above, and answer in plain text."
    )
    return [{"role": "system", "content": "\n".join(parts)}, {"role": "user", "content": prompt}]


def _answer_one(llm: LLMClient, run: RecordedRun, platform: str, agent_id: int, prompt: str) -> dict[str, Any]:
    try:
        messages = build_interview_messages(run, platform, agent_id, prompt)
        if messages is None:
            return {"agent_id": agent_id, "response": None, "platform": platform,
                    "error": f"Agent {agent_id} not found on {platform}"}
        text = llm.chat(messages, temperature=INTERVIEW_TEMPERATURE, max_tokens=INTERVIEW_MAX_TOKENS)
    except Exception as e:  # one agent's failure must not sink the batch
        logger.warning(f"Reconstructed interview failed: agent_id={agent_id}, platform={platform}: {e}")
        return {"agent_id": agent_id, "response": None, "platform": platform, "error": str(e)}
    return {"agent_id": agent_id, "response": text, "timestamp": _now(), "platform": platform}


def _run_jobs(run: RecordedRun, jobs: list[tuple[str, int, str]], timeout: float) -> dict[str, dict[str, Any]]:
    """Answer (platform, agent_id, prompt) jobs in parallel; key results like the live path."""
    results: dict[str, dict[str, Any]] = {}
    if not jobs:
        return results
    llm = LLMClient()
    pool = ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_LLM_CALLS, len(jobs)))
    try:
        futures = {pool.submit(_answer_one, llm, run, p, a, q): (p, a) for p, a, q in jobs}
        done, _ = wait(futures, timeout=timeout)
        for future, (platform, agent_id) in futures.items():
            if future in done:
                results[f"{platform}_{agent_id}"] = future.result()
            else:
                results[f"{platform}_{agent_id}"] = {"agent_id": agent_id, "response": None, "platform": platform,
                                                     "error": f"timed out after {timeout}s"}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def _as_int(agent_id: Any) -> int | None:
    try:
        return int(agent_id)
    except (TypeError, ValueError):
        return None


def reconstructed_batch(
    sim_dir: str, interviews: list[dict[str, Any]], platform: str | None = None, timeout: float = 120.0
) -> dict[str, Any]:
    """Batch interview from the recorded run. Same shape as SimulationRunner.interview_agents_batch."""
    run = RecordedRun(sim_dir)
    available = run.platforms()
    jobs = []
    for interview in interviews:
        agent_id = _as_int(interview.get("agent_id"))
        if agent_id is None:
            continue
        # Same resolution as ParallelIPCHandler.handle_batch_interview.
        item_platform = interview.get("platform", platform)
        targets = [item_platform] if item_platform in PLATFORMS else list(PLATFORMS)
        jobs.extend((p, agent_id, interview.get("prompt", "")) for p in targets if p in available)

    base = {"interviews_count": len(interviews), "timestamp": _now(), "mode": InterviewMode.RECONSTRUCTED.value}
    if not available:
        return {"success": False, **base, "error": "No recorded profiles for this simulation; nothing to interview"}
    if not jobs:
        return {"success": False, **base,
                "error": f"No valid agent_id on a recorded platform (recorded: {', '.join(available)})"}
    results = _run_jobs(run, jobs, timeout)
    if not any(r.get("response") for r in results.values()):
        errors = sorted({r.get("error", "no response") for r in results.values()})
        if results and all("timed out" in e for e in errors):
            raise TimeoutError(f"Reconstructed interviews timed out ({timeout}s)")
        return {"success": False, **base, "error": "no successful interviews: " + "; ".join(errors)}
    return {"success": True, **base, "result": {"interviews_count": len(results), "results": results}}


def reconstructed_single(
    sim_dir: str, agent_id: int, prompt: str, platform: str | None = None, timeout: float = 60.0
) -> dict[str, Any]:
    """Single interview from the recorded run. Same shape as SimulationRunner.interview_agent."""
    batch = reconstructed_batch(sim_dir, [{"agent_id": agent_id, "prompt": prompt, "platform": platform}],
                                platform=platform, timeout=timeout)
    base = {"agent_id": agent_id, "prompt": prompt, "timestamp": batch["timestamp"],
            "mode": InterviewMode.RECONSTRUCTED.value}
    if not batch["success"]:
        return {"success": False, **base, "error": batch["error"]}
    results = batch["result"]["results"]
    if platform in PLATFORMS:
        return {"success": True, **base, "result": results[f"{platform}_{_as_int(agent_id)}"]}
    platforms = {key.split("_", 1)[0]: value for key, value in results.items()}
    return {"success": True, **base, "result": {"agent_id": agent_id, "prompt": prompt, "platforms": platforms}}


# ============== Dispatch: live IPC when the process is alive, else reconstructed ==============


def interview_single(simulation_id: str, agent_id: int, prompt: str, platform: str | None = None,
                     timeout: float = 60.0) -> dict[str, Any]:
    sim_dir = _require_sim_dir(simulation_id)
    if SimulationRunner.check_env_alive(simulation_id):
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id, agent_id=agent_id, prompt=prompt, platform=platform, timeout=timeout
        )
        return {**result, "mode": InterviewMode.LIVE.value}
    logger.info(f"Process gone, reconstructing interview: simulation_id={simulation_id}, agent_id={agent_id}")
    return reconstructed_single(sim_dir, agent_id, prompt, platform, timeout)


def interview_batch(simulation_id: str, interviews: list[dict[str, Any]], platform: str | None = None,
                    timeout: float = 120.0) -> dict[str, Any]:
    sim_dir = _require_sim_dir(simulation_id)
    if SimulationRunner.check_env_alive(simulation_id):
        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id, interviews=interviews, platform=platform, timeout=timeout
        )
        return {**result, "mode": InterviewMode.LIVE.value}
    logger.info(f"Process gone, reconstructing {len(interviews)} interviews: simulation_id={simulation_id}")
    return reconstructed_batch(sim_dir, interviews, platform, timeout)


def interview_all(simulation_id: str, prompt: str, platform: str | None = None,
                  timeout: float = 180.0) -> dict[str, Any]:
    sim_dir = _require_sim_dir(simulation_id)
    if SimulationRunner.check_env_alive(simulation_id):
        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id, prompt=prompt, platform=platform, timeout=timeout
        )
        return {**result, "mode": InterviewMode.LIVE.value}
    run = RecordedRun(sim_dir)
    if not run.agent_configs:
        raise ValueError(f"No Agents in simulation config: {simulation_id}")
    interviews = [{"agent_id": agent_id, "prompt": prompt} for agent_id in run.agent_configs]
    return reconstructed_batch(sim_dir, interviews, platform, timeout)


def interview_status(simulation_id: str) -> dict[str, Any]:
    """Whether interviews can be answered, and by which path."""
    try:
        sim_dir = _require_sim_dir(simulation_id)
    except SimulationNotFoundError:
        return {"interview_available": False, "interview_mode": None}
    if SimulationRunner.check_env_alive(simulation_id):
        return {"interview_available": True, "interview_mode": InterviewMode.LIVE.value}
    available = bool(RecordedRun(sim_dir).platforms())
    return {"interview_available": available,
            "interview_mode": InterviewMode.RECONSTRUCTED.value if available else None}
