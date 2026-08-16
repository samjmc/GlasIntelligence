#!/usr/bin/env python3
"""Score simulation persona coherence against the methodology in
docs/simulation-quality-audit.md.

Measures, per platform (twitter/reddit) and combined:

- quote ratio on the ACTION stream (QUOTE_POST / total actions), including a
  per-round-window breakdown mirroring the audit's windows (seed round 0 is
  grouped with the first 8-round window, giving windows 1-8, 9-16, 17-24, ...);
- distinct-original ratio from the platform post table
  (distinct original content / total originals);
- empty-commentary quotes: QUOTE_POST actions whose quote_content (the quoting
  agent's own words) is empty or whitespace;
- institutional first-person anecdotes: QUOTE_POST actions by institutional
  accounts whose quote_content matches the audit's anecdote regex;
- per-agent action mix.

Usage:
    python3 scripts/score_persona_coherence.py <simulation_dir> [--json]
        [--fail-if-quote-ratio R] [--fail-if-anecdotes N]
        [--institutional-accounts a,b,c]

Exit code is 0 unless a gate flag is violated.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from typing import Iterable, Optional

# Corrected definition from docs/simulation-quality-audit.md: quote replies are
# answered with the agent's own words in quote_content; the audit's anecdote
# regex detects first-person clinical voice in those words.
ANECDOTE_REGEX = re.compile(
    r"my practice data|Just finished surgery|I had to tell|my pharmacy|my own|I spoke at|my PCN",
    re.IGNORECASE,
)

# Institutional accounts named by the audit (NHS England, NCHWA, ICBs).
DEFAULT_INSTITUTIONAL_ACCOUNTS = (
    "NHS England",
    "National Center for Healthcare Workforce Analysis",
    "care boards",
)

QUOTE_ACTIONS = {"QUOTE_POST"}

WINDOW_SIZE = 8


def iter_actions(sim_dir: str, platform: str) -> Iterable[dict]:
    """Yield action records from <sim_dir>/<platform>/actions.jsonl.

    Tolerates both bare action records (this sim's format) and records wrapped
    in an event stream (event_type == 'action').
    """
    path = os.path.join(sim_dir, platform, "actions.jsonl")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or not rec.get("action_type"):
                continue
            yield rec


def load_actions(sim_dir: str, platform: str) -> list[dict]:
    return list(iter_actions(sim_dir, platform))


def window_breakdown(actions: list[dict]) -> list[dict]:
    """Per-round-window quote stats, mirroring the audit's windowing.

    The seed round 0 is grouped with the first 8-round window (the audit's
    "1-8" window spans file rounds 0-8); later windows are 8 rounds each.
    """
    per_round: dict[int, Counter] = defaultdict(Counter)
    for act in actions:
        rnd = act.get("round", 0)
        try:
            rnd = int(rnd)
        except (TypeError, ValueError):
            rnd = 0
        per_round[rnd][act["action_type"]] += 1

    windows: list[dict] = []
    rnds = sorted(per_round)
    if not rnds:
        return windows
    lo = rnds[0]
    first = True
    while True:
        span = WINDOW_SIZE + (1 if first and rnds[0] == 0 else 0)
        hi = lo + span
        members = [r for r in rnds if lo <= r < hi]
        if not members:
            break
        if first and rnds[0] == 0:
            label = "1-8"
        else:
            label = f"{lo}-{hi - 1}"
        win_actions = sum(
            sum(per_round[r].values()) for r in members
        )
        win_quotes = sum(
            per_round[r][t] for r in members for t in QUOTE_ACTIONS
        )
        win_creates = sum(per_round[r]["CREATE_POST"] for r in members)
        win_likes = sum(per_round[r]["LIKE_POST"] for r in members)
        windows.append(
            {
                "label": label,
                "rounds": [members[0], members[-1]],
                "total_actions": win_actions,
                "quotes": win_quotes,
                "quote_ratio": win_quotes / win_actions if win_actions else 0.0,
                "creates": win_creates,
                "likes": win_likes,
            }
        )
        lo = hi
        first = False
    return windows


def db_post_stats(db_path: str) -> Optional[dict]:
    """Distinct-original ratio from the platform post table."""
    if not os.path.exists(db_path):
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT content) FROM post "
            "WHERE original_post_id IS NULL"
        ).fetchone()
        quote_rows = con.execute(
            "SELECT COUNT(*) FROM post "
            "WHERE original_post_id IS NOT NULL AND quote_content IS NOT NULL"
        ).fetchone()
        empty_quote_rows = con.execute(
            "SELECT COUNT(*) FROM post "
            "WHERE original_post_id IS NOT NULL "
            "AND trim(coalesce(quote_content, '')) = ''"
        ).fetchone()
    finally:
        con.close()
    originals, distinct = int(row[0]), int(row[1])
    return {
        "originals": originals,
        "distinct_originals": distinct,
        "distinct_original_ratio": (
            distinct / originals if originals else 0.0
        ),
        "db_quote_rows": int(quote_rows[0]),
        "db_empty_quote_rows": int(empty_quote_rows[0]),
    }


def compute_platform(sim_dir: str, platform: str,
                     institutional: Iterable[str]) -> dict:
    actions = load_actions(sim_dir, platform)
    total = len(actions)
    type_counts = Counter(a["action_type"] for a in actions)
    quotes = sum(type_counts[t] for t in QUOTE_ACTIONS)

    empty_commentaries: list[dict] = []
    anecdotes: list[dict] = []
    institutional_set = set(institutional)
    for act in actions:
        args = act.get("action_args") or {}
        qc = args.get("quote_content")
        qc = "" if qc is None else str(qc)
        if act["action_type"] not in QUOTE_ACTIONS:
            continue
        if not qc.strip():
            empty_commentaries.append(
                {"round": act.get("round"), "agent": act.get("agent_name")}
            )
        if act.get("agent_name") in institutional_set and ANECDOTE_REGEX.search(qc):
            anecdotes.append(
                {
                    "round": act.get("round"),
                    "agent": act.get("agent_name"),
                    "quote_content": qc,
                }
            )

    agent_mix: dict[str, Counter] = defaultdict(Counter)
    for act in actions:
        agent_mix[str(act.get("agent_name"))][act["action_type"]] += 1

    db_path = os.path.join(sim_dir, f"{platform}_simulation.db")
    return {
        "platform": platform,
        "total_actions": total,
        "action_type_counts": dict(type_counts),
        "quotes": quotes,
        "quote_ratio": quotes / total if total else 0.0,
        "empty_commentary_quotes": len(empty_commentaries),
        "empty_commentary_details": empty_commentaries,
        "institutional_anecdotes": len(anecdotes),
        "anecdote_details": anecdotes,
        "db": db_post_stats(db_path),
        "windows": window_breakdown(actions),
        "agent_action_mix": {name: dict(c) for name, c in agent_mix.items()},
    }


def merge_combined(platforms: list[dict]) -> dict:
    total = sum(p["total_actions"] for p in platforms)
    quotes = sum(p["quotes"] for p in platforms)
    empty = sum(p["empty_commentary_quotes"] for p in platforms)
    anecdotes = sum(p["institutional_anecdotes"] for p in platforms)
    originals = sum(
        (p["db"] or {}).get("originals", 0) for p in platforms
    )
    distinct = sum(
        (p["db"] or {}).get("distinct_originals", 0) for p in platforms
    )
    return {
        "total_actions": total,
        "quotes": quotes,
        "quote_ratio": quotes / total if total else 0.0,
        "empty_commentary_quotes": empty,
        "institutional_anecdotes": anecdotes,
        "distinct_originals": distinct,
        "originals": originals,
        "distinct_original_ratio": (
            distinct / originals if originals else 0.0
        ),
    }


def run_report(sim_dir: str, institutional: Iterable[str]) -> dict:
    platforms = [
        compute_platform(sim_dir, "twitter", institutional),
        compute_platform(sim_dir, "reddit", institutional),
    ]
    platforms = [p for p in platforms if p["total_actions"] > 0]
    return {
        "simulation_dir": sim_dir,
        "institutional_accounts": list(institutional),
        "platforms": platforms,
        "combined": merge_combined(platforms),
    }


def render_human(report: dict) -> str:
    lines = [f"Simulation: {report['simulation_dir']}"]
    for p in report["platforms"]:
        lines.append("")
        lines.append(f"--- {p['platform'].upper()} ---")
        lines.append(f"total actions: {p['total_actions']}")
        lines.append(
            f"quote ratio (actions): {p['quotes']}/{p['total_actions']} "
            f"({p['quote_ratio']:.0%})"
        )
        for w in p["windows"]:
            lines.append(
                f"  rounds {w['label']}: {w['total_actions']} actions, "
                f"{w['quotes']} quotes ({w['quote_ratio']:.0%}), "
                f"{w['creates']} creates, {w['likes']} likes"
            )
        if p["db"]:
            d = p["db"]
            lines.append(
                f"distinct-original ratio: {d['distinct_originals']}/"
                f"{d['originals']} ({d['distinct_original_ratio']:.0%})"
            )
            lines.append(
                f"db quote rows: {d['db_quote_rows']} "
                f"(empty quote_content: {d['db_empty_quote_rows']})"
            )
        else:
            lines.append("distinct-original ratio: n/a (no db)")
        lines.append(
            f"empty-commentary quotes: {p['empty_commentary_quotes']}"
        )
        lines.append(
            f"institutional first-person anecdotes: {p['institutional_anecdotes']}"
        )
        lines.append("per-agent action mix:")
        for agent, mix in p["agent_action_mix"].items():
            lines.append(f"  {agent}: {mix}")
    c = report["combined"]
    lines.append("")
    lines.append("--- COMBINED ---")
    lines.append(f"total actions: {c['total_actions']}")
    lines.append(f"quote ratio: {c['quotes']}/{c['total_actions']} ({c['quote_ratio']:.0%})")
    lines.append(
        f"distinct-original ratio: {c['distinct_originals']}/{c['originals']} "
        f"({c['distinct_original_ratio']:.0%})"
    )
    lines.append(f"empty-commentary quotes: {c['empty_commentary_quotes']}")
    lines.append(
        f"institutional first-person anecdotes: {c['institutional_anecdotes']}"
    )
    return "\n".join(lines)


def gate_violations(report: dict, quote_ratio: Optional[float],
                    anecdotes: Optional[int]) -> list[str]:
    violations: list[str] = []
    ratios = [p["quote_ratio"] for p in report["platforms"]]
    ratios.append(report["combined"]["quote_ratio"])
    if quote_ratio is not None:
        for r in ratios:
            if r > quote_ratio:
                violations.append(
                    f"quote ratio {r:.2%} exceeds --fail-if-quote-ratio "
                    f"{quote_ratio:.2%}"
                )
    if anecdotes is not None and (
        report["combined"]["institutional_anecdotes"] > anecdotes
    ):
        violations.append(
            f"institutional anecdotes "
            f"{report['combined']['institutional_anecdotes']} exceeds "
            f"--fail-if-anecdotes {anecdotes}"
        )
    return violations


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score persona coherence of a simulation directory."
    )
    parser.add_argument("simulation_dir", help="Path to the sim dir")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument(
        "--fail-if-quote-ratio", type=float, default=None, metavar="R",
        help="Exit 1 if any platform or the combined quote ratio exceeds R",
    )
    parser.add_argument(
        "--fail-if-anecdotes", type=int, default=None, metavar="N",
        help="Exit 1 if institutional first-person anecdotes exceed N",
    )
    parser.add_argument(
        "--institutional-accounts", default=",".join(DEFAULT_INSTITUTIONAL_ACCOUNTS),
        help="Comma-separated institutional account names",
    )
    args = parser.parse_args(argv)

    institutional = [a.strip() for a in args.institutional_accounts.split(",") if a.strip()]
    report = run_report(args.simulation_dir, institutional)
    violations = gate_violations(
        report, args.fail_if_quote_ratio, args.fail_if_anecdotes
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_human(report))
        for v in violations:
            print(f"GATE VIOLATION: {v}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
