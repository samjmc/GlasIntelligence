"""Live A/B: run the same recorded simulation with Jev off and with Jev active.

Rebuilds a simulation directory (config + agent profiles) from a golden demo tape,
then runs the real OASIS simulation in-process twice with identical settings:

    A: JEV_MODE=off     (today's behaviour)
    B: JEV_MODE=active  (activation weighting, post-validity monitor, effect targets)

and writes a comparison to <out>/ab_summary.json. Needs a working LLM key for the
agents (LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME) and Jev configured for run B.
Zep, Tavily and Supabase are NOT used.

    cd backend && uv run --frozen python scripts/jev_live_ab.py \
        --tape ../frontend/public/demo/pharmacy-first-caps/tape.json --rounds 8 --out <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import importlib
import json
import os
import random
import shutil
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "scripts" / "lib"))

CONTENT_TYPES = {"CREATE_POST", "CREATE_COMMENT", "QUOTE_POST"}


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
    for plat in ("twitter", "reddit"):
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


def summarise_run(sim_dir: Path, seconds: float, ledger: dict[str, Any] | None) -> dict[str, Any]:
    acts = read_actions(sim_dir)
    content = [a for a in acts if a.get("action_type") in CONTENT_TYPES and _text(a).strip()]
    texts = [_text(a).strip() for a in content]
    by_agent = Counter(a["agent_name"] for a in acts)
    rounds = sorted({a.get("round") for a in acts if a.get("round") is not None})
    speakers_by_round: dict[int, set[str]] = {}
    for a in acts:
        r = a.get("round")
        if r is not None:
            speakers_by_round.setdefault(r, set()).add(a["agent_name"])
    validity = []
    vpath = sim_dir / "jev_validity.jsonl"
    if vpath.exists():
        for line in vpath.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                validity.append(json.loads(line))
    on_p = [v["on_persona_p"] for v in validity if v.get("on_persona_p") is not None]
    new_p = [v["adds_new_content_p"] for v in validity if v.get("adds_new_content_p") is not None]
    alert_path = sim_dir / "jev_validity_alert.json"
    return {
        "wall_seconds": round(seconds, 1),
        "actions": len(acts),
        "content_actions": len(content),
        "distinct_texts": len(set(texts)),
        "quote_share_of_content": round(sum(1 for a in content if a["action_type"] == "QUOTE_POST") / len(content), 3)
        if content
        else None,
        "action_types": dict(Counter(a["action_type"] for a in acts).most_common()),
        "actions_by_agent": dict(by_agent.most_common()),
        "rounds_with_activity": len(rounds),
        "mean_distinct_speakers_per_round": round(statistics.mean(len(s) for s in speakers_by_round.values()), 2)
        if speakers_by_round
        else None,
        "validity_scored": len(validity),
        "validity_on_persona_mean": round(statistics.mean(on_p), 3) if on_p else None,
        "validity_share_below_0_3": round(sum(1 for p in on_p if p < 0.3) / len(on_p), 3) if on_p else None,
        "validity_quote_restating_share": round(sum(1 for p in new_p if p < 0.5) / len(new_p), 3) if new_p else None,
        "validity_alert": json.loads(alert_path.read_text(encoding="utf-8")) if alert_path.exists() else None,
        "jev_ledger": ledger,
    }


def run_once(sim_dir: Path, mode: str, rounds: int, seed: int) -> dict[str, Any]:
    os.environ["JEV_MODE"] = mode
    # Fresh Config so JEV_MODE takes effect; drop cached app/runner modules.
    for name in list(sys.modules):
        if (
            name == "app"
            or name.startswith("app.")
            or name in ("platform_runners", "time_utils", "run_parallel_simulation")
        ):
            del sys.modules[name]
    from app.utils.jev_metrics import LEDGER

    LEDGER.reset()
    random.seed(seed)
    rps = importlib.import_module("run_parallel_simulation")
    argv = sys.argv
    sys.argv = [
        "run_parallel_simulation.py",
        "--config",
        str(sim_dir / "simulation_config.json"),
        "--max-rounds",
        str(rounds),
        "--no-wait",
    ]
    started = time.perf_counter()
    try:
        asyncio.run(rps.main())
    except SystemExit:
        pass
    finally:
        sys.argv = argv
    seconds = time.perf_counter() - started
    ledger = LEDGER.summary() if mode != "off" else None
    return summarise_run(sim_dir, seconds, ledger)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tape", required=True)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["off", "active"], default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"tape": args.tape, "rounds_cap": args.rounds, "seed": args.seed}
    for mode in [m for m in ("off", "active") if args.only in (None, m)]:
        sim_dir = out / f"sim_{mode}"
        build_sim_dir(Path(args.tape), sim_dir, f"ab_{mode}")
        print(f"\n===== run {mode.upper()} -> {sim_dir}", flush=True)
        results[mode] = run_once(sim_dir, mode, args.rounds, args.seed)
        print(json.dumps({k: v for k, v in results[mode].items() if k != "jev_ledger"}, indent=2), flush=True)
    (out / "ab_summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {out / 'ab_summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
