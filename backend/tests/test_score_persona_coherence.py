"""Tests for scripts/score_persona_coherence.py (task T5).

The scorer mirrors docs/simulation-quality-audit.md's corrected definitions:
quotes are counted on the ACTION stream, quote_content is the quoting agent's
own words, and institutional anecdotes use the audit's regex and org set.
"""
import json
import os
import sqlite3
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))

from score_persona_coherence import (  # noqa: E402
    ANECDOTE_REGEX,
    main,
    run_report,
)

TWITTER_POST_SCHEMA = """
CREATE TABLE post (
    post_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_post_id INTEGER,
    content TEXT DEFAULT '',
    quote_content TEXT,
    created_at DATETIME,
    num_likes INTEGER DEFAULT 0,
    num_dislikes INTEGER DEFAULT 0,
    num_shares INTEGER DEFAULT 0,
    num_reports INTEGER DEFAULT 0
);
"""


def write_actions(sim_dir, platform, actions):
    path = os.path.join(sim_dir, platform, "actions.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for act in actions:
            fh.write(json.dumps(act) + "\n")


def make_db(sim_dir, platform, rows):
    """Create a minimal platform_simulation.db with a post table."""
    db_path = os.path.join(sim_dir, f"{platform}_simulation.db")
    con = sqlite3.connect(db_path)
    con.execute(TWITTER_POST_SCHEMA)
    con.executemany(
        "INSERT INTO post (post_id, user_id, original_post_id, content, quote_content)"
        " VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    con.commit()
    con.close()


def quote(round_, agent, qc, quoted_content="original text", action_type="QUOTE_POST"):
    return {
        "round": round_,
        "agent_id": 1,
        "agent_name": agent,
        "action_type": action_type,
        "action_args": {
            "quoted_id": 1,
            "new_post_id": 2,
            "original_content": quoted_content,
            "original_author_name": "someone",
            "quote_content": qc,
        },
        "success": True,
    }


def post(round_, agent, content):
    return {
        "round": round_,
        "agent_id": 1,
        "agent_name": agent,
        "action_type": "CREATE_POST",
        "action_args": {"content": content},
        "success": True,
    }


def like(round_, agent):
    return {
        "round": round_,
        "agent_id": 1,
        "agent_name": agent,
        "action_type": "LIKE_POST",
        "action_args": {"post_id": 1},
        "success": True,
    }


@pytest.fixture
def sim_dir(tmp_path):
    """Synthetic mini sim dir: 3 quotes (1 empty, 1 institutional anecdote),
    1 GP anecdote (not institutional -> must NOT count), 1 post, 1 like.

    Rounds 0-1 land in the first window (seed round grouped in).
    """
    platform = "twitter"
    actions = [
        post(0, "pharmacies", "seed post"),
        quote(1, "NHS England", ""),  # empty-commentary quote
        quote(1, "NHS England", "Just finished surgery and the data is clear."),
        quote(1, "GPs", "Just finished surgery, my own practice data backs this."),
        post(2, "GPs", "another original"),
        like(2, "pharmacies"),
    ]
    write_actions(tmp_path, platform, actions)
    # 5 originals, 2 distinct; 1 quote row with real commentary, 1 empty.
    make_db(
        tmp_path,
        platform,
        [
            (1, 1, None, "dup text A", None),
            (2, 1, None, "dup text A", None),
            (3, 1, None, "unique text B", None),
            (4, 1, None, "unique text C", None),
            (5, 1, None, "unique text D", None),
            (6, 1, 1, "quoted", "real commentary"),
            (7, 1, 1, "quoted", ""),
        ],
    )
    return tmp_path


def test_quote_ratio_math(sim_dir):
    report = run_report(str(sim_dir), ["NHS England"])
    tw = report["platforms"][0]
    # 6 actions, 3 quotes -> 50%
    assert tw["total_actions"] == 6
    assert tw["quotes"] == 3
    assert tw["quote_ratio"] == pytest.approx(0.5)
    assert report["combined"]["quote_ratio"] == pytest.approx(0.5)


def test_window_breakdown(sim_dir):
    report = run_report(str(sim_dir), ["NHS England"])
    windows = report["platforms"][0]["windows"]
    # seed round 0 grouped into the first window: rounds 0-2 here.
    assert windows[0]["label"] == "1-8"
    assert windows[0]["total_actions"] == 6
    assert windows[0]["quotes"] == 3
    assert windows[0]["quote_ratio"] == pytest.approx(0.5)
    assert windows[0]["creates"] == 2
    assert windows[0]["likes"] == 1
    assert len(windows) == 1


def test_empty_commentary_detection(sim_dir):
    report = run_report(str(sim_dir), ["NHS England"])
    tw = report["platforms"][0]
    assert tw["empty_commentary_quotes"] == 1
    detail = tw["empty_commentary_details"][0]
    assert detail["agent"] == "NHS England"
    assert detail["round"] == 1


def test_anecdote_detection_only_institutional(sim_dir):
    report = run_report(str(sim_dir), ["NHS England"])
    tw = report["platforms"][0]
    # NHS England's "Just finished surgery..." counts; GPs' identical phrase
    # is persona-correct and must not.
    assert tw["institutional_anecdotes"] == 1
    assert report["combined"]["institutional_anecdotes"] == 1
    detail = tw["anecdote_details"][0]
    assert detail["agent"] == "NHS England"
    assert detail["round"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "my practice data is clear",
        "Just finished surgery and the numbers are in",
        "I had to tell the practice manager",
        "my pharmacy had 40 consultations",
        "my own patients agree",
        "I spoke at the LPC meeting",
        "my PCN referred 321 patients",
    ],
)
def test_anecdote_regex_variants(text):
    assert ANECDOTE_REGEX.search(text)


def test_anecdote_regex_ignores_institutional_voice():
    assert not ANECDOTE_REGEX.search(
        "Pharmacy First continues to deliver: 3.3 million consultations."
    )
    assert not ANECDOTE_REGEX.search(
        "Anecdotal reports are consistent with our workforce models."
    )


def test_distinct_original_math(sim_dir):
    report = run_report(str(sim_dir), ["NHS England"])
    tw = report["platforms"][0]
    assert tw["db"]["originals"] == 5
    assert tw["db"]["distinct_originals"] == 4
    assert tw["db"]["distinct_original_ratio"] == pytest.approx(4 / 5)
    assert tw["db"]["db_quote_rows"] == 2
    assert tw["db"]["db_empty_quote_rows"] == 1


def test_agent_action_mix(sim_dir):
    report = run_report(str(sim_dir), ["NHS England"])
    mix = report["platforms"][0]["agent_action_mix"]
    assert mix["NHS England"]["QUOTE_POST"] == 2
    assert mix["GPs"]["QUOTE_POST"] == 1
    assert mix["pharmacies"]["CREATE_POST"] == 1


def test_fail_gates_violation(sim_dir, capsys):
    rc = main(
        [
            str(sim_dir),
            "--fail-if-quote-ratio",
            "0.25",
            "--fail-if-anecdotes",
            "0",
        ]
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "GATE VIOLATION" in out
    assert "quote ratio" in out
    assert "institutional anecdotes" in out


def test_fail_gates_pass(sim_dir, capsys):
    rc = main(
        [
            str(sim_dir),
            "--fail-if-quote-ratio",
            "0.9",
            "--fail-if-anecdotes",
            "5",
            "--json",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out)["combined"]["institutional_anecdotes"] == 1


def test_default_exit_zero(sim_dir):
    assert main([str(sim_dir)]) == 0


def test_reddit_no_quotes_does_not_crash(tmp_path):
    write_actions(tmp_path, "reddit", [post(0, "GPs", "reddit post")])
    make_db(
        tmp_path,
        "reddit",
        [(1, 1, None, "reddit original", None)],
    )
    report = run_report(str(tmp_path), ["NHS England"])
    # twitter has no actions -> excluded; reddit-only report.
    assert len(report["platforms"]) == 1
    rd = report["platforms"][0]
    assert rd["platform"] == "reddit"
    assert rd["quotes"] == 0
    assert rd["quote_ratio"] == 0.0
    assert rd["db"]["originals"] == 1
