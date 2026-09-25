"""Record real Step 5 answers for a static demo scenario.

The static demo replays a tape and has no backend, so Step 5 (Deep Interaction)
can only show answers that were recorded ahead of time. This script records them
once from a golden tape and writes ``step5.json`` next to it:

- agent answers: every agent in the run, each of AGENT_QUESTIONS, through the same
  reconstructed-interview path the live backend uses once the OASIS process has
  exited (``services/offline_interview.py``), on reddit (the platform Step 5 shows);
- report-agent answers: each of REPORT_QUESTIONS, with the report agent's chat
  prompt and the recorded report text. The graph tools are left out (they are the
  paid Zep reads, and the prompt already tells the agent to answer from the report).

Costs LLM calls only: agents x 3 + 3 per scenario (about 30 per golden tape on
deepseek-flash, a few cents). No Zep, Tavily or Supabase is touched. Any empty
answer fails the run, so a half-recorded file is never written.

    cd backend && uv run --frozen python scripts/build_demo_step5.py \
        --tape ../frontend/public/demo/pharmacy-first-caps/tape.json \
        --tape ../frontend/public/demo/energy-price-cap/tape.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.simulation_helpers import optimize_interview_prompt  # noqa: E402
from app.config import Config  # noqa: E402
from app.services import offline_interview  # noqa: E402
from app.services.report_agent import CHAT_SYSTEM_PROMPT_TEMPLATE  # noqa: E402
from app.utils.llm_client import LLMClient  # noqa: E402

SCHEMA_VERSION = 1
PLATFORM = "reddit"  # Step 5 shows the reddit answer when both exist
REPORT_CHARS = 15000  # the same cut ReportAgent.chat makes
INTERVIEW_TIMEOUT_S = 300.0

AGENT_QUESTIONS = (
    "What was your position on this policy, and why?",
    "What surprised you most about how others reacted during the simulation?",
    "If you could change one thing about the policy, what would it be?",
)
REPORT_QUESTIONS = (
    "What is the single most important finding of this report?",
    "Which stakeholders are hit hardest, and how?",
    "What should a decision-maker watch for next?",
)
NO_TOOLS = "(None in this recorded answer: answer from the report above.)"


def _last_data(entries: list[dict[str, Any]], match) -> dict[str, Any]:
    hits = [e for e in entries if e["method"] == "GET" and match(e["path"].split("?")[0])]
    if not hits:
        raise SystemExit("tape has no entry the Step 5 recording needs")
    return hits[-1]["body"].get("data") or {}


def load_run(tape: dict[str, Any]) -> dict[str, Any]:
    """The config, reddit profiles, actions and report text the tape recorded."""
    entries = tape["entries"]
    config = _last_data(entries, lambda p: p.startswith("/api/simulation/") and p.endswith("/config"))
    profiles = _last_data(entries, lambda p: p.endswith("/profiles/realtime"))["profiles"]
    actions = _last_data(entries, lambda p: p.endswith("/run-status/detail"))["all_actions"]
    report = _last_data(entries, lambda p: re.fullmatch(r"/api/report/[^/]+", p) is not None)
    return {"config": config, "profiles": profiles, "actions": actions, "report": report}


def write_run_dir(run: dict[str, Any], sim_dir: Path) -> None:
    """Lay the recorded run out the way a finished simulation leaves it on disk."""
    (sim_dir / PLATFORM).mkdir(parents=True)
    (sim_dir / "simulation_config.json").write_text(json.dumps(run["config"]), encoding="utf-8")
    (sim_dir / "reddit_profiles.json").write_text(json.dumps(run["profiles"]), encoding="utf-8")
    lines = []
    for a in sorted(run["actions"], key=lambda a: a.get("timestamp", "")):
        if a.get("platform") != PLATFORM:
            continue
        entry = {k: v for k, v in a.items() if k not in ("platform", "round_num")}
        entry["round"] = a.get("round_num")
        lines.append(json.dumps(entry, ensure_ascii=False))
    (sim_dir / PLATFORM / "actions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def agent_answers(sim_dir: Path, agent_ids: list[int]) -> dict[int, list[str]]:
    answers: dict[int, list[str]] = {a: [] for a in agent_ids}
    for question in AGENT_QUESTIONS:
        prompt = optimize_interview_prompt(question)
        out = offline_interview.reconstructed_batch(
            str(sim_dir),
            [{"agent_id": a, "prompt": prompt, "platform": PLATFORM} for a in agent_ids],
            platform=PLATFORM,
            timeout=INTERVIEW_TIMEOUT_S,
        )
        results = (out.get("result") or {}).get("results", {})
        for a in agent_ids:
            text = (results.get(f"{PLATFORM}_{a}") or {}).get("response")
            if not text or not text.strip():
                raise SystemExit(f"agent {a} gave no answer to {question!r}: {results.get(f'{PLATFORM}_{a}')}")
            answers[a].append(text.strip())
        print(f"  agents answered: {question}")
    return answers


def report_answers(run: dict[str, Any], llm: LLMClient) -> list[str]:
    report_text = run["report"].get("markdown_content") or ""
    if not report_text:
        raise SystemExit("tape has no report text")
    if len(report_text) > REPORT_CHARS:
        report_text = report_text[:REPORT_CHARS] + "\n\n... [Report content truncated] ..."
    system = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
        simulation_requirement=run["config"].get("simulation_requirement", ""),
        report_content=report_text,
        tools_description=NO_TOOLS,
    )
    answers = []
    for question in REPORT_QUESTIONS:
        text = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": question}], temperature=0.5)
        # Same clean-up ReportAgent.chat applies to a reply
        text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL).strip()
        if not text:
            raise SystemExit(f"report agent gave no answer to {question!r}")
        answers.append(text)
        print(f"  report agent answered: {question}")
    return answers


def build(tape_path: Path) -> Path:
    tape = json.loads(tape_path.read_text(encoding="utf-8"))
    run = load_run(tape)
    agent_ids = sorted(int(c["agent_id"]) for c in run["config"]["agent_configs"] if c.get("agent_id") is not None)
    names = {int(c["agent_id"]): c.get("entity_name") for c in run["config"]["agent_configs"]}
    print(f"{tape['scenario']}: {len(agent_ids)} agents")
    with tempfile.TemporaryDirectory() as tmp:
        sim_dir = Path(tmp) / "run"
        write_run_dir(run, sim_dir)
        answers = agent_answers(sim_dir, agent_ids)
    bank = {
        "schema_version": SCHEMA_VERSION,
        "scenario": tape["scenario"],
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": Config.LLM_MODEL_NAME,
        "agent_questions": list(AGENT_QUESTIONS),
        "agents": {str(a): {"name": names.get(a), "answers": answers[a]} for a in agent_ids},
        "report_questions": list(REPORT_QUESTIONS),
        "report_answers": report_answers(run, LLMClient()),
    }
    out = tape_path.with_name("step5.json")
    out.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tape", action="append", required=True, type=Path)
    for tape_path in parser.parse_args().tape:
        print(f"wrote {build(tape_path)}")


if __name__ == "__main__":
    main()
