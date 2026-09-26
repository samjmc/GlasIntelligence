"""Opening posts (round 0) must not be replayed into round 1.

Drives the real OASIS platforms with ManualActions only, so no LLM is called. Measured
2026-09-25 before the fix: round 1 re-read the trace from rowid 0, so on reddit all 8
opening posts came back as round-1 CREATE_POSTs; on twitter only 1 did, because twitter
kept one opening post per agent and published 1 of the 8.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sqlite3
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
for _p in (_SCRIPTS, os.path.join(_SCRIPTS, "lib")):  # the paths run_parallel_simulation.py sets up
    if _p not in sys.path:
        sys.path.insert(0, _p)
import oasis  # noqa: E402
import platform_runners as pr  # noqa: E402
from camel.models import ModelFactory  # noqa: E402
from camel.types import ModelPlatformType  # noqa: E402
from db_utils import fetch_new_actions_from_db  # noqa: E402
from oasis import ActionType, ManualAction  # noqa: E402

NAMES = {0: "Alice", 1: "Bob", 2: "Cara"}
OPENING = [
    {"poster_agent_id": 0, "content": "opening one"},
    {"poster_agent_id": 0, "content": "opening two"},
    {"poster_agent_id": 0, "content": "opening three"},
    {"poster_agent_id": 1, "content": "opening four"},
]


def _model():
    # Never called: every action in these tests is a ManualAction.
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="unused",
        api_key="unused",
        url="http://127.0.0.1:9/v1",
    )


async def _make_env(platform: str, tmp_path):
    if platform == "twitter":
        profile = tmp_path / "twitter_profiles.csv"
        with open(profile, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["user_id", "name", "username", "user_char", "description"])
            for i, n in NAMES.items():
                w.writerow([i, n, n.lower(), f"{n} persona", f"{n} bio"])
        graph = await pr.generate_twitter_agent_graph_with_tools(
            profile_path=str(profile), model=_model(), available_actions=pr.TWITTER_ACTIONS
        )
        kind = oasis.DefaultPlatformType.TWITTER
    else:
        profile = tmp_path / "reddit_profiles.json"
        profile.write_text(
            json.dumps(
                [
                    {
                        "user_id": i, "username": n.lower(), "name": n, "bio": f"{n} bio",
                        "persona": f"{n} persona", "karma": 1000, "age": 30, "gender": "other",
                        "mbti": "ISTJ", "country": "Ireland",
                    }
                    for i, n in NAMES.items()
                ]
            ),
            encoding="utf-8",
        )
        graph = await pr.generate_reddit_agent_graph_with_tools(
            profile_path=str(profile), model=_model(), available_actions=pr.REDDIT_ACTIONS
        )
        kind = oasis.DefaultPlatformType.REDDIT
    db_path = str(tmp_path / f"{platform}.db")
    env = oasis.make(agent_graph=graph, platform=kind, database_path=db_path)
    await env.reset()
    return env, db_path


def _trace_posts(db_path: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT count(*) FROM trace WHERE action = 'create_post'").fetchone()[0]


@pytest.mark.parametrize("platform", ["twitter", "reddit"])
def test_round_one_does_not_replay_opening_posts(platform, tmp_path):
    async def scenario():
        env, db_path = await _make_env(platform, tmp_path)
        try:
            actions, accepted = pr._opening_actions(env.agent_graph, OPENING)
            assert len(accepted) == 4
            last_rowid = await pr._publish_opening_posts(env, actions, db_path, NAMES)

            # Every opening post reached the platform (twitter used to keep 1 per agent).
            assert _trace_posts(db_path) == 4
            # The old handoff (rowid 0) replays them: proves the check below can fail.
            replayed, _ = fetch_new_actions_from_db(db_path, 0, NAMES)
            assert sum(a["action_type"] == "CREATE_POST" for a in replayed) == 4

            # One round-1 post; round 1 must see exactly that and nothing from round 0.
            agent2 = env.agent_graph.get_agent(2)
            await env.step(
                {agent2: ManualAction(action_type=ActionType.CREATE_POST, action_args={"content": "round one"})}
            )
            round1, _ = fetch_new_actions_from_db(db_path, last_rowid, NAMES)
            posts = [(a["agent_name"], a["action_args"].get("content")) for a in round1 if a["action_type"] == "CREATE_POST"]
            assert posts == [("Cara", "round one")]
        finally:
            await env.close()

    asyncio.run(scenario())


def test_opening_actions_groups_by_agent_and_skips_unknown():
    class Graph:
        def get_agent(self, agent_id):
            if agent_id not in (0, 1):
                raise KeyError(agent_id)
            return f"agent{agent_id}"

    posts = OPENING + [{"poster_agent_id": 99, "content": "nobody"}]
    actions, accepted = pr._opening_actions(Graph(), posts)
    assert {k: [a.action_args["content"] for a in v] for k, v in actions.items()} == {
        "agent0": ["opening one", "opening two", "opening three"],
        "agent1": ["opening four"],
    }
    assert accepted == [(p["poster_agent_id"], p["content"]) for p in OPENING]
