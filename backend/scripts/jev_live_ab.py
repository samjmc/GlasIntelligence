"""Live A/B for Jev: repeated runs of one recorded simulation, Jev off vs Jev active.

Rebuilds a simulation directory (config + agent profiles) from a golden demo tape and
runs the real OASIS simulation in both arms, alternating them so a provider slowdown
hits both:

    off     JEV_MODE=off     (today's behaviour)
    active  JEV_MODE=active  (activation weighting + the live post-validity monitor)

Every run is its own process (``--only <arm>``). Two runs in one process leaked state
between them (db_utils keeps the first run's ToolCallLogger, builtins.open is re-wrapped
on each import), so the parent only orchestrates. Agent tools are OFF in both arms: tool
roles and scenario tools re-roll per run and would be a second variable. Activation is
seeded per platform (OASIS_SEED), but OASIS's recommender still draws from the global
RNG, so runs are independent samples, not pairs: arms are compared with an exact
permutation test.

Per run (the opening posts excluded, because they are identical in both arms; each
platform also reported on its own): actions, posts with text, distinct texts, quote
share, speakers per round, voice evenness (Gini of actions across agents), the smallest
agent's share, validity (both arms scored after the run with the live monitor's own
questions), wall time, exact LLM tokens (the ``usage`` of every chat completion),
agent-call errors counted from stderr, and the Jev ledger.

    cd backend && uv run --frozen python scripts/jev_live_ab.py \\
        --tape ../frontend/public/demo/pharmacy-first-caps/tape.json --rounds 8 --repeats 5 --out <dir>

Needs LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME for the agents, and Jev (JEV_API_KEY,
JEV_PROVIDER, ...) for the active arm and the validity scoring. Zep, Tavily and Supabase
are NOT used.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import importlib
import itertools
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "scripts" / "lib"))

CONTENT_TYPES = {"CREATE_POST", "CREATE_COMMENT", "QUOTE_POST"}
PLATFORMS = ("twitter", "reddit")
ARMS = ("off", "active")
PLATFORM_METRICS = (
    "actions",
    "posts_with_text",
    "distinct_texts",
    "quote_share",
    "speakers_per_round",
    "gini",
    "min_agent_share",
)
# Agent-call failures never reach simulation.log; they surface on stderr.
LLM_ERROR_RE = re.compile(
    r"\b(BadRequestError|RateLimitError|APIConnectionError|APITimeoutError|"
    r"InternalServerError|AuthenticationError|APIError)\b"
)
EXACT_PERMUTATION_LIMIT = 20_000
SAMPLED_PERMUTATIONS = 10_000


def _last(entries: list[dict], pred) -> dict | None:
    hits = [e for e in entries if pred(e)]
    return hits[-1] if hits else None


def build_sim_dir(tape_path: Path, sim_dir: Path, sim_id: str) -> dict[str, Any]:
    tape = json.loads(tape_path.read_text(encoding="utf-8"))
    entries = tape["entries"]
    cfg_e = _last(entries, lambda e: e["path"].endswith("/config") or e["path"].endswith("/config/realtime"))
    if not cfg_e:
        raise SystemExit("tape has no simulation config")
    body = cfg_e["body"]
    cfg = body.get("data") or body
    cfg = dict(cfg.get("config") or cfg)
    prof_e = _last(entries, lambda e: "profiles/realtime" in e["path"])
    profiles = prof_e["body"]["data"]["profiles"] if prof_e else []
    if not profiles:
        raise SystemExit("tape has no agent profiles")

    if sim_dir.exists():
        shutil.rmtree(sim_dir)
    sim_dir.mkdir(parents=True)
    cfg["simulation_id"] = sim_id
    cfg.pop("llm_base_url", None)  # use this machine's LLM settings, not the recorder's
    cfg.pop("llm_model", None)
    # Tool roles and scenario tools re-roll every run (temperature 0.7), so with tools on
    # the arms would differ in two things, not one.
    cfg["enable_agent_tools"] = False

    reddit = []
    for i, p in enumerate(profiles):
        reddit.append(
            {
                "user_id": p.get("user_id", i),
                "username": p.get("username"),
                "name": p.get("name"),
                "bio": (p.get("bio") or p.get("name") or "")[:150],
                "persona": p.get("persona") or f"{p.get('name')} is a participant in social discussions.",
                "karma": p.get("karma") or 1000,
                "created_at": p.get("created_at"),
                "age": p.get("age") or 30,
                "gender": p.get("gender") or "other",
                "mbti": p.get("mbti") or "ISTJ",
                "country": p.get("country") or "United Kingdom",
                **({"profession": p["profession"]} if p.get("profession") else {}),
                **({"interested_topics": p["interested_topics"]} if p.get("interested_topics") else {}),
            }
        )
    (sim_dir / "reddit_profiles.json").write_text(json.dumps(reddit, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(sim_dir / "twitter_profiles.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "name", "username", "user_char", "description"])
        for i, p in enumerate(profiles):
            bio = (p.get("bio") or "").replace("\n", " ").replace("\r", " ")
            persona = (p.get("persona") or "").replace("\n", " ").replace("\r", " ")
            char = f"{bio} {persona}".strip() if persona and persona != bio else bio
            w.writerow([i, p.get("name"), p.get("username"), char, bio])
    (sim_dir / "simulation_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def read_actions(sim_dir: Path) -> list[dict]:
    out: list[dict] = []
    for plat in PLATFORMS:
        p = sim_dir / plat / "actions.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("agent_name") and d.get("action_type"):
                d["platform"] = plat
                out.append(d)
    return out


def _text(a: dict) -> str:
    args = a.get("action_args") or {}
    return (args.get("quote_content") if a.get("action_type") == "QUOTE_POST" else args.get("content")) or ""


# --------------------------------------------------------------------------- metrics


def gini(values: list[int]) -> float | None:
    """0 = every agent acted equally often, towards 1 = one agent did everything."""
    n, total = len(values), sum(values)
    if n == 0 or total == 0:
        return None
    return sum(abs(a - b) for a in values for b in values) / (2 * n * total)


def _key(a: dict) -> tuple:
    return (a.get("platform"), a["agent_name"], a["action_type"], _text(a))


def experiment_actions(acts: list[dict]) -> list[dict]:
    """Actions from round 1 on, without the opening posts. Round 0's posts are the same
    in both arms, and the runner logs them AGAIN as round 1 (its first read of the
    platform DB starts at row 0; measured: all 8 on reddit), so both copies go."""
    opening = {_key(a) for a in acts if (a.get("round") or 0) == 0}
    return [a for a in acts if (a.get("round") or 0) > 0 and not (a["round"] == 1 and _key(a) in opening)]


def platform_metrics(acts: list[dict], agent_names: list[str]) -> dict[str, Any]:
    """Metrics over the experiment's own actions. Agents who never acted count as zeros."""
    acts = experiment_actions(acts)
    content = [a for a in acts if a.get("action_type") in CONTENT_TYPES and _text(a).strip()]
    by_agent = Counter(a["agent_name"] for a in acts)
    counts = [by_agent.get(n, 0) for n in agent_names] + [c for n, c in by_agent.items() if n not in agent_names]
    speakers: dict[int, set[str]] = defaultdict(set)
    for a in acts:
        speakers[a["round"]].add(a["agent_name"])
    total = len(acts)
    return {
        "actions": total,
        "posts_with_text": len(content),
        "distinct_texts": len({_text(a).strip() for a in content}),
        "quote_share": round(sum(a["action_type"] == "QUOTE_POST" for a in content) / len(content), 3)
        if content
        else None,
        "speakers_per_round": round(statistics.mean(len(s) for s in speakers.values()), 2) if speakers else None,
        "gini": None if (g := gini(counts)) is None else round(g, 3),
        "min_agent_share": round(min(counts) / total, 3) if total and counts else None,
        "actions_by_agent": dict(by_agent.most_common()),
    }


def run_metrics(sim_dir: Path) -> dict[str, Any]:
    cfg = json.loads((sim_dir / "simulation_config.json").read_text(encoding="utf-8"))
    names = [str(ac.get("entity_name") or f"Agent_{ac.get('agent_id')}") for ac in cfg.get("agent_configs", [])]
    acts = read_actions(sim_dir)
    out = {"all": platform_metrics(acts, names)}
    for plat in PLATFORMS:
        out[plat] = platform_metrics([a for a in acts if a["platform"] == plat], names)
    return out


# --------------------------------------------------------------------------- exact LLM usage


class UsageCounter:
    """Sums the ``usage`` block of every chat completion made in this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.calls_without_usage = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cache_hit_tokens = 0

    def add(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        with self._lock:
            self.calls += 1
            if usage is None:
                self.calls_without_usage += 1
                return
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            # DeepSeek reports its context-cache hits as an extra field.
            self.cache_hit_tokens += int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)

    def as_dict(self) -> dict[str, int]:
        with self._lock:
            return {
                "calls": self.calls,
                "calls_without_usage": self.calls_without_usage,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cache_hit_tokens": self.cache_hit_tokens,
            }


def install_usage_counter() -> UsageCounter:
    """Wrap the openai client methods CAMEL calls, for this harness process only:
    ``create``, and ``parse`` for structured replies (``client.beta.chat.completions`` is
    the same class; ``parse`` posts on its own, so nothing is counted twice)."""
    from openai.resources.chat import completions as chat

    counter = UsageCounter()

    def wrap_sync(cls: type, name: str) -> None:
        orig = getattr(cls, name)

        def wrapper(self, *args, **kwargs):
            response = orig(self, *args, **kwargs)
            counter.add(response)
            return response

        setattr(cls, name, wrapper)

    def wrap_async(cls: type, name: str) -> None:
        orig = getattr(cls, name)

        async def wrapper(self, *args, **kwargs):
            response = await orig(self, *args, **kwargs)
            counter.add(response)
            return response

        setattr(cls, name, wrapper)

    wrap_sync(chat.Completions, "create")
    wrap_async(chat.AsyncCompletions, "create")
    wrap_sync(chat.Completions, "parse")
    wrap_async(chat.AsyncCompletions, "parse")
    return counter


# --------------------------------------------------------------------------- one run (child)


def run_arm(sim_dir: Path, arm: str, rounds: int, seed: int) -> dict[str, Any]:
    os.environ["JEV_MODE"] = arm  # before anything imports app.config
    from time_utils import SEED_ENV

    os.environ[SEED_ENV] = str(seed)
    random.seed(seed)
    usage = install_usage_counter()
    from app.utils.jev_metrics import LEDGER

    rps = importlib.import_module("run_parallel_simulation")
    sys.argv = [
        "run_parallel_simulation.py",
        "--config",
        str(sim_dir / "simulation_config.json"),
        "--max-rounds",
        str(rounds),
        "--no-wait",
    ]
    started = time.perf_counter()
    with contextlib.suppress(SystemExit):
        asyncio.run(rps.main())
    return {
        "arm": arm,
        "seed": seed,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "llm_usage": usage.as_dict(),
        "jev_live": LEDGER.summary()["totals"],
        "metrics": run_metrics(sim_dir),
    }


# --------------------------------------------------------------------------- orchestration (parent)


def count_llm_errors(stderr_text: str) -> dict[str, int]:
    """One count per stderr line that names an openai error class."""
    counts: Counter[str] = Counter()
    for line in stderr_text.splitlines():
        m = LLM_ERROR_RE.search(line)
        if m:
            counts[m.group(1)] += 1
    return dict(counts)


def deepseek_balance() -> float | None:
    """Account balance in USD, a whole-batch cross-check only (the API gives 2 decimals)."""
    if "deepseek" not in os.environ.get("LLM_BASE_URL", "").lower():
        return None
    try:
        import requests  # type: ignore[import-untyped]

        resp = requests.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {os.environ.get('LLM_API_KEY', '')}"},
            timeout=15,
        )
        resp.raise_for_status()
        infos = resp.json().get("balance_infos") or []
        usd = [float(i["total_balance"]) for i in infos if i.get("currency") == "USD"]
        return usd[0] if usd else None
    except Exception as e:
        print(f"(DeepSeek balance unavailable: {e})", flush=True)
        return None


def score_validity(sim_dir: Path, out_dir: Path, client: Any) -> dict[str, Any] | None:
    """Score every post from round 1 on with the live monitor's own questions, in both arms."""
    from app.services.jev_simulation_gates import ValidityMonitor

    cfg = json.loads((sim_dir / "simulation_config.json").read_text(encoding="utf-8"))
    if out_dir.exists():
        shutil.rmtree(out_dir)  # the monitor appends; a re-run must not double-count
    monitor = ValidityMonitor(str(out_dir), cfg.get("agent_configs", []), jev=client)
    if not monitor.enabled:
        return None
    by_round: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for a in experiment_actions(read_actions(sim_dir)):
        by_round[(a["platform"], a["round"])].append(a)
    for key in sorted(by_round):
        monitor.score_round(key[1], by_round[key])
    rows = []
    if Path(monitor.jsonl_path).exists():
        rows = [json.loads(line) for line in Path(monitor.jsonl_path).read_text(encoding="utf-8").splitlines()]
    on_p = [r["on_persona_p"] for r in rows]
    new_p = [r["adds_new_content_p"] for r in rows if r.get("adds_new_content_p") is not None]
    return {
        "scored": len(on_p),
        "on_persona_mean": round(statistics.mean(on_p), 3) if on_p else None,
        "share_below_0_3": round(sum(p < 0.3 for p in on_p) / len(on_p), 3) if on_p else None,
        "quote_restating_share": round(sum(p < 0.5 for p in new_p) / len(new_p), 3) if new_p else None,
    }


def permutation_p(a: list[float], b: list[float]) -> float | None:
    """Two-sided p for a difference in means, over every relabelling (sampled if too many)."""
    if len(a) < 2 or len(b) < 2:
        return None
    pooled = a + b
    observed = abs(statistics.mean(a) - statistics.mean(b))
    n, k = len(pooled), len(a)

    def diff(idx: tuple[int, ...]) -> float:
        chosen = set(idx)
        xs = [pooled[i] for i in idx]
        ys = [pooled[i] for i in range(n) if i not in chosen]
        return abs(statistics.mean(xs) - statistics.mean(ys))

    if math.comb(n, k) <= EXACT_PERMUTATION_LIMIT:
        combos: Any = itertools.combinations(range(n), k)
        total = math.comb(n, k)
    else:
        rng = random.Random(0)
        combos = (tuple(rng.sample(range(n), k)) for _ in range(SAMPLED_PERMUTATIONS))
        total = SAMPLED_PERMUTATIONS
    hits = sum(diff(c) >= observed - 1e-12 for c in combos)
    return round(hits / total, 4)


def flatten(run: dict[str, Any]) -> dict[str, float | None]:
    """The scalar metrics compared between arms. No dollar estimate: DeepSeek bills cache
    hits at a fraction of the input price (list prices gave 5x the measured balance drop),
    so cache-miss tokens are the cost signal and the balance delta is the real spend."""
    row: dict[str, float | None] = {}
    for scope in ("all", *PLATFORMS):
        for k in PLATFORM_METRICS:
            row[f"{scope}.{k}"] = run["metrics"][scope][k]
    usage = run["llm_usage"]
    row["wall_seconds"] = run["wall_seconds"]
    row["llm_prompt_tokens"] = usage["prompt_tokens"]
    row["llm_completion_tokens"] = usage["completion_tokens"]
    row["llm_cache_miss_tokens"] = usage["prompt_tokens"] - usage.get("cache_hit_tokens", 0)
    row["llm_errors"] = sum(run.get("llm_errors", {}).values())
    row["jev_live_cost_usd"] = run["jev_live"]["jev_cost_usd"]
    validity = run.get("validity") or {}
    row["validity_on_persona_mean"] = validity.get("on_persona_mean")
    row["validity_share_below_0_3"] = validity.get("share_below_0_3")
    return row


def compare(rows_by_arm: dict[str, list[dict[str, float | None]]]) -> list[dict[str, Any]]:
    out = []
    for key in rows_by_arm["off"][0]:
        a = [r[key] for r in rows_by_arm["off"] if r[key] is not None]
        b = [r[key] for r in rows_by_arm["active"] if r[key] is not None]
        out.append(
            {
                "metric": key,
                "off_mean": round(statistics.mean(a), 6) if a else None,
                "off_sd": round(statistics.stdev(a), 6) if len(a) > 1 else None,
                "active_mean": round(statistics.mean(b), 6) if b else None,
                "active_sd": round(statistics.stdev(b), 6) if len(b) > 1 else None,
                "n_off": len(a),
                "n_active": len(b),
                "p": permutation_p(a, b),
            }
        )
    return out


def render_table(comparison: list[dict[str, Any]]) -> str:
    def cell(mean, sd):
        if mean is None:
            return "—"
        return f"{mean:g} ± {sd:g}" if sd is not None else f"{mean:g}"

    lines = [
        "| metric | off (mean ± sd) | active (mean ± sd) | n off / active | permutation p |",
        "|---|---|---|---|---|",
    ]
    for c in comparison:
        p = c["p"]
        flag = " **(p < 0.05)**" if p is not None and p < 0.05 else ""
        lines.append(
            f"| {c['metric']} | {cell(c['off_mean'], c['off_sd'])} | {cell(c['active_mean'], c['active_sd'])} "
            f"| {c['n_off']} / {c['n_active']} | {'—' if p is None else p}{flag} |"
        )
    return "\n".join(lines)


def run_batch(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ["JEV_MODE"] = "active"  # for this process's validity scoring; each child sets its own
    from app.utils.jev_client import JevClient
    from app.utils.jev_metrics import LEDGER

    client = JevClient.from_config()
    if client is None:
        print("Jev is not configured: validity will not be scored in either arm", flush=True)
    balance_before = deepseek_balance()

    runs: list[dict[str, Any]] = []
    for i in range(args.repeats):
        for arm in ARMS:
            run_dir = out / f"r{i + 1}_{arm}"
            run_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--only",
                arm,
                "--tape",
                str(Path(args.tape).resolve()),
                "--rounds",
                str(args.rounds),
                "--seed",
                str(args.seed + i),
                "--out",
                str(run_dir),
            ]
            print(f"\n===== repeat {i + 1}/{args.repeats} arm {arm.upper()} -> {run_dir}", flush=True)
            with (
                open(run_dir / "stdout.log", "w", encoding="utf-8") as so,
                open(run_dir / "stderr.log", "w", encoding="utf-8") as se,
            ):
                code = subprocess.call(cmd, stdout=so, stderr=se, env={**os.environ, "JEV_MODE": arm}, cwd=BACKEND)
            summary_path = run_dir / "run_summary.json"
            if code != 0 or not summary_path.exists():
                print(f"  run failed (exit {code}); see {run_dir / 'stderr.log'}", flush=True)
                continue
            run = json.loads(summary_path.read_text(encoding="utf-8"))
            run["llm_errors"] = count_llm_errors((run_dir / "stderr.log").read_text(encoding="utf-8", errors="replace"))
            run["validity"] = score_validity(run_dir / "sim", run_dir / "posthoc_validity", client) if client else None
            runs.append(run)
            print(json.dumps(flatten(run), indent=1), flush=True)

    balance_after = deepseek_balance()
    rows_by_arm = {arm: [flatten(r) for r in runs if r["arm"] == arm] for arm in ARMS}
    comparison = compare(rows_by_arm) if all(rows_by_arm.values()) else []
    result = {
        "tape": args.tape,
        "rounds_cap": args.rounds,
        "repeats": args.repeats,
        "seed_base": args.seed,
        "runs_completed": {arm: len(rows_by_arm[arm]) for arm in ARMS},
        "deepseek_balance_usd": {
            "before": balance_before,
            "after": balance_after,
            "spent": None
            if balance_before is None or balance_after is None
            else round(balance_before - balance_after, 2),
        },
        "posthoc_validity_jev": LEDGER.summary()["totals"],
        "comparison": comparison,
        "runs": runs,
    }
    (out / "ab_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    table = render_table(comparison) if comparison else "(not enough completed runs to compare)"
    (out / "ab_table.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)
    print(f"\n-> {out / 'ab_summary.json'}")
    return 0 if all(rows_by_arm.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tape", required=True)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--repeats", type=int, default=5, help="runs per arm")
    ap.add_argument("--seed", type=int, default=7, help="repeat i uses seed + i in both arms")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=ARMS, default=None, help="internal: run ONE arm in this process")
    args = ap.parse_args()
    if args.only is None:
        return run_batch(args)
    run_dir = Path(args.out)
    build_sim_dir(Path(args.tape), run_dir / "sim", f"ab_{args.only}_{args.seed}")
    summary = run_arm(run_dir / "sim", args.only, args.rounds, args.seed)
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
