"""Calibration side of the Jev integration: decomposed forecast features and outcome resolution.

No network: Jev is a fake, Tavily and Supabase are fakes/MagicMocks.
"""

from __future__ import annotations

import importlib.util
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app import config as app_config
from app.services import forecast_features as ff
from app.services import outcome_resolution as orr
from app.services.calibration_grading import compute_calibration_grades
from app.services.case_predictions import record_case_predictions, record_predictions_for_report
from app.services.report_agent import ReportManager
from app.services.supabase_client import SupabaseDB
from app.utils.jev_client import JevAnswer, JevClient
from app.utils.jev_metrics import LEDGER

# ---------------------------------------------------------------------- fakes


class FakeJev:
    """Answers every noul with ``noul_p`` (evaluate) or returns scripted per-item answers (evaluate_many)."""

    model = "fake-jev"

    def __init__(self, *, noul_p=0.8, answers=None, many=None, error=None):
        self.noul_p = noul_p
        self.answers = answers
        self.many = many
        self.error = error
        self.calls = []
        self.items = None
        self.site = None

    def evaluate(self, state, questions, *, site="unlabelled"):
        self.calls.append((state, questions, site))
        if self.error:
            raise self.error
        if self.answers is not None:
            return self.answers
        return {name: JevAnswer("noul", self.noul_p, max(self.noul_p, 1 - self.noul_p)) for name in questions}

    def evaluate_many(self, items, max_workers=None, *, site="unlabelled"):
        self.items = items
        self.site = site
        if self.error:
            raise self.error
        return self.many


def _verdict(option, conf):
    return {"verdict": JevAnswer("choice", option, conf, {option: conf})}


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table, rows):
        self._table = table
        self._rows = rows

    def eq(self, field, value):
        return _FakeQuery(self._table, [r for r in self._rows if r.get(field) == value])

    def execute(self):
        return _Resp(list(self._rows))


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.inserts = []
        self.updates = []

    def select(self, *_a, **_k):
        return _FakeQuery(self, self.rows)

    def insert(self, row):
        self.inserts.append(dict(row))
        return _FakeQuery(self, [dict(row)])

    def update(self, fields):
        self.updates.append(dict(fields))
        return _FakeQuery(self, self.rows)


class _FakeClient:
    def __init__(self, rows_by_table=None):
        self.tables = {}
        self._rows = rows_by_table or {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = _FakeTable(list(self._rows.get(name, [])))
        return self.tables[name]


# ---------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _fresh_ledger():
    LEDGER.reset()
    yield
    LEDGER.reset()


@pytest.fixture
def jev_active(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "active")
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset())


def _payload():
    return {
        "simulation_requirement": "NHS England caps Pharmacy First consultation fees from April 2026",
        "scenarios": [
            {
                "name": "Cap implemented as planned",
                "outcome_narrative": "The cap lands on schedule; closures accelerate in deprived areas.",
                "probability_range": {"low": 40, "mid": 55, "high": 70},
                "_meta": {"mc_mean": 58.5},
            },
            {
                "name": "Cap delayed after review",
                "outcome_narrative": "NHS England announces a review; the cap slips by a year.",
                "probability_range": {"low": 20, "mid": 30, "high": 45},
            },
            {
                "name": "Cap withdrawn",
                "outcome_narrative": "Sustained pressure leads to withdrawal.",
                "probability_range": {"low": 5, "mid": 15, "high": 25},
            },
        ],
        "quant": {
            "positions": {
                "stance_analysis": {
                    "agents_analyzed": 12,
                    "stances": [{"agent_name": "x"} for _ in range(12)],
                    "position_distribution": {"opposing": 0.67, "supportive": 0.17, "neutral": 0.16},
                    "average_intensity": 4.1,
                }
            },
            "metrics": {
                "escalation_analysis": {"overall_trend": "rising", "peak_intensity": 0.8, "intensity_curve": []}
            },
            "risks": {
                "probability_assessment": {"estimates": [{"outcome": "Closures exceed 500", "confidence": "moderate"}]},
                "risk_matrix": {"risks": [{"risk": "Closures accelerate", "severity": "critical", "likelihood": 4}]},
            },
        },
        "grounding": {
            "claims": [
                {"text": "PSNC has threatened collective action.", "classification": "verified", "source_id": "s1"},
                {"text": "Boots says 300 branches are at risk.", "classification": "unverified", "source_id": "s2"},
            ]
        },
        "decision": {"verdict": "proceed with caution", "key_drivers": ["funding"]},
    }


# ====================================================================== features


def test_features_one_request_with_every_signal_and_scenario_noul(jev_active):
    fake = FakeJev(noul_p=0.8)

    rows = ff.compute_forecast_features(_payload(), fake, case_id="sim_1")

    assert len(fake.calls) == 1
    state, questions, site = fake.calls[0]
    assert site == "forecast_features"
    scenario_keys = {
        "evidence_supports_cap_implemented_as_planned",
        "evidence_supports_cap_delayed_after_review",
        "evidence_supports_cap_withdrawn",
    }
    assert set(questions) == set(ff.SIGNALS) | scenario_keys
    assert len(ff.SIGNALS) == 16
    assert all(q["type"] == "noul" for q in questions.values())
    assert "Cap withdrawn" in questions["evidence_supports_cap_withdrawn"]["instructions"]
    assert state["note"] == ff._DATA_NOTE
    assert state["stakeholders"]["position_distribution"]["opposing"] == 0.67
    assert state["escalation"]["overall_trend"] == "rising"
    assert "stances" not in json.dumps(state)  # filtered, not dumped

    assert len(rows) == len(questions)
    assert {r["dimension"] for r in rows} == {f"feature:{name}" for name in questions}
    assert all(r["case_id"] == "sim_1" for r in rows)
    assert all(r["predicted_score"] == 80.0 for r in rows)
    assert rows[0]["rationale"] == "jev noul p=0.800 conf=0.800 model=fake-jev"
    site_stats = LEDGER.summary()["sites"]["forecast_features"]
    assert (site_stats["items_total"], site_stats["items_jev_confident"]) == (len(questions), len(questions))


def test_features_scores_are_0_100_and_low_confidence_counted(jev_active):
    fake = FakeJev(noul_p=0.55)
    rows = ff.compute_forecast_features(_payload(), fake, case_id="sim_1")
    assert rows and all(0 <= r["predicted_score"] <= 100 for r in rows)
    assert all(r["predicted_score"] == 55.0 for r in rows)
    site_stats = LEDGER.summary()["sites"]["forecast_features"]
    assert site_stats["items_jev_confident"] == 0
    assert site_stats["items_jev_low_confidence"] == len(rows)


def test_features_state_stays_under_cap_for_a_huge_payload(jev_active):
    payload = _payload()
    payload["simulation_requirement"] = "x" * 5000
    payload["grounding"]["claims"] = [{"text": "c" * 2000, "classification": "verified"} for _ in range(50)]
    for scenario in payload["scenarios"]:
        scenario["outcome_narrative"] = "n" * 4000

    state = ff.build_evidence_state(payload)

    assert len(json.dumps(state, ensure_ascii=False)) <= ff.STATE_CHAR_CAP
    assert len(state["scenarios"]) == 3  # scenarios survive; claims are trimmed first
    assert len(state["policy"]) == ff._REQUIREMENT_CHARS


def test_features_off_paths_return_empty(monkeypatch, jev_active):
    fake = FakeJev()
    assert ff.compute_forecast_features(_payload(), None, case_id="s") == []

    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"forecast_features"}))
    assert ff.compute_forecast_features(_payload(), fake, case_id="s") == []

    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset())
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "off")
    assert ff.compute_forecast_features(_payload(), fake, case_id="s") == []
    assert fake.calls == []


def test_features_request_failure_returns_empty_and_records(jev_active):
    fake = FakeJev(error=RuntimeError("boom"))
    assert ff.compute_forecast_features(_payload(), fake, case_id="s") == []
    site_stats = LEDGER.summary()["sites"]["forecast_features"]
    assert site_stats["items_jev_failed"] == len(ff.SIGNALS) + 3


def test_features_empty_payload_makes_no_request(jev_active):
    fake = FakeJev()
    assert ff.compute_forecast_features({}, fake, case_id="s") == []
    assert fake.calls == []


def test_features_missing_and_non_noul_answers_skipped(jev_active):
    answers = {
        "regulator_publicly_committed_to_policy": JevAnswer("noul", 0.9, 0.9),
        "opposition_intensity_high": JevAnswer("choice", "yes", 0.9),  # wrong kind
    }
    fake = FakeJev(answers=answers)
    rows = ff.compute_forecast_features(_payload(), fake, case_id="s")
    assert [r["dimension"] for r in rows] == ["feature:regulator_publicly_committed_to_policy"]
    assert rows[0]["predicted_score"] == 90.0
    site_stats = LEDGER.summary()["sites"]["forecast_features"]
    assert site_stats["items_jev_failed"] == len(ff.SIGNALS) + 3 - 1


def test_features_scenario_slug_collisions_get_suffixes(jev_active):
    payload = {"simulation_requirement": "r", "scenarios": [{"name": "Cap holds!"}, {"name": "Cap holds?"}]}
    questions = ff.build_questions(ff.build_evidence_state(payload))
    assert "evidence_supports_cap_holds" in questions and "evidence_supports_cap_holds_2" in questions


# ====================================================================== case_predictions wiring


def test_case_predictions_upserts_feature_rows_alongside_outcomes(monkeypatch, jev_active):
    fake_jev = FakeJev(noul_p=0.7)
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake_jev))
    fake_db = _FakeClient()

    with patch.object(SupabaseDB, "client", return_value=fake_db):
        record_case_predictions("sim_x", _payload())

    inserts = fake_db.tables["case_predictions"].inserts
    outcome_dims = [r["dimension"] for r in inserts if not r["dimension"].startswith("feature:")]
    feature_dims = [r["dimension"] for r in inserts if r["dimension"].startswith("feature:")]
    assert outcome_dims == ["Cap implemented as planned", "Cap delayed after review", "Cap withdrawn"]
    assert len(feature_dims) == len(ff.SIGNALS) + 3
    assert all(r["case_id"] == "sim_x" for r in inserts)


def test_case_predictions_updates_changed_feature_rows(monkeypatch, jev_active):
    fake_jev = FakeJev(noul_p=0.7)
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake_jev))
    existing = [
        {
            "case_id": "sim_x",
            "dimension": "feature:opposition_intensity_high",
            "predicted_score": 10.0,
            "rationale": "old",
        }
    ]
    fake_db = _FakeClient({"case_predictions": existing})

    with patch.object(SupabaseDB, "client", return_value=fake_db):
        record_case_predictions("sim_x", _payload())

    table = fake_db.tables["case_predictions"]
    assert table.updates == [{"predicted_score": 70.0, "rationale": "jev noul p=0.700 conf=0.700 model=fake-jev"}]
    assert "feature:opposition_intensity_high" not in [r["dimension"] for r in table.inserts]


def test_case_predictions_jev_off_writes_only_outcome_rows(monkeypatch):
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))
    fake_db = _FakeClient()

    with (
        patch.object(ReportManager, "load_payload_v1", return_value=_payload()),
        patch.object(SupabaseDB, "client", return_value=fake_db),
    ):
        record_predictions_for_report("sim_x", "report_1")

    inserts = fake_db.tables["case_predictions"].inserts
    assert [r["dimension"] for r in inserts] == [
        "Cap implemented as planned",
        "Cap delayed after review",
        "Cap withdrawn",
    ]
    assert len(fake_db.tables["historical_cases"].inserts) == 1


def test_case_predictions_jev_failure_still_records_outcomes(monkeypatch, jev_active):
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: FakeJev(error=RuntimeError("down"))))
    fake_db = _FakeClient()
    with patch.object(SupabaseDB, "client", return_value=fake_db):
        record_case_predictions("sim_x", _payload())
    assert len(fake_db.tables["case_predictions"].inserts) == 3


def test_grading_ignores_feature_rows_without_outcomes():
    preds = [
        {"case_id": "c1", "dimension": "Cap withdrawn", "predicted_score": 15.0},
        {"case_id": "c1", "dimension": "feature:opposition_intensity_high", "predicted_score": 80.0},
        {"case_id": "c1", "dimension": "feature:evidence_supports_cap_withdrawn", "predicted_score": 30.0},
    ]
    outcomes = [{"case_id": "c1", "dimension": "Cap withdrawn", "actual_score": 0.0}]

    grades = compute_calibration_grades(preds, outcomes)

    assert grades["n_predictions"] == 1
    assert set(grades["errors"]) == {"Cap withdrawn"}
    assert grades["binary"]["n"] == 1


# ====================================================================== outcome resolution


def _articles(n=3):
    return [{"title": f"Story {i}", "url": f"https://news.example/{i}", "content": f"Body {i}"} for i in range(n)]


def test_resolution_occurred_needs_two_confident_supporters(jev_active):
    fake = FakeJev(many=[_verdict("supports", 0.9), _verdict("supports", 0.85), _verdict("says_nothing", 0.95)])

    result = orr.resolve_outcome("c1", "Cap withdrawn", _articles(), fake)

    assert (result.decision, result.score) == ("occurred", 100)
    assert result.best_url == "https://news.example/0"  # the strongest supporter
    assert (result.n_articles, result.support_p, result.contradict_p) == (3, 0.9, 0.0)
    assert fake.site == "outcome_resolution"
    assert len(fake.items) == 3
    state, questions = fake.items[0]
    assert state["outcome"] == "Cap withdrawn" and state["article"]["url"] == "https://news.example/0"
    assert questions["verdict"]["type"] == "choice"
    assert set(questions["verdict"]["criteria"]) == {"supports", "contradicts", "says_nothing"}
    assert "data" in questions["verdict"]["instructions"]
    site_stats = LEDGER.summary()["sites"]["outcome_resolution"]
    assert (site_stats["items_total"], site_stats["items_jev_confident"]) == (3, 3)


def test_resolution_did_not_occur_mirrors(jev_active):
    fake = FakeJev(many=[_verdict("contradicts", 0.95), _verdict("contradicts", 0.8), _verdict("says_nothing", 0.9)])
    result = orr.resolve_outcome("c1", "Cap withdrawn", _articles(), fake)
    assert (result.decision, result.score, result.best_url) == ("did_not_occur", 0, "https://news.example/0")
    assert result.contradict_p == 0.95


def test_resolution_one_confident_contradiction_blocks_occurred(jev_active):
    fake = FakeJev(many=[_verdict("supports", 0.9), _verdict("supports", 0.9), _verdict("contradicts", 0.85)])
    result = orr.resolve_outcome("c1", "d", _articles(), fake)
    assert (result.decision, result.score) == ("unresolved", None)
    assert result.best_url == "https://news.example/0"
    assert "2 supporting, 1 contradicting" in result.notes


def test_resolution_low_confidence_supporters_do_not_count(jev_active):
    fake = FakeJev(many=[_verdict("supports", 0.7), _verdict("supports", 0.7), _verdict("supports", 0.79)])
    result = orr.resolve_outcome("c1", "d", _articles(), fake)
    assert result.decision == "unresolved"
    fake = FakeJev(many=[_verdict("supports", 0.9), _verdict("says_nothing", 0.9), _verdict("says_nothing", 0.9)])
    assert orr.resolve_outcome("c1", "d", _articles(), fake).decision == "unresolved"


def test_resolution_failures_are_unresolved(monkeypatch, jev_active):
    assert orr.resolve_outcome("c1", "d", _articles(), None).decision == "unresolved"
    assert orr.resolve_outcome("c1", "d", [], FakeJev(many=[])).notes == "no articles"

    result = orr.resolve_outcome("c1", "d", _articles(), FakeJev(error=RuntimeError("boom")))
    assert result.decision == "unresolved" and "boom" in result.notes

    result = orr.resolve_outcome("c1", "d", _articles(), FakeJev(many=[None, None, None]))
    assert result.decision == "unresolved" and result.n_articles == 3
    assert LEDGER.summary()["sites"]["outcome_resolution"]["items_jev_failed"] == 3

    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"outcome_resolution"}))
    fake = FakeJev(many=[_verdict("supports", 0.9)] * 3)
    assert orr.resolve_outcome("c1", "d", _articles(), fake).notes == "jev off or site disabled"
    assert fake.items is None


def test_resolution_caps_articles_and_truncates_content(jev_active):
    articles = [{"title": f"t{i}", "url": f"u{i}", "content": "x" * 5000} for i in range(10)]
    fake = FakeJev(many=[_verdict("says_nothing", 0.9)] * 8)
    result = orr.resolve_outcome("c1", "d", articles, fake)
    assert result.n_articles == 8 and len(fake.items) == 8
    assert len(fake.items[0][0]["article"]["text"]) == 2500


def test_search_articles_filters_by_published_date_and_survives_failure():
    tavily = MagicMock()
    tavily.search.return_value = [
        {"title": "old", "url": "u1", "content": "c", "published": "2026-01-15T10:00:00Z"},
        {"title": "new", "url": "u2", "content": "c", "published": "2026-03-02"},
        {"title": "undated", "url": "u3", "content": "c"},
        {"title": "", "url": "u4", "content": ""},  # nothing to classify
        "not-a-dict",
    ]

    kept = orr.search_articles("Cap withdrawn Pharmacy First", "2026-02-01T00:00:00", tavily)

    assert [a["url"] for a in kept] == ["u2", "u3"]
    tavily.search.assert_called_once_with("Cap withdrawn Pharmacy First", max_results=8)
    assert [a["url"] for a in orr.search_articles("q", None, tavily)] == ["u1", "u2", "u3"]

    tavily.search.side_effect = RuntimeError("tavily down")
    assert orr.search_articles("q", None, tavily) == []


def test_build_query_adds_title_once_and_caps_length():
    assert orr.build_query("Cap withdrawn", "Pharmacy First fee cap") == "Cap withdrawn Pharmacy First fee cap"
    assert orr.build_query("Cap withdrawn", None) == "Cap withdrawn"
    assert orr.build_query("Pharmacy First cap withdrawn", "Pharmacy First") == "Pharmacy First cap withdrawn"
    assert len(orr.build_query("x" * 500, "y" * 500)) == orr.QUERY_CHARS


# ====================================================================== CLI: resolve


def _load_cli():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "calibration_ledger.py")
    spec = importlib.util.spec_from_file_location("calibration_ledger_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cli_rows():
    return {
        "case_predictions": [
            {
                "case_id": "c1",
                "dimension": "Cap withdrawn",
                "predicted_score": 15.0,
                "created_at": "2026-02-01T00:00:00",
            },
            {"case_id": "c1", "dimension": "Cap delayed", "predicted_score": 30.0, "created_at": "2026-02-01T00:00:00"},
            {"case_id": "c1", "dimension": "feature:opposition_intensity_high", "predicted_score": 80.0},
            {"case_id": "c2", "dimension": "Already resolved", "predicted_score": 50.0},
        ],
        "case_outcomes": [{"case_id": "c2", "dimension": "Already resolved", "actual_score": 100.0}],
        "historical_cases": [{"case_id": "c1", "title": "Pharmacy First fee cap"}],
    }


def test_cli_resolve_exits_2_without_tavily_or_jev(monkeypatch, capsys):
    # Patch the CLI's OWN Config: test_config_tavily.py evicts app.config from sys.modules, so a
    # freshly loaded CLI can hold a different Config object from the one imported at the top here.
    cli = _load_cli()
    monkeypatch.setattr(cli.Config, "TAVILY_API_KEY", "")
    assert cli.main(["resolve"]) == 2
    assert "TAVILY_API_KEY" in capsys.readouterr().err

    monkeypatch.setattr(cli.Config, "TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))
    assert cli.main(["resolve"]) == 2
    assert "Jev" in capsys.readouterr().err


def test_cli_resolve_dry_run_prints_and_writes_nothing(monkeypatch, capsys, jev_active):
    cli = _load_cli()
    monkeypatch.setattr(cli.Config, "TAVILY_API_KEY", "tvly-test")
    fake_jev = FakeJev(many=[_verdict("supports", 0.9), _verdict("supports", 0.9)])
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake_jev))
    tavily = MagicMock()
    tavily.search.return_value = _articles(2)
    monkeypatch.setattr(cli, "TavilyClient", MagicMock(return_value=tavily))
    fake_db = _FakeClient(_cli_rows())

    with patch.object(SupabaseDB, "client", return_value=fake_db):
        rc = cli.main(["resolve", "--dry-run"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "Cap withdrawn" in out and "Cap delayed" in out and "occurred" in out and "https://news.example/" in out
    assert "feature:" not in out and "Already resolved" not in out
    assert "dry run" in out
    assert fake_db.tables["case_outcomes"].inserts == [] and fake_db.tables["case_outcomes"].updates == []
    # the query carries the dimension AND the case title; after_date is the prediction's created_at
    assert tavily.search.call_args_list[0].args[0] == "Cap withdrawn Pharmacy First fee cap"


def test_cli_resolve_writes_confident_decisions_only(monkeypatch, capsys, jev_active):
    cli = _load_cli()
    monkeypatch.setattr(cli.Config, "TAVILY_API_KEY", "tvly-test")
    scripted = iter(
        [
            [_verdict("supports", 0.9), _verdict("supports", 0.9)],  # Cap withdrawn -> occurred
            [_verdict("supports", 0.9), _verdict("contradicts", 0.9)],  # Cap delayed -> unresolved
        ]
    )
    fake_jev = FakeJev()
    fake_jev.evaluate_many = lambda items, max_workers=None, *, site="unlabelled": next(scripted)
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake_jev))
    tavily = MagicMock()
    tavily.search.return_value = _articles(2)
    monkeypatch.setattr(cli, "TavilyClient", MagicMock(return_value=tavily))
    fake_db = _FakeClient(_cli_rows())

    with patch.object(SupabaseDB, "client", return_value=fake_db):
        rc = cli.main(["resolve", "--case-id", "c1"])

    assert rc == 0
    assert fake_db.tables["case_outcomes"].inserts == [
        {"case_id": "c1", "dimension": "Cap withdrawn", "actual_score": 100.0}
    ]
    assert fake_db.tables["case_outcomes"].updates == []
    assert "2 pending, 1 written" in capsys.readouterr().out


def test_cli_record_outcome_still_upserts(monkeypatch, capsys):
    cli = _load_cli()
    fake_db = _FakeClient({"case_outcomes": [{"case_id": "c1", "dimension": "d", "actual_score": 0.0}]})
    with patch.object(SupabaseDB, "client", return_value=fake_db):
        assert cli.main(["record-outcome", "c1", "d", "100"]) == 0
        assert cli.main(["record-outcome", "c9", "d", "0"]) == 0
    table = fake_db.tables["case_outcomes"]
    assert table.updates == [{"actual_score": 100.0}]
    assert table.inserts == [{"case_id": "c9", "dimension": "d", "actual_score": 0.0}]
    out = capsys.readouterr().out
    assert "Updated case_outcome" in out and "Inserted case_outcome" in out
