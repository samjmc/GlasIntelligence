"""Interviews after the OASIS process has exited (services/offline_interview.py).

Zep is never called: the offline path needs no graph, and nothing here talks to a network.
The LLM is a fake that records the messages it was sent.
"""

import csv
import json
import os
import time

import pytest

from app.services import offline_interview as oi
from app.services.simulation_runner import SimulationRunner

PERSONA_0 = "Persona-zero: a rural community pharmacist who fears the caps will close her branch."
PERSONA_1 = "Persona-one: a Treasury economist who believes the caps are overdue discipline."


class FakeLLM:
    """Stands in for LLMClient; answers in persona-agnostic text and records every call."""

    calls: list = []
    delay = 0.0
    fail = False

    def __init__(self, *args, **kwargs):
        pass

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        FakeLLM.calls.append(messages)
        if FakeLLM.delay:
            time.sleep(FakeLLM.delay)
        if FakeLLM.fail:
            raise RuntimeError("provider down")
        return "Recorded-run answer."


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    FakeLLM.calls = []
    FakeLLM.delay = 0.0
    FakeLLM.fail = False
    monkeypatch.setattr(oi, "LLMClient", FakeLLM)


def _write_actions(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "simulation_start", "platform": "x"}) + "\n")
        for e in entries:
            f.write(json.dumps(e) + "\n")
        f.write('{"round": 99, "agent_id": 0, "action_ty')  # partial last line from a killed run


def _action(round_num, agent_id, name, action_type, **args):
    return {"round": round_num, "agent_id": agent_id, "agent_name": name, "action_type": action_type,
            "action_args": args, "timestamp": f"2026-09-22T10:{round_num:02d}:00"}


@pytest.fixture
def sim_root(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def finished_run(sim_root):
    """A two-agent run on both platforms whose process has exited."""
    sim_dir = sim_root / "sim_done"
    sim_dir.mkdir()
    config = {
        "agent_configs": [
            {"agent_id": 0, "entity_name": "Rural Pharmacist", "entity_type": "Person", "stance": "opposing"},
            {"agent_id": 1, "entity_name": "Treasury Economist", "entity_type": "Person", "stance": "supportive"},
        ],
        "event_config": {"initial_posts": [
            {"poster_agent_id": 0, "content": "Opening post: the caps will close rural branches."},
        ]},
    }
    (sim_dir / "simulation_config.json").write_text(json.dumps(config), encoding="utf-8")
    reddit = [
        {"user_id": 0, "username": "rural_pharm_1", "name": "Rural Pharmacist", "bio": "Pharmacist.",
         "persona": PERSONA_0, "age": 44, "gender": "female", "mbti": "ISFJ", "country": "UK"},
        {"user_id": 1, "username": "treasury_econ_2", "name": "Treasury Economist", "bio": "Economist.",
         "persona": PERSONA_1, "age": 51, "gender": "male", "mbti": "INTJ", "country": "UK"},
    ]
    (sim_dir / "reddit_profiles.json").write_text(json.dumps(reddit), encoding="utf-8")
    with open(sim_dir / "twitter_profiles.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "name", "username", "user_char", "description"])
        w.writerow([0, "Rural Pharmacist", "rural_pharm_1", PERSONA_0, "Pharmacist."])
        w.writerow([1, "Treasury Economist", "treasury_econ_2", PERSONA_1, "Economist."])
    for platform in ("twitter", "reddit"):
        _write_actions(str(sim_dir / platform / "actions.jsonl"), [
            _action(0, 0, "Rural Pharmacist", "CREATE_POST", content="Opening post: the caps will close rural branches."),
            _action(1, 1, "Treasury Economist", "CREATE_COMMENT", content="Caps are overdue.",
                    post_author_name="Rural Pharmacist", post_content="Opening post"),
            _action(2, 0, "Rural Pharmacist", "DO_NOTHING"),
            _action(3, 0, "Rural Pharmacist", "QUOTE_POST", quote_content="Tell that to my patients.",
                    original_author_name="Treasury Economist", original_content="Caps are overdue."),
        ])
    (sim_dir / "env_status.json").write_text(json.dumps({"status": "stopped"}), encoding="utf-8")
    return sim_dir


def _system(messages):
    return messages[0]["content"]


# ---------- live path unchanged ----------


def test_live_process_uses_ipc_and_never_the_llm(finished_run, monkeypatch):
    seen = {}

    def fake_batch(**kwargs):
        seen.update(kwargs)
        return {"success": True, "interviews_count": 1, "result": {"interviews_count": 1, "results": {}},
                "timestamp": "t"}

    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, sid: True))
    monkeypatch.setattr(SimulationRunner, "interview_agents_batch", staticmethod(fake_batch))
    out = oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q"}], platform=None, timeout=5)

    assert seen == {"simulation_id": "sim_done", "interviews": [{"agent_id": 0, "prompt": "Q"}],
                    "platform": None, "timeout": 5}
    assert out["mode"] == "live"
    assert out["result"] == {"interviews_count": 1, "results": {}}  # existing fields untouched
    assert FakeLLM.calls == []


def test_live_single_keeps_ipc_result(finished_run, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, sid: True))
    monkeypatch.setattr(SimulationRunner, "interview_agent",
                        staticmethod(lambda **kw: {"success": True, "agent_id": kw["agent_id"], "result": {"x": 1}}))
    out = oi.interview_single("sim_done", 0, "Q", platform="twitter")
    assert out == {"success": True, "agent_id": 0, "result": {"x": 1}, "mode": "live"}
    assert FakeLLM.calls == []


# ---------- dead process: reconstructed ----------


def test_dead_process_batch_is_reconstructed_in_live_shape(finished_run):
    out = oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Why oppose the caps?"}])

    assert out["success"] is True
    assert out["mode"] == "reconstructed"
    assert out["interviews_count"] == 1
    results = out["result"]["results"]
    assert set(results) == {"twitter_0", "reddit_0"}  # dual platform, like the live handler
    assert out["result"]["interviews_count"] == 2
    for platform in ("twitter", "reddit"):
        r = results[f"{platform}_0"]
        assert r["agent_id"] == 0 and r["platform"] == platform
        assert r["response"] == "Recorded-run answer."
    assert len(FakeLLM.calls) == 2
    assert all(m[-1] == {"role": "user", "content": "Why oppose the caps?"} for m in FakeLLM.calls)


def test_single_platform_and_dual_platform_single_shapes(finished_run):
    one = oi.interview_single("sim_done", 1, "Q", platform="reddit")
    assert one["success"] and one["mode"] == "reconstructed"
    assert one["result"]["platform"] == "reddit" and one["result"]["agent_id"] == 1

    both = oi.interview_single("sim_done", 1, "Q")
    assert set(both["result"]["platforms"]) == {"twitter", "reddit"}
    assert both["result"]["agent_id"] == 1 and both["result"]["prompt"] == "Q"


def test_interview_all_uses_config_agents(finished_run):
    out = oi.interview_all("sim_done", "Q", platform="twitter")
    assert set(out["result"]["results"]) == {"twitter_0", "twitter_1"}


def test_prompt_matches_what_the_agent_did_and_what_others_said(finished_run):
    oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q", "platform": "twitter"}])
    system = _system(FakeLLM.calls[0])

    assert "Your name is rural_pharm_1." in system
    assert "You represent Rural Pharmacist (Person). Your stance on the topic: opposing." in system
    assert "Opening post: the caps will close rural branches." in system  # round-0 post, logged once
    assert system.count("Opening post: the caps will close rural branches.") == 1
    assert "Tell that to my patients." in system  # its own quote
    assert "DO_NOTHING" not in system  # non-opinion actions skipped
    assert "Treasury Economist: commented on Rural Pharmacist's post" in system  # reply TO the agent


def test_initial_posts_come_from_config_when_the_log_lacks_round_zero(finished_run):
    path = finished_run / "twitter" / "actions.jsonl"
    _write_actions(str(path), [_action(1, 1, "Treasury Economist", "CREATE_POST", content="Unrelated.")])
    oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q", "platform": "twitter"}])
    assert "Opening post: the caps will close rural branches." in _system(FakeLLM.calls[0])


def test_persona_never_includes_another_agents_persona(finished_run):
    # Distinct prompts tie each LLM call back to the agent it was for.
    oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q-agent-0"}, {"agent_id": 1, "prompt": "Q-agent-1"}])
    assert len(FakeLLM.calls) == 4
    own = {0: (PERSONA_0, "rural_pharm_1"), 1: (PERSONA_1, "treasury_econ_2")}
    for messages in FakeLLM.calls:
        agent_id = int(messages[-1]["content"].rsplit("-", 1)[1])
        system = _system(messages)
        persona, username = own[agent_id]
        other_persona, other_username = own[1 - agent_id]
        assert persona in system and f"Your name is {username}." in system
        assert other_persona not in system and f"Your name is {other_username}." not in system


def test_memory_cap_is_honoured(finished_run):
    entries = [_action(0, 0, "Rural Pharmacist", "CREATE_POST", content="Opening post: the caps will close rural branches.")]
    entries += [_action(r, 0, "Rural Pharmacist", "CREATE_POST", content=f"own-post-{r:03d}") for r in range(1, 61)]
    entries += [_action(r, 1, "Treasury Economist", "CREATE_COMMENT", content=f"reply-{r:03d}",
                        post_author_name="Rural Pharmacist") for r in range(1, 26)]
    entries += [_action(r, 1, "Treasury Economist", "CREATE_POST", content=f"mention of Rural Pharmacist {r:03d}")
                for r in range(30, 40)]
    _write_actions(str(finished_run / "twitter" / "actions.jsonl"), entries)

    oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q", "platform": "twitter"}])
    system = _system(FakeLLM.calls[0])

    own = system.split("# WHAT YOU DID")[1].split("# WHAT OTHERS SAID")[0]
    others = system.split("# WHAT OTHERS SAID")[1].split("# INTERVIEW")[0]
    own_lines = [ln for ln in own.splitlines() if ln.startswith("- Round")]
    other_lines = [ln for ln in others.splitlines() if ln.startswith("- Round")]
    assert len(own_lines) == oi.MAX_OWN_ACTIONS == 30
    assert len(other_lines) == oi.MAX_REPLIES == 10
    assert "Opening post" in own_lines[0]  # round-0 post always kept, first
    assert "own-post-060" in own and "own-post-032" in own and "own-post-031" not in own  # the latest 29
    # direct replies outrank mere mentions; the most recent direct replies win
    assert all("reply-" in ln for ln in other_lines)
    assert "reply-025" in others and "reply-016" in others and "reply-015" not in others


def test_memory_lines_are_truncated(finished_run):
    long_text = "x" * (oi.MAX_MEMORY_LINE_CHARS * 3)
    _write_actions(str(finished_run / "twitter" / "actions.jsonl"),
                   [_action(1, 0, "Rural Pharmacist", "CREATE_POST", content=long_text)])
    oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q", "platform": "twitter"}])
    line = next(ln for ln in _system(FakeLLM.calls[0]).splitlines() if "xxxx" in ln)
    assert len(line) <= oi.MAX_MEMORY_LINE_CHARS + len("- Round 1: ")


def test_unknown_agent_gets_an_error_entry_not_a_crash(finished_run):
    out = oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q"}, {"agent_id": 7, "prompt": "Q"}],
                             platform="twitter")
    assert out["success"] is True
    assert out["result"]["results"]["twitter_7"]["response"] is None
    assert "not found" in out["result"]["results"]["twitter_7"]["error"]


def test_one_bad_record_does_not_sink_the_batch(finished_run, monkeypatch):
    real = oi.build_interview_messages
    monkeypatch.setattr(oi, "build_interview_messages",
                        lambda run, p, a, q: (_ for _ in ()).throw(KeyError("bad row")) if a == 1 else real(run, p, a, q))
    out = oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q"}, {"agent_id": 1, "prompt": "Q"}],
                             platform="twitter")
    assert out["success"] is True
    assert out["result"]["results"]["twitter_0"]["response"] == "Recorded-run answer."
    assert "bad row" in out["result"]["results"]["twitter_1"]["error"]


def test_nothing_to_interview_says_why(finished_run):
    (finished_run / "reddit_profiles.json").unlink()
    out = oi.interview_single("sim_done", 0, "Q", platform="reddit")
    assert out["success"] is False and "recorded: twitter" in out["error"]
    assert FakeLLM.calls == []


def test_llm_failure_on_every_agent_is_a_clean_failure(finished_run):
    FakeLLM.fail = True
    out = oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q"}])
    assert out["success"] is False and "provider down" in out["error"] and out["mode"] == "reconstructed"


def test_timeout_raises_like_the_live_path(finished_run, monkeypatch):
    FakeLLM.delay = 2.0
    with pytest.raises(TimeoutError):
        oi.interview_batch("sim_done", [{"agent_id": 0, "prompt": "Q", "platform": "twitter"}], timeout=0.2)


# ---------- missing simulation ----------


@pytest.mark.parametrize("sim_id", ["sim_missing", "..", "../sim_done", "a/b", ""])
def test_missing_or_unsafe_simulation_is_not_found(sim_root, sim_id):
    with pytest.raises(oi.SimulationNotFoundError):
        oi.interview_batch(sim_id, [{"agent_id": 0, "prompt": "Q"}])
    assert FakeLLM.calls == []


# ---------- status ----------


def test_status_reports_reconstructed_when_process_gone(finished_run):
    assert oi.interview_status("sim_done") == {"interview_available": True, "interview_mode": "reconstructed"}
    assert oi.interview_status("sim_missing") == {"interview_available": False, "interview_mode": None}


def test_status_reports_live_when_alive(finished_run, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, sid: True))
    assert oi.interview_status("sim_done") == {"interview_available": True, "interview_mode": "live"}


# ---------- check_env_alive no longer trusts a stale "alive" ----------


def _stale_alive(sim_dir, pid):
    (sim_dir / "env_status.json").write_text(json.dumps({"status": "alive"}), encoding="utf-8")
    (sim_dir / "run_state.json").write_text(json.dumps({"simulation_id": sim_dir.name, "process_pid": pid}),
                                            encoding="utf-8")
    SimulationRunner._run_states.pop(sim_dir.name, None)
    SimulationRunner._processes.pop(sim_dir.name, None)


def test_check_env_alive_false_when_recorded_pid_is_gone(finished_run):
    import psutil

    dead_pid = max(psutil.pids()) + 100000
    _stale_alive(finished_run, dead_pid)
    assert SimulationRunner.check_env_alive("sim_done") is False


def test_check_env_alive_false_when_recorded_pid_is_reused_by_another_process(finished_run):
    _stale_alive(finished_run, os.getpid())  # alive, but not this run's OASIS process
    assert SimulationRunner.check_env_alive("sim_done") is False


def test_check_env_alive_true_when_recorded_pid_runs(finished_run):
    import subprocess
    import sys

    config_path = os.path.join(SimulationRunner.RUN_STATE_DIR, "sim_done", "simulation_config.json")
    # Same argv shape as SimulationRunner.start_simulation: <python> <script> --config <config_path>
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "--config", config_path])
    try:
        _stale_alive(finished_run, proc.pid)
        assert SimulationRunner.check_env_alive("sim_done") is True
    finally:
        proc.kill()
        proc.wait()


def test_check_env_alive_trusts_status_file_without_a_pid(finished_run):
    _stale_alive(finished_run, None)
    assert SimulationRunner.check_env_alive("sim_done") is True


# ---------- the report agent's interview_agents tool ----------


def test_report_interview_tool_works_after_process_exit(finished_run, monkeypatch):
    from unittest.mock import MagicMock

    from app.services.zep_tools import ZepToolsService

    svc = ZepToolsService.__new__(ZepToolsService)  # no Zep client: this path needs no graph
    svc._llm_client = MagicMock()
    agent = {"realname": "Rural Pharmacist", "username": "rural_pharm_1", "profession": "Pharmacist", "bio": "b"}
    monkeypatch.setattr(svc, "_load_agent_profiles", lambda sid: [agent])
    monkeypatch.setattr(svc, "_select_agents_for_interview", lambda **kw: ([agent], [0], "only one"))
    monkeypatch.setattr(svc, "_generate_interview_summary", lambda **kw: "summary")
    retry_modes = []
    monkeypatch.setattr(svc, "_retry_malformed_interview_answers",
                        lambda *a, mode="live": retry_modes.append(mode) or a[3])

    result = svc.interview_agents("sim_done", "caps", custom_questions=["Why?"])

    assert result.interview_mode == "reconstructed"
    assert retry_modes == ["reconstructed"]  # a retry would go down the same path
    assert result.interviewed_count == 1
    assert "Recorded-run answer." in result.interviews[0].response
    assert "reconstructed from the recorded run" in result.to_text()
    assert result.to_dict()["interview_mode"] == "reconstructed"


# ---------- the persona prompt matches OASIS ----------


def test_system_prompt_matches_oasis_userinfo(finished_run, tmp_path, monkeypatch):
    """Our persona block is OASIS's own system message up to '# RESPONSE METHOD'."""
    (tmp_path / "log").mkdir(exist_ok=True)  # oasis.social_agent.agent opens ./log/... at import
    monkeypatch.chdir(tmp_path)
    config_mod = pytest.importorskip("oasis.social_platform.config")
    UserInfo = config_mod.UserInfo
    run = oi.RecordedRun(str(finished_run))

    tw = run.profile("twitter", 0)
    ours = oi.oasis_system_prompt("twitter", tw)
    theirs = UserInfo(name=tw["username"], description=tw["description"],
                      profile={"nodes": [], "edges": [], "other_info": {"user_profile": tw["user_char"]}},
                      recsys_type="twitter").to_system_message()
    assert ours.strip() == theirs.split("# RESPONSE METHOD")[0].strip()

    rd = run.profile("reddit", 1)
    ours = oi.oasis_system_prompt("reddit", rd)
    other_info = {"user_profile": rd["persona"], "mbti": rd["mbti"], "gender": rd["gender"],
                  "age": rd["age"], "country": rd["country"]}
    theirs = UserInfo(name=rd["username"], description=rd["bio"],
                      profile={"nodes": [], "edges": [], "other_info": other_info},
                      recsys_type="reddit").to_system_message()
    assert ours.strip() == theirs.split("# RESPONSE METHOD")[0].strip()


# ---------- HTTP contract of the routes ----------


@pytest.fixture
def api(monkeypatch):
    import zep_cloud

    # A stale local lockfile ships a zep_cloud without AddNodeItem/EpisodeData, which breaks
    # create_app() at import. Only fill the gap; with a current zep_cloud this does nothing.
    for name in ("AddNodeItem", "EpisodeData"):
        if not hasattr(zep_cloud, name):
            monkeypatch.setattr(zep_cloud, name, type(name, (), {}), raising=False)
    from app import create_app

    from .conftest import TestConfig

    return create_app(TestConfig).test_client()


def test_route_batch_after_process_exit_is_answered_not_400(api, finished_run):
    res = api.post("/api/simulation/interview/batch",
                   json={"simulation_id": "sim_done", "interviews": [{"agent_id": 0, "prompt": "Why?"}]})
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["data"]["mode"] == "reconstructed"
    assert body["data"]["result"]["results"]["reddit_0"]["response"] == "Recorded-run answer."
    # the route adds optimize_interview_prompt's plain-text rules before the question
    assert FakeLLM.calls[0][-1]["content"].endswith("Why?")
    assert "without using any tools" in FakeLLM.calls[0][-1]["content"]


def test_route_single_and_all_after_process_exit(api, finished_run):
    one = api.post("/api/simulation/interview",
                   json={"simulation_id": "sim_done", "agent_id": 1, "prompt": "Q", "platform": "twitter"})
    assert one.status_code == 200 and one.get_json()["data"]["mode"] == "reconstructed"
    every = api.post("/api/simulation/interview/all", json={"simulation_id": "sim_done", "prompt": "Q"})
    assert every.status_code == 200
    assert set(every.get_json()["data"]["result"]["results"]) == {"twitter_0", "twitter_1", "reddit_0", "reddit_1"}


@pytest.mark.parametrize("path,payload", [
    ("/api/simulation/interview", {"agent_id": 0, "prompt": "Q"}),
    ("/api/simulation/interview/batch", {"interviews": [{"agent_id": 0, "prompt": "Q"}]}),
    ("/api/simulation/interview/all", {"prompt": "Q"}),
])
def test_route_missing_simulation_is_404(api, sim_root, path, payload):
    res = api.post(path, json={"simulation_id": "sim_missing", **payload})
    assert res.status_code == 404
    assert "does not exist" in res.get_json()["error"]


def test_route_env_status_keeps_old_fields_and_adds_interview_availability(api, finished_run):
    data = api.post("/api/simulation/env-status", json={"simulation_id": "sim_done"}).get_json()["data"]
    assert data["env_alive"] is False
    assert {"twitter_available", "reddit_available", "message"} <= set(data)
    assert data["interview_available"] is True
    assert data["interview_mode"] == "reconstructed"
    assert "recorded run" in data["message"]


def test_route_env_status_live(api, finished_run, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, sid: True))
    data = api.post("/api/simulation/env-status", json={"simulation_id": "sim_done"}).get_json()["data"]
    assert data["env_alive"] is True and data["interview_mode"] == "live"


def test_route_live_still_goes_through_ipc(api, finished_run, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, sid: True))
    monkeypatch.setattr(SimulationRunner, "interview_agents_batch",
                        staticmethod(lambda **kw: {"success": True, "interviews_count": 1,
                                                   "result": {"results": {"reddit_0": {"response": "live!"}}}}))
    body = api.post("/api/simulation/interview/batch",
                    json={"simulation_id": "sim_done", "interviews": [{"agent_id": 0, "prompt": "Q"}]}).get_json()
    assert body["data"]["mode"] == "live"
    assert body["data"]["result"]["results"]["reddit_0"]["response"] == "live!"
    assert FakeLLM.calls == []
