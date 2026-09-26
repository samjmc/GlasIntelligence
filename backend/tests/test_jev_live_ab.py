"""The Jev A/B harness: metrics, exact LLM usage, error counting, statistics, seeding."""

import asyncio
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "scripts" / "lib"))

import jev_live_ab as ab  # noqa: E402
import time_utils  # noqa: E402

TAPE = BACKEND.parent / "frontend" / "public" / "demo" / "pharmacy-first-caps" / "tape.json"


def _act(rnd, name, kind="LIKE_POST", text=None, platform="twitter"):
    key = "quote_content" if kind == "QUOTE_POST" else "content"
    return {
        "round": rnd,
        "agent_name": name,
        "action_type": kind,
        "action_args": {key: text} if text else {},
        "platform": platform,
    }


def test_gini():
    assert ab.gini([2, 2, 2]) == 0
    assert ab.gini([0, 0, 3]) == pytest.approx(2 / 3)
    assert ab.gini([]) is None
    assert ab.gini([0, 0]) is None


def test_platform_metrics_skips_round_zero_and_counts_silent_agents():
    acts = [
        _act(0, "A", "CREATE_POST", "opening post"),  # identical in both arms: excluded
        _act(1, "A", "CREATE_POST", "opening post"),  # the runner's replay of it in round 1: excluded
        _act(1, "A", "CREATE_POST", "hello"),
        _act(1, "B", "QUOTE_POST", "hello"),
        _act(2, "A"),
    ]
    m = ab.platform_metrics(acts, ["A", "B", "C"])
    assert m["actions"] == 3
    assert m["posts_with_text"] == 2
    assert m["distinct_texts"] == 1
    assert m["quote_share"] == 0.5
    assert m["speakers_per_round"] == 1.5  # round 1: A,B; round 2: A
    assert m["min_agent_share"] == 0  # C never acted, and still counts
    assert m["gini"] == round(ab.gini([2, 1, 0]), 3)
    assert m["actions_by_agent"] == {"A": 2, "B": 1}


def test_experiment_actions_keeps_a_later_repeat_of_an_opening_post():
    acts = [_act(0, "A", "CREATE_POST", "x"), _act(1, "A", "CREATE_POST", "x"), _act(3, "A", "CREATE_POST", "x")]
    assert [a["round"] for a in ab.experiment_actions(acts)] == [3]  # only round 1 replays the opening


def test_run_metrics_reports_each_platform(tmp_path):
    cfg = {"agent_configs": [{"agent_id": 0, "entity_name": "A"}, {"agent_id": 1, "entity_name": "B"}]}
    (tmp_path / "simulation_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    for plat, rows in {
        "twitter": [_act(1, "A", "CREATE_POST", "t1")],
        "reddit": [_act(1, "B", "CREATE_COMMENT", "r1"), _act(2, "B")],
    }.items():
        (tmp_path / plat).mkdir()
        body = "\n".join(json.dumps({k: v for k, v in r.items() if k != "platform"}) for r in rows)
        (tmp_path / plat / "actions.jsonl").write_text(body + '\n{"event_type": "round_end"}\n', encoding="utf-8")

    m = ab.run_metrics(tmp_path)
    assert (m["all"]["actions"], m["twitter"]["actions"], m["reddit"]["actions"]) == (3, 1, 2)
    assert m["twitter"]["actions_by_agent"] == {"A": 1}
    assert m["reddit"]["min_agent_share"] == 0  # A is silent on reddit


def test_permutation_p():
    assert ab.permutation_p([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0
    # fully separated 5 vs 5: only the observed split and its mirror are as extreme
    assert ab.permutation_p([1, 2, 3, 4, 5], [6, 7, 8, 9, 10]) == round(2 / 252, 4)
    assert ab.permutation_p([1.0], [2.0, 3.0]) is None


def test_count_llm_errors():
    text = "\n".join(
        [
            "openai.BadRequestError: Error code: 400 - reasoning_content",
            "INFO normal line",
            "openai.RateLimitError: 429",
            "openai.BadRequestError: Error code: 400",
        ]
    )
    assert ab.count_llm_errors(text) == {"BadRequestError": 2, "RateLimitError": 1}


def test_usage_counter_sums_and_notes_missing_usage():
    c = ab.UsageCounter()
    c.add(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, prompt_cache_hit_tokens=60)))
    c.add(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=50, completion_tokens=5)))
    c.add(SimpleNamespace())  # e.g. a stream: no usage block
    assert c.as_dict() == {
        "calls": 3,
        "calls_without_usage": 1,
        "prompt_tokens": 150,
        "completion_tokens": 25,
        "cache_hit_tokens": 60,
    }


def test_install_usage_counter_wraps_sync_and_async(monkeypatch):
    from openai.resources.chat import completions as chat

    resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3))

    async def fake_async(self, *a, **k):
        return resp

    # monkeypatch restores the real methods after the test
    for name in ("create", "parse"):
        monkeypatch.setattr(chat.Completions, name, lambda self, *a, **k: resp)
        monkeypatch.setattr(chat.AsyncCompletions, name, fake_async)

    counter = ab.install_usage_counter()
    assert chat.Completions.create(None) is resp
    assert asyncio.run(chat.AsyncCompletions.create(None)) is resp
    chat.Completions.parse(None)
    asyncio.run(chat.AsyncCompletions.parse(None))
    assert counter.as_dict()["calls"] == 4
    assert counter.as_dict()["prompt_tokens"] == 28


def test_build_sim_dir_turns_agent_tools_off(tmp_path):
    cfg = ab.build_sim_dir(TAPE, tmp_path / "sim", "ab_test")
    saved = json.loads((tmp_path / "sim" / "simulation_config.json").read_text(encoding="utf-8"))
    assert cfg["enable_agent_tools"] is False
    assert saved["enable_agent_tools"] is False
    assert saved["agent_configs"]  # the tape's agents came through


def test_platform_rng(monkeypatch):
    monkeypatch.delenv(time_utils.SEED_ENV, raising=False)
    assert time_utils.platform_rng("twitter") is random  # unset: exactly the old behaviour

    monkeypatch.setenv(time_utils.SEED_ENV, "7")
    tw, rd = time_utils.platform_rng("twitter"), time_utils.platform_rng("reddit")
    assert isinstance(tw, random.Random)
    tw_draws = [tw.random() for _ in range(5)]
    assert tw_draws != [rd.random() for _ in range(5)]  # one stream per platform
    again = time_utils.platform_rng("twitter")
    assert [again.random() for _ in range(5)] == tw_draws  # same seed, same stream


def test_compare_and_table_flag_only_real_differences():
    def run(actions, cost):
        metrics = {s: {k: None for k in ab.PLATFORM_METRICS} for s in ("all", *ab.PLATFORMS)}
        metrics["all"]["actions"] = actions
        return {
            "metrics": metrics,
            "llm_usage": {"prompt_tokens": 1000, "completion_tokens": 100, "cache_hit_tokens": 850},
            "wall_seconds": 60,
            "jev_live": {"jev_cost_usd": cost},
        }

    rows = {
        "off": [ab.flatten(run(a, 0.0)) for a in (10, 11, 12, 13, 14)],
        "active": [ab.flatten(run(a, 0.01)) for a in (30, 31, 32, 33, 34)],
    }
    comp = {c["metric"]: c for c in ab.compare(rows)}
    assert comp["all.actions"]["p"] < 0.05
    assert comp["wall_seconds"]["p"] == 1.0
    assert comp["llm_cache_miss_tokens"]["off_mean"] == 150
    table = ab.render_table(list(comp.values()))
    assert "| all.actions |" in table and "(p < 0.05)" in table
    assert table.count("(p < 0.05)") == 2  # actions and the Jev cost, nothing else
