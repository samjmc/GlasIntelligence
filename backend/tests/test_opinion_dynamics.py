"""Opinion dynamics: per-window stance from each agent's own posts, via a fake Jev."""

import json

import pytest

from app import config as app_config
from app.services import opinion_dynamics as od
from app.services.report_payload import build_report_payload_v1
from app.utils.jev_client import JevAnswer, JevClient
from app.utils.jev_metrics import LEDGER


class FakeJev:
    """Answers each item from ``script(state)``; records every call it was asked."""

    def __init__(self, script):
        self.script = script
        self.items = []
        self.sites = []

    def evaluate_many(self, items, max_workers=None, *, site="unlabelled"):
        self.items.extend(items)
        self.sites.append(site)
        return [self.script(state) for state, _ in items]


def _answer(top, probs):
    return {"position": JevAnswer("choice", top, probs[top], dict(probs))}


OPP = {"opposing": 0.8, "supportive": 0.1, "neutral": 0.05, "ambivalent": 0.05}
SUP = {"opposing": 0.1, "supportive": 0.7, "neutral": 0.1, "ambivalent": 0.1}


def _write(sim_dir, platform, records):
    d = sim_dir / platform
    d.mkdir(parents=True, exist_ok=True)
    (d / "actions.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _post(rnd, name, text, kind="CREATE_POST", agent_id=0):
    key = "quote_content" if kind == "QUOTE_POST" else "content"
    return {"round": rnd, "agent_id": agent_id, "agent_name": name, "action_type": kind, "action_args": {key: text}}


@pytest.fixture(autouse=True)
def _fresh_ledger():
    LEDGER.reset()
    yield
    LEDGER.reset()


@pytest.fixture
def jev_on(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "active")
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset())
    # Until a fake is installed there is NO client, so nothing can reach the real Jev
    # (a JEV_API_KEY in the developer's environment would otherwise build one).
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))

    def _install(script):
        fake = FakeJev(script)
        monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake))
        return fake

    return _install


@pytest.mark.parametrize(
    ("n_rounds", "expected"),
    [(1, 1), (2, 1), (3, 2), (8, 4), (9, 5), (10, 5), (40, 5)],
)
def test_window_size_keeps_two_windows_on_short_runs(n_rounds, expected):
    assert od.window_size(n_rounds) == expected


def test_windows_track_a_moving_agent(tmp_path, jev_on):
    # 10 rounds -> two windows of 5. Alice opposes then supports; Bob opposes throughout.
    _write(
        tmp_path,
        "twitter",
        [
            {"event_type": "round_start", "round": 1},
            _post(1, "Alice", "No to this."),
            _post(2, "Bob", "Against it."),
            {"round": 3, "agent_id": 1, "agent_name": "Bob", "action_type": "LIKE_POST", "action_args": {}},
            _post(7, "Alice", "Actually I now back it."),
            _post(10, "Bob", "Still against.", kind="QUOTE_POST"),
        ],
    )
    _write(tmp_path, "reddit", [_post(8, "Alice", "Changed my mind, yes.", kind="CREATE_COMMENT")])

    fake = jev_on(lambda state: _answer("supportive", SUP) if "back it" in state["posts"] else _answer("opposing", OPP))
    out = od.compute_opinion_dynamics("sim", "the policy", sim_dir=tmp_path)

    assert set(fake.sites) == {"opinion_dynamics"}
    assert len(fake.items) == 4  # 2 agents x 2 windows; LIKE_POST and events add nothing
    alice_w2 = next(s for s, _ in fake.items if s["author"] == "Alice" and "back it" in s["posts"])
    assert alice_w2["posts"] == "Actually I now back it.\n---\nChanged my mind, yes."  # both platforms, round order
    assert any(s["posts"] == "Still against." for s, _ in fake.items)  # QUOTE_POST reads quote_content

    assert out["window_rounds"] == 5
    assert [w["label"] for w in out["windows"]] == ["R1-5", "R6-10"]
    w1, w2 = out["windows"]
    assert w1["n_agents"] == w2["n_agents"] == 2
    assert w1["mean_probabilities"]["opposing"] == 0.8
    assert w2["mean_probabilities"]["opposing"] == pytest.approx(0.45)
    assert w2["mean_probabilities"]["supportive"] == pytest.approx(0.4)
    assert w1["mean_uncertainty"] == pytest.approx(0.2)
    assert {a["agent"]: a["position"] for a in w2["agents"]} == {"Alice": "supportive", "Bob": "opposing"}
    assert out["movers"] == [
        {
            "agent": "Alice",
            "path": [{"window": "R1-5", "position": "opposing"}, {"window": "R6-10", "position": "supportive"}],
        }
    ]
    assert out["agents_judged"] == 2
    assert LEDGER.summary()["sites"]["opinion_dynamics"]["items_total"] == 4


def test_empty_windows_are_skipped_and_posts_capped(tmp_path, jev_on):
    # Rounds 1..12 -> windows R1-5, R6-10, R11-12. Nobody posts in R6-10.
    _write(
        tmp_path,
        "twitter",
        [
            _post(1, "Alice", "x" * 5000),
            {"round": 7, "agent_id": 0, "agent_name": "Alice", "action_type": "LIKE_POST", "action_args": {}},
            _post(12, "Alice", "later"),
        ],
    )
    fake = jev_on(lambda state: _answer("opposing", OPP))
    out = od.compute_opinion_dynamics("sim", "the policy", sim_dir=tmp_path)

    assert [w["label"] for w in out["windows"]] == ["R1-5", "R11-12"]
    assert len(fake.items) == 2
    assert max(len(s["posts"]) for s, _ in fake.items) == od.MAX_POST_CHARS
    assert out["movers"] == []


def test_failed_jev_items_are_dropped_not_guessed(tmp_path, jev_on):
    # Bob's call failed; Carol's answer came back with no probability map.
    _write(tmp_path, "twitter", [_post(1, "Alice", "a"), _post(1, "Bob", "b"), _post(1, "Carol", "c")])
    no_probs = {"position": JevAnswer("choice", "neutral", 0.9, {})}
    scripted = {"Alice": _answer("opposing", OPP), "Bob": None, "Carol": no_probs}
    jev_on(lambda s: scripted[s["author"]])
    out = od.compute_opinion_dynamics("sim", "the policy", sim_dir=tmp_path)

    assert out["jev_failed"] == 2
    w = out["windows"][0]
    assert [a["agent"] for a in w["agents"]] == ["Alice"]
    assert w["mean_probabilities"]["opposing"] == 0.8  # not dragged down by Carol's empty map


def test_jev_down_costs_one_call_not_one_per_agent_window(tmp_path, jev_on):
    _write(tmp_path, "twitter", [_post(r, name, "x") for r in (1, 6) for name in ("Alice", "Bob", "Carol")])
    fake = jev_on(lambda state: None)
    assert od.compute_opinion_dynamics("sim", "the policy", sim_dir=tmp_path) is None
    assert len(fake.items) == 1  # the probe; the other 5 agent-windows are never sent


def test_no_posts_returns_none(tmp_path, jev_on):
    _write(tmp_path, "twitter", [{"round": 1, "agent_id": 0, "agent_name": "A", "action_type": "LIKE_POST"}])
    fake = jev_on(lambda state: _answer("opposing", OPP))
    assert od.compute_opinion_dynamics("sim", "p", sim_dir=tmp_path) is None
    assert od.compute_opinion_dynamics("sim", "p", sim_dir=tmp_path / "missing") is None
    assert fake.items == []


@pytest.mark.parametrize("setup", ["off", "shadow", "disabled_site", "unconfigured"])
def test_not_active_returns_none_without_calling_jev(tmp_path, monkeypatch, jev_on, setup):
    _write(tmp_path, "twitter", [_post(1, "Alice", "a")])
    fake = jev_on(lambda state: _answer("opposing", OPP))
    if setup in ("off", "shadow"):
        monkeypatch.setattr(app_config.Config, "JEV_MODE", setup)
    elif setup == "disabled_site":
        monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"opinion_dynamics"}))
    else:
        monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))

    assert od.compute_opinion_dynamics("sim", "p", sim_dir=tmp_path) is None
    assert fake.items == []


# ---------------------------------------------------------------- report payload


def _payload(simulation_id="sim_1"):
    return build_report_payload_v1(
        simulation_requirement="the policy",
        simulation_id=simulation_id,
        graph_id="g",
        project=None,
        metrics_payload=None,
        positions_payload=None,
        risks_payload=None,
        stakeholder_matrix_payload=None,
        scenarios=[],
        staleness_warnings=[],
        claims=[],
    )


def test_payload_has_no_key_when_jev_off():
    assert app_config.Config.JEV_MODE == "off"  # pinned by conftest
    p = _payload()
    assert "opinion_dynamics" not in p
    assert "opinion_dynamics" not in p["quant"]


def test_payload_adds_key_when_active_and_is_otherwise_unchanged(tmp_path, monkeypatch, jev_on):
    assert JevClient.from_config() is None  # the baseline must not build a real client
    baseline = _payload("sim_x")
    monkeypatch.setattr(app_config.Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))
    _write(tmp_path / "sim_x", "twitter", [_post(1, "Alice", "a"), _post(6, "Alice", "b")])
    jev_on(lambda state: _answer("opposing", OPP))

    p = _payload("sim_x")
    dynamics = p.pop("opinion_dynamics")
    assert [w["label"] for w in dynamics["windows"]] == ["R1-3", "R4-6"]
    assert p == baseline  # additive: every other key byte-for-byte the same


def test_payload_survives_a_crashing_dynamics_step(monkeypatch, jev_on):
    jev_on(lambda state: _answer("opposing", OPP))

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(od, "compute_opinion_dynamics", boom)
    assert "opinion_dynamics" not in _payload()
