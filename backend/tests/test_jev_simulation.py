"""Jev gates in the simulation runtime: activation, validity, effect targets, graph actor filter.

Each gate must (a) be byte-identical to today's behaviour when Jev is off, (b) degrade
to today's behaviour on any Jev failure, and (c) record to the LEDGER. No network:
Jev is a fake; the rng is seeded.
"""

from __future__ import annotations

import json
import os
import random
import sys
from unittest.mock import MagicMock

import pytest

from app import config as app_config
from app.services import jev_simulation_gates as gates
from app.services.simulation_effects import EffectEngine
from app.services.simulation_runner import SimulationRunner, SimulationRunState
from app.services.zep_entity_reader import ZepEntityReader
from app.utils.jev_client import JevAnswer, JevClient
from app.utils.jev_metrics import LEDGER

_LIB = os.path.join(os.path.dirname(__file__), "..", "scripts", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import time_utils  # noqa: E402  (scripts/lib module, imported the way the OASIS subprocess does)


def noul(p: float) -> JevAnswer:
    return JevAnswer("noul", p, max(p, 1 - p))


class FakeJev:
    """Scripted Jev: a fixed answer list, or a per-item function; records every call."""

    def __init__(self, answers=None, *, per_item=None, raise_exc=None):
        self.answers = answers
        self.per_item = per_item
        self.raise_exc = raise_exc
        self.calls: list[tuple[list, str]] = []

    def evaluate_many(self, items, max_workers=None, *, site="unlabelled"):
        self.calls.append((list(items), site))
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.per_item is not None:
            return [self.per_item(state, questions) for state, questions in items]
        assert len(items) == len(self.answers), "test script must cover every item"
        return list(self.answers)

    @property
    def sites(self):
        return {site for _, site in self.calls}


@pytest.fixture(autouse=True)
def _fresh_ledger():
    LEDGER.reset()
    yield
    LEDGER.reset()


@pytest.fixture
def jev(monkeypatch):
    """Install a FakeJev under ``JevClient.from_config`` in the given mode (default active)."""
    monkeypatch.setattr(app_config.Config, "JEV_MIN_CONFIDENCE", 0.6)
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset())

    def _install(fake: FakeJev, mode: str = "active") -> FakeJev:
        monkeypatch.setattr(app_config.Config, "JEV_MODE", mode)
        monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake))
        return fake

    return _install


@pytest.fixture
def jev_off(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "off")
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))


# ====================================================================== activation


class _Env:
    class _Graph:
        @staticmethod
        def get_agent(agent_id):
            return f"agent-{agent_id}"

    agent_graph = _Graph()


def _agents():
    return [
        {
            "agent_id": 0,
            "entity_name": "NHS England",
            "entity_type": "GovernmentBody",
            "stance": "supportive",
            "activity_level": 0.6,
        },
        {
            "agent_id": 1,
            "entity_name": "Jane Doe",
            "entity_type": "Pharmacist",
            "stance": "opposing",
            "activity_level": 0.6,
        },
        {
            "agent_id": 2,
            "entity_name": "The Guardian",
            "entity_type": "MediaOutlet",
            "stance": "neutral",
            "activity_level": 0.6,
        },
    ]


def _config(agents=None, unit="day", per_round=(1, 3)):
    return {
        "agent_configs": agents or _agents(),
        "time_config": {
            "agents_per_round_min": per_round[0],
            "agents_per_round_max": per_round[1],
            "time_scale": {"unit": unit, "per_round": 1},
            "phases": [],
        },
    }


FEED = [{"agent_name": "Jane Doe", "action_type": "CREATE_POST", "content": "NHS England must drop the caps."}]


def _legacy_select(config, current_hour, round_num, rng) -> list[int]:
    """Today's algorithm, copied verbatim (ids only), as the byte-identical reference."""
    time_config = config.get("time_config", {})
    agent_configs = config.get("agent_configs", [])
    base_min = time_config.get("agents_per_round_min", 5)
    base_max = time_config.get("agents_per_round_max", 20)
    unit = time_config.get("time_scale", {}).get("unit", "hour")
    if unit != "hour":
        candidates = [cfg.get("agent_id", 0) for cfg in agent_configs if rng.random() < cfg.get("activity_level", 0.5)]
        target_count = int(rng.uniform(base_min, base_max) * 1.0)
    else:
        multiplier = 1.5 if current_hour in [9, 10, 11, 14, 15, 20, 21, 22] else 1.0
        target_count = int(rng.uniform(base_min, base_max) * multiplier)
        candidates = []
        for cfg in agent_configs:
            if current_hour not in cfg.get("active_hours", list(range(8, 23))):
                continue
            if rng.random() < cfg.get("activity_level", 0.5):
                candidates.append(cfg.get("agent_id", 0))
    return rng.sample(candidates, min(target_count, len(candidates))) if candidates else []


def _ids(active):
    return [aid for aid, _ in active]


@pytest.mark.parametrize("unit", ["day", "hour"])
def test_activation_off_is_byte_identical_to_today(jev_off, unit):
    config = _config(unit=unit)
    for seed in range(25):
        got = _ids(
            time_utils.get_active_agents_for_round(_Env(), config, 10, 3, recent_feed=FEED, rng=random.Random(seed))
        )
        assert got == _legacy_select(config, 10, 3, random.Random(seed))


def test_activation_round_zero_without_feed_never_asks_jev(jev):
    fake = jev(FakeJev(per_item=lambda s, q: {"addressed": noul(1.0), "interest_at_stake": noul(1.0)}))
    config = _config()
    got = _ids(time_utils.get_active_agents_for_round(_Env(), config, 10, 0, recent_feed=[], rng=random.Random(1)))
    assert got == _legacy_select(config, 10, 0, random.Random(1))
    assert fake.calls == []


def _rates(config, rng_seed_count=1500, mode_hook=None):
    counts = {ac["agent_id"]: 0 for ac in config["agent_configs"]}
    for seed in range(rng_seed_count):
        for aid in _ids(
            time_utils.get_active_agents_for_round(_Env(), config, 10, 1, recent_feed=FEED, rng=random.Random(seed))
        ):
            counts[aid] += 1
    return {aid: n / rng_seed_count for aid, n in counts.items()}


def _signals_by_name(table):
    return lambda state, questions: {
        "addressed": noul(table[state["actor"]["name"]][0]),
        "interest_at_stake": noul(table[state["actor"]["name"]][1]),
    }


def test_activation_active_extremes(jev):
    """Both signals saturated at activity 1.0 -> weight 0.95; both zero at activity 0.3 -> floor 0.05."""
    agents = [
        {"agent_id": 0, "entity_name": "Hot", "entity_type": "Pharmacist", "stance": "opposing", "activity_level": 1.0},
        {"agent_id": 1, "entity_name": "Cold", "entity_type": "Pharmacist", "stance": "neutral", "activity_level": 0.3},
    ]
    fake = jev(FakeJev(per_item=_signals_by_name({"Hot": (1.0, 1.0), "Cold": (0.0, 0.0)})))
    rates = _rates(_config(agents, per_round=(10, 10)))
    assert rates[0] > 0.9, rates
    assert rates[1] < 0.09, rates  # baseline would have been 0.30
    assert gates.activation_weight(1.0, 1.0, 1.0) == gates.ACTIVATION_P_CEILING
    assert gates.activation_weight(0.0, 0.0, 0.3) == gates.ACTIVATION_P_FLOOR
    state, questions = fake.calls[0][0][0]
    assert set(questions) == {"addressed", "interest_at_stake"}
    assert all(q["type"] == "noul" for q in questions.values())
    assert state["actor"] == {"name": "Hot", "entity_type": "Pharmacist", "stance": "opposing"}
    assert state["recent_feed"] == FEED
    assert fake.sites == {"activation"}


def test_activation_discriminates_named_actor_from_uninvolved_one(jev):
    """Same activity_level: the actor the feed addresses activates far more often than one it ignores."""
    agents = [
        {
            "agent_id": 0,
            "entity_name": "NHS England",
            "entity_type": "GovernmentBody",
            "stance": "supportive",
            "activity_level": 0.6,
        },
        {
            "agent_id": 1,
            "entity_name": "Bystander",
            "entity_type": "Person",
            "stance": "neutral",
            "activity_level": 0.6,
        },
    ]
    jev(FakeJev(per_item=_signals_by_name({"NHS England": (0.95, 0.9), "Bystander": (0.02, 0.05)})))
    rates = _rates(_config(agents, per_round=(10, 10)))
    assert rates[0] > 0.5, rates  # weight ~ (0.15 + 0.4275 + 0.36) * 0.6 = 0.56
    assert rates[1] < 0.15, rates  # weight ~ (0.15 + 0.009 + 0.02) * 0.6 = 0.11
    assert rates[0] > 3 * rates[1]


def test_activation_shadow_keeps_baseline_and_records_agreement(jev):
    fake = jev(
        FakeJev(
            per_item=_signals_by_name({"NHS England": (1.0, 1.0), "Jane Doe": (0.0, 0.0), "The Guardian": (0.5, 0.5)})
        ),
        mode="shadow",
    )
    config = _config()
    for seed in range(20):
        got = _ids(
            time_utils.get_active_agents_for_round(_Env(), config, 10, 2, recent_feed=FEED, rng=random.Random(seed))
        )
        assert got == _legacy_select(config, 10, 2, random.Random(seed))
    assert len(fake.calls) == 20
    site = LEDGER.summary()["sites"]["activation"]
    assert site["items_total"] == 60 and site["items_jev_confident"] == 60
    assert site["shadow_compared"] == 60
    assert 0 < site["shadow_agreed"] < 60  # p>=0.5 vs the Bernoulli outcome: sometimes agrees, sometimes not


def test_activation_jev_exception_falls_back_to_baseline(jev):
    jev(FakeJev(raise_exc=RuntimeError("boom")))
    config = _config()
    for seed in range(10):
        got = _ids(
            time_utils.get_active_agents_for_round(_Env(), config, 10, 1, recent_feed=FEED, rng=random.Random(seed))
        )
        assert got == _legacy_select(config, 10, 1, random.Random(seed))


def test_activation_unscored_agent_uses_baseline_and_hour_mode_only_asks_about_eligible(jev):
    agents = _agents()
    agents[1]["active_hours"] = [22]  # not active at hour 10
    fake = jev(
        FakeJev(
            per_item=lambda s, q: (
                None
                if s["actor"]["name"] == "The Guardian"
                else {"addressed": noul(1.0), "interest_at_stake": noul(1.0)}
            )
        )
    )
    time_utils.get_active_agents_for_round(
        _Env(), _config(agents, unit="hour"), 10, 1, recent_feed=FEED, rng=random.Random(3)
    )
    asked = [state["actor"]["name"] for state, _ in fake.calls[0][0]]
    assert asked == ["NHS England", "The Guardian"]
    site = LEDGER.summary()["sites"]["activation"]
    assert (site["items_total"], site["items_jev_confident"], site["items_jev_failed"]) == (2, 1, 1)


def test_recent_feed_keeps_last_n_content_actions_and_caps_text():
    feed = gates.RecentFeed(window=2)
    feed.push_actions(
        [
            {"agent_name": "a", "action_type": "LIKE_POST", "action_args": {"post_id": 1}},
            {"agent_name": "b", "action_type": "CREATE_POST", "action_args": {"content": "x" * 500}},
            {"agent_name": "c", "action_type": "QUOTE_POST", "action_args": {"quote_content": "q", "content": "c"}},
            {"agent_name": "d", "action_type": "CREATE_COMMENT", "action_args": {"content": "d"}},
        ]
    )
    items = feed.items()
    assert [i["agent_name"] for i in items] == ["c", "d"]
    assert items[0]["content"] == "q"
    feed2 = gates.RecentFeed()
    feed2.push_actions([{"agent_name": "b", "action_type": "CREATE_POST", "action_args": {"content": "x" * 500}}])
    assert len(feed2.items()[0]["content"]) == gates.FEED_TEXT_MAX_CHARS


# ====================================================================== validity


def _post(agent_id, text, action_type="CREATE_POST", **extra):
    args = {"content": text, **extra}
    return {
        "agent_id": agent_id,
        "agent_name": _agents()[agent_id]["entity_name"],
        "action_type": action_type,
        "action_args": args,
    }


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_validity_writes_jsonl_and_scores_quotes_for_new_content(jev, tmp_path):
    fake = jev(
        FakeJev(
            per_item=lambda s, q: {
                "on_persona": noul(0.9),
                **({"adds_new_content": noul(0.2)} if "adds_new_content" in q else {}),
            }
        )
    )
    monitor = gates.ValidityMonitor(str(tmp_path), _agents())
    actions = [
        _post(0, "We back Pharmacy First."),
        {"agent_id": 1, "agent_name": "Jane Doe", "action_type": "LIKE_POST", "action_args": {"post_id": 1}},
        _post(2, "", action_type="QUOTE_POST", quote_content="Nothing new here", original_content="Original text"),
    ]
    assert monitor.score_round(1, actions) == 2
    rows = _read_jsonl(monitor.jsonl_path)
    assert [r["action_type"] for r in rows] == ["CREATE_POST", "QUOTE_POST"]
    assert rows[0] == {
        "round": 1,
        "agent_id": 0,
        "agent_name": "NHS England",
        "action_type": "CREATE_POST",
        "on_persona_p": 0.9,
        "adds_new_content_p": None,
    }
    assert rows[1]["adds_new_content_p"] == 0.2
    quote_state, quote_q = fake.calls[0][0][1]
    assert set(quote_q) == {"on_persona", "adds_new_content"}
    assert quote_state["quote_content"] == "Nothing new here" and quote_state["original_content"] == "Original text"
    assert quote_state["actor"]["name"] == "The Guardian"
    assert set(fake.calls[0][0][0][1]) == {"on_persona"}
    assert not os.path.exists(monitor.alert_path)
    site = LEDGER.summary()["sites"]["validity"]
    assert (site["items_total"], site["items_jev_confident"]) == (2, 2)


def test_validity_alert_written_only_when_off_persona_share_crosses_threshold(jev, tmp_path):
    jev(FakeJev(per_item=lambda s, q: {"on_persona": noul(0.1)}))
    low = gates.ValidityMonitor(str(tmp_path / "low"), _agents())
    for rnd in range(1, 4):
        low.score_round(rnd, [_post(0, f"p{rnd}-{i}") for i in range(4)])  # 12 scored, all off persona
    assert os.path.exists(low.alert_path)
    with open(low.alert_path, encoding="utf-8") as f:
        alert = json.load(f)
    assert alert["validity_alert"] is True and alert["round"] == 3 and "100%" in alert["reason"]

    jev(FakeJev(per_item=lambda s, q: {"on_persona": noul(0.8)}))
    high = gates.ValidityMonitor(str(tmp_path / "high"), _agents())
    for rnd in range(1, 4):
        high.score_round(rnd, [_post(0, f"p{rnd}-{i}") for i in range(4)])
    assert not os.path.exists(high.alert_path)
    assert len(_read_jsonl(high.jsonl_path)) == 12


def test_validity_no_alert_before_min_sample(jev, tmp_path):
    jev(FakeJev(per_item=lambda s, q: {"on_persona": noul(0.1)}))
    monitor = gates.ValidityMonitor(str(tmp_path), _agents())
    monitor.score_round(1, [_post(0, f"p{i}") for i in range(gates.VALIDITY_MIN_SCORED - 1)])
    assert not os.path.exists(monitor.alert_path)


def test_validity_off_writes_nothing(jev_off, tmp_path):
    monitor = gates.ValidityMonitor(str(tmp_path), _agents())
    assert not monitor.enabled
    assert monitor.score_round(1, [_post(0, "hello")]) == 0
    assert not os.path.exists(monitor.jsonl_path) and not os.path.exists(monitor.alert_path)


def test_validity_disabled_site_and_jev_exception_never_raise(jev, monkeypatch, tmp_path):
    jev(FakeJev(raise_exc=RuntimeError("boom")))
    monitor = gates.ValidityMonitor(str(tmp_path), _agents())
    assert monitor.enabled
    assert monitor.score_round(1, [_post(0, "hello")]) == 0
    assert not os.path.exists(monitor.jsonl_path)
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"validity"}))
    assert not gates.ValidityMonitor(str(tmp_path), _agents()).enabled


def test_runner_surfaces_validity_alert_on_run_state(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sim_dir = tmp_path / "sim-1"
    sim_dir.mkdir()
    state = SimulationRunState(simulation_id="sim-1")
    SimulationRunner._apply_validity_alert(state, str(sim_dir))
    assert state.validity_alert is None and state.to_dict()["validity_alert"] is None

    (sim_dir / gates.VALIDITY_ALERT_FILE).write_text(
        json.dumps({"validity_alert": True, "reason": "60% off persona", "round": 7}), encoding="utf-8"
    )
    SimulationRunner._apply_validity_alert(state, str(sim_dir))
    assert state.validity_alert == "60% off persona (round 7)"
    SimulationRunner._save_run_state(state)
    SimulationRunner._run_states.pop("sim-1", None)
    reloaded = SimulationRunner._load_run_state("sim-1")
    assert reloaded is not None and reloaded.validity_alert == "60% off persona (round 7)"
    assert reloaded.runner_status == state.runner_status  # additive: nothing else changed


# ====================================================================== effect targets


def _engine(tmp_path, agents=None):
    agents = agents or _agents()
    return EffectEngine({"agent_configs": agents}, {ac["agent_id"]: ac["entity_name"] for ac in agents}, str(tmp_path))


def test_effect_targets_confident_pick_returns_mapped_id(jev, tmp_path):
    fake = jev(FakeJev([{"target": JevAnswer("choice", "Jane Doe", 0.9)}]))
    engine = _engine(tmp_path)
    assert engine.resolve_target("Sanction the pharmacist who spoke to The Guardian") == 1  # heuristic says 2
    state, questions = fake.calls[0][0][0]
    assert state == {"action_description": "Sanction the pharmacist who spoke to The Guardian"}
    assert questions["target"]["type"] == "choice"
    assert set(questions["target"]["criteria"]) == {"NHS England", "Jane Doe", "The Guardian", "none_of_these"}
    assert questions["target"]["criteria"]["Jane Doe"] == "Pharmacist"
    assert fake.sites == {"effect_targets"}
    site = LEDGER.summary()["sites"]["effect_targets"]
    assert (site["items_total"], site["items_jev_confident"], site["items_llm"]) == (1, 1, 0)


def test_effect_targets_confident_none_of_these_returns_none_even_when_heuristic_matches(jev, tmp_path):
    jev(FakeJev([{"target": JevAnswer("choice", "none_of_these", 0.95)}]))
    engine = _engine(tmp_path)
    assert engine._resolve_target_heuristic("Praise the guardian angels of pharmacy") == 2
    assert engine.resolve_target("Praise the guardian angels of pharmacy") is None


def test_effect_targets_unsure_or_failed_uses_heuristic(jev, tmp_path):
    jev(FakeJev([{"target": JevAnswer("choice", "Jane Doe", 0.4)}]))
    assert _engine(tmp_path).resolve_target("Write to NHS England") == 0
    jev(FakeJev([None]))
    assert _engine(tmp_path).resolve_target("Write to NHS England") == 0
    jev(FakeJev([{"target": JevAnswer("choice", "Nobody Known", 0.99)}]))
    assert _engine(tmp_path).resolve_target("Write to NHS England") == 0
    site = LEDGER.summary()["sites"]["effect_targets"]
    assert (site["items_jev_low_confidence"], site["items_jev_failed"], site["items_llm"]) == (2, 1, 3)


def test_effect_targets_large_roster_skips_jev(jev, tmp_path):
    fake = jev(FakeJev([{"target": JevAnswer("choice", "Entity 7", 0.99)}]))
    agents = [{"agent_id": i, "entity_name": f"Entity {i}", "entity_type": "Person"} for i in range(300)]
    engine = _engine(tmp_path, agents)
    assert engine._target_question is None
    assert engine.resolve_target("Contact Entity 12 today") == 12
    assert fake.calls == []


def test_effect_targets_off_and_empty_match_heuristic(jev_off, tmp_path):
    engine = _engine(tmp_path)
    assert engine.resolve_target("") is None
    assert engine.resolve_target("Ask the guardian") == 2
    assert engine.resolve_target("nobody here") is None
    assert "effect_targets" in LEDGER.summary()["sites"]


def test_effect_targets_shadow_records_agreement_and_keeps_heuristic(jev, tmp_path):
    jev(FakeJev([{"target": JevAnswer("choice", "Jane Doe", 0.9)}]), mode="shadow")
    engine = _engine(tmp_path)
    assert engine.resolve_target("Sanction the pharmacist who spoke to The Guardian") == 2  # heuristic wins
    jev(FakeJev([{"target": JevAnswer("choice", "none_of_these", 0.9)}]), mode="shadow")
    engine = _engine(tmp_path)
    assert engine.resolve_target("nobody here") is None  # both say no target -> agrees
    site = LEDGER.summary()["sites"]["effect_targets"]
    assert (site["shadow_compared"], site["shadow_agreed"], site["items_llm"]) == (2, 1, 2)


# ====================================================================== graph actor filter


def _nodes():
    rows = [
        ("u1", "NHS England", ["Entity", "GovernmentBody"], "Commissioner"),
        ("u2", "Pharmacy First", ["Entity", "Policy"], "A scheme"),
        ("u3", "£645m", ["Entity", "Amount"], "Funding figure"),
        ("u4", "Untyped", ["Entity"], "label-filtered before Jev"),
        ("u5", "Maybe Topic", ["Entity", "Topic"], "unsure"),
    ]
    return [
        {"uuid": uuid, "name": name, "labels": labels, "summary": summary, "attributes": {}}
        for uuid, name, labels, summary in rows
    ]


def _reader(monkeypatch):
    monkeypatch.setattr("app.services.zep_entity_reader.Zep", MagicMock())
    reader = ZepEntityReader(api_key="k")
    monkeypatch.setattr(reader, "get_all_nodes", lambda graph_id: _nodes())
    monkeypatch.setattr(reader, "get_all_edges", lambda graph_id: [])
    return reader


def test_graph_filter_drops_confident_non_actors_and_noise_only(jev, monkeypatch):
    fake = jev(
        FakeJev(
            [
                {"kind": JevAnswer("choice", "actor", 0.9)},
                {"kind": JevAnswer("choice", "non_actor_concept", 0.9)},
                {"kind": JevAnswer("choice", "quantitative_noise", 0.95)},
                {"kind": JevAnswer("choice", "non_actor_concept", 0.4)},  # unsure -> kept
            ]
        )
    )
    result = _reader(monkeypatch).filter_defined_entities("g", enrich_with_edges=False)
    assert [e.name for e in result.entities] == ["NHS England", "Maybe Topic"]
    assert result.jev_dropped == 2 and result.filtered_count == 2 and result.total_count == 5
    assert result.to_dict()["jev_dropped"] == 2
    states = [state for state, _ in fake.calls[0][0]]
    assert states[0] == {"name": "NHS England", "labels": ["Entity", "GovernmentBody"], "summary": "Commissioner"}
    assert len(states) == 4  # the label-only node never reaches Jev
    assert set(fake.calls[0][0][0][1]["kind"]["criteria"]) == {"actor", "non_actor_concept", "quantitative_noise"}
    assert fake.sites == {"graph_actor_filter"}
    site = LEDGER.summary()["sites"]["graph_actor_filter"]
    assert (site["items_total"], site["items_jev_confident"], site["items_jev_low_confidence"]) == (4, 3, 1)


def test_graph_filter_off_keeps_every_labelled_node(jev_off, monkeypatch):
    result = _reader(monkeypatch).filter_defined_entities("g", enrich_with_edges=False)
    assert [e.name for e in result.entities] == ["NHS England", "Pharmacy First", "£645m", "Maybe Topic"]
    assert result.jev_dropped == 0 and result.filtered_count == 4
    assert "graph_actor_filter" not in LEDGER.summary()["sites"]


def test_graph_filter_shadow_measures_but_drops_nothing(jev, monkeypatch):
    jev(FakeJev([{"kind": JevAnswer("choice", "quantitative_noise", 0.99)}] * 4), mode="shadow")
    result = _reader(monkeypatch).filter_defined_entities("g", enrich_with_edges=False)
    assert result.filtered_count == 4 and result.jev_dropped == 0
    assert LEDGER.summary()["sites"]["graph_actor_filter"]["items_jev_confident"] == 4


def test_graph_filter_jev_failure_keeps_every_node(jev, monkeypatch):
    jev(FakeJev(raise_exc=RuntimeError("boom")))
    result = _reader(monkeypatch).filter_defined_entities("g", enrich_with_edges=False)
    assert result.filtered_count == 4 and result.jev_dropped == 0
