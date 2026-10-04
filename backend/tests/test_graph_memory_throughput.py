"""Live graph memory keeps up on Graphiti, and its backlog is written before the report.

Measured 2026-10-04 on a full run: 688 actions, 18 s per 5-activity batch, only 115 written
when the app exited; the rest was lost. These tests pin the fixes.
"""

import json
import threading
import time

from app import config as app_config
from app.services import zep_graph_memory_updater as gm
from app.services.simulation_runner import RunnerStatus, SimulationRunner, SimulationRunState
from app.services.zep_graph_memory_updater import (
    MEMORY_SKIP_ACTIONS,
    AgentActivity,
    ZepGraphMemoryManager,
    ZepGraphMemoryUpdater,
)

LONG_POST = "Pharmacy First caps will close rural pharmacies across England, " * 6


def _act(action_type, **args):
    return AgentActivity("reddit", 1, "Jo Bloggs", action_type, args, 1, "t")


class RecordingStore:
    """Records every add_text and the thread that sent it."""

    def __init__(self, batch=None, delay=0.0):
        self.batch = batch
        self.delay = delay
        self.sends: list[tuple[str, str]] = []

    def preferred_memory_batch_size(self):
        return self.batch

    def add_text(self, graph_id, text):
        time.sleep(self.delay)
        self.sends.append((threading.current_thread().name, text))


# ---------- what one activity becomes ----------


def test_reactions_quote_only_the_start_of_the_post():
    text = _act("LIKE_POST", post_content=LONG_POST, post_author_name="CPE").to_episode_text()
    assert text.startswith("Jo Bloggs: liked CPE's post: \"Pharmacy First caps will close")
    assert text.endswith('..."') and len(text) < 160
    for kind, args in (
        ("DISLIKE_POST", {"post_content": LONG_POST}),
        ("LIKE_COMMENT", {"comment_content": LONG_POST, "comment_author_name": "NPA"}),
        ("DISLIKE_COMMENT", {"comment_content": LONG_POST}),
        ("REPOST", {"original_content": LONG_POST, "original_author_name": "IPA"}),
    ):
        assert len(_act(kind, **args).to_episode_text()) < 160, kind


def test_own_words_are_kept_in_full():
    comment = "We will lobby every MP in the county against these caps before March."
    text = _act("CREATE_COMMENT", content=comment, post_content=LONG_POST, post_author_name="CPE").to_episode_text()
    assert comment in text and LONG_POST not in text
    quote = _act("QUOTE_POST", original_content=LONG_POST, quote_content=comment).to_episode_text()
    assert comment in quote and LONG_POST not in quote
    assert LONG_POST.strip() in _act("CREATE_POST", content=LONG_POST.strip()).to_episode_text()


def test_actions_without_content_are_skipped():
    updater = ZepGraphMemoryUpdater("g", store=RecordingStore())
    for kind in sorted(MEMORY_SKIP_ACTIONS):
        updater.add_activity(_act(kind))
    updater.add_activity(_act("CREATE_POST", content="hello"))
    assert updater._skipped_count == len(MEMORY_SKIP_ACTIONS) and updater._total_activities == 1
    assert {"SEARCH_POSTS", "SEARCH_USER", "TREND", "REFRESH", "DO_NOTHING"} <= MEMORY_SKIP_ACTIONS


# ---------- batch size ----------


def test_batch_size_comes_from_the_store_else_config(monkeypatch):
    monkeypatch.setattr(app_config.Config, "ZEP_GRAPH_MEMORY_BATCH_SIZE", 7)
    monkeypatch.setattr(app_config.Config, "ZEP_GRAPH_MEMORY_SEND_INTERVAL_SEC", 0.25)
    assert ZepGraphMemoryUpdater("g", store=RecordingStore(batch=20)).BATCH_SIZE == 20
    plain = ZepGraphMemoryUpdater("g", store=RecordingStore(batch=None))
    assert (plain.BATCH_SIZE, plain.SEND_INTERVAL) == (7, 0.25)  # the env settings are read now


def test_graphiti_prefers_twenty():
    from app.services.graph_store.graphiti_store import GraphitiGraphStore

    assert app_config.Config.GRAPHITI_MEMORY_BATCH_SIZE == 20
    assert GraphitiGraphStore.preferred_memory_batch_size(object.__new__(GraphitiGraphStore)) == 20


# ---------- draining ----------


def test_stop_sends_the_backlog_in_normal_batches_from_the_worker_thread():
    store = RecordingStore(batch=20)
    updater = ZepGraphMemoryUpdater("g", store=store)
    updater.SEND_INTERVAL = 0
    for i in range(45):
        updater.add_activity(_act("CREATE_POST", content=f"post {i}"))
    updater.start()
    updater.stop()  # waits for everything
    sizes = [len(text.splitlines()) for _, text in store.sends]
    assert sizes == [20, 20, 5]  # never one 45-activity episode
    assert {name for name, _ in store.sends} == {updater._worker_thread.name}  # one sender only
    assert updater.pending() == 0 and updater._total_items_sent == 45


def test_finish_async_then_wait_until_drained(monkeypatch):
    store = RecordingStore(batch=10, delay=0.05)
    monkeypatch.setattr(gm, "get_graph_store", lambda api_key=None: store)
    updater = ZepGraphMemoryManager.create_updater("sim-x", "g")
    updater.SEND_INTERVAL = 0
    for i in range(25):
        updater.add_activity(_act("CREATE_COMMENT", content=f"comment {i}"))

    seen = []
    ZepGraphMemoryManager.finish_updater_async("sim-x")
    assert ZepGraphMemoryManager.get_updater("sim-x") is None  # no new activity accepted
    assert ZepGraphMemoryManager.wait_until_drained("sim-x", timeout=30, on_wait=seen.append, poll=0.01)
    assert sum(len(text.splitlines()) for _, text in store.sends) == 25
    assert seen and all(n > 0 for n in seen)  # progress was reported while sending
    assert ZepGraphMemoryManager.pending("sim-x") == 0
    assert "sim-x" not in ZepGraphMemoryManager._finishing


def test_wait_returns_at_once_when_the_run_had_no_memory():
    t0 = time.time()
    assert ZepGraphMemoryManager.wait_until_drained("never-had-memory", timeout=30)
    assert time.time() - t0 < 1


def test_wait_times_out_while_still_sending(monkeypatch):
    store = RecordingStore(batch=1, delay=0.3)
    monkeypatch.setattr(gm, "get_graph_store", lambda api_key=None: store)
    updater = ZepGraphMemoryManager.create_updater("sim-slow", "g")
    updater.SEND_INTERVAL = 0
    for i in range(10):
        updater.add_activity(_act("CREATE_POST", content=f"p{i}"))
    ZepGraphMemoryManager.finish_updater_async("sim-slow")
    assert ZepGraphMemoryManager.wait_until_drained("sim-slow", timeout=0.2, poll=0.05) is False
    assert ZepGraphMemoryManager.wait_until_drained("sim-slow", timeout=30, poll=0.05) is True


# ---------- the runner starts the drain when the run ends, not when the process exits ----------


class StaysAliveForInterviews:
    """poll() is None for a while after simulation_end, like the wait-for-command OASIS process."""

    def __init__(self, alive_polls):
        self.alive_polls = alive_polls
        self.polls = 0
        self.returncode = 0

    def poll(self):
        self.polls += 1
        return None if self.polls <= self.alive_polls else 0


def test_runner_finishes_memory_while_the_process_is_still_alive(tmp_path, monkeypatch):
    sim_dir = tmp_path / "sim"
    (sim_dir / "reddit").mkdir(parents=True)
    lines = [
        {"round": 1, "agent_id": 1, "agent_name": "Jo", "action_type": "CREATE_POST", "action_args": {"content": "x"}},
        {"event_type": "simulation_end", "total_rounds": 1, "total_actions": 11, "agent_actions": 1},
    ]
    (sim_dir / "reddit" / "actions.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    state = SimulationRunState(simulation_id="sim", runner_status=RunnerStatus.RUNNING)
    process = StaysAliveForInterviews(alive_polls=5)
    monkeypatch.setitem(SimulationRunner._run_states, "sim", state)
    monkeypatch.setitem(SimulationRunner._processes, "sim", process)
    monkeypatch.setitem(SimulationRunner._graph_memory_enabled, "sim", True)
    monkeypatch.setattr("app.services.simulation_runner.time.sleep", lambda _s: None)
    calls = []
    monkeypatch.setattr(
        ZepGraphMemoryManager, "finish_updater_async", classmethod(lambda cls, sid: calls.append((sid, process.polls)))
    )

    SimulationRunner._monitor_simulation("sim")

    assert calls[0] == ("sim", 1)  # right after simulation_end was read, process still alive
    assert state.runner_status == RunnerStatus.COMPLETED
