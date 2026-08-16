"""Tests for case prediction recording (backend/app/services/case_predictions.py).

Covers the shared interface contract used by the grading script:
case_id == simulation_id, dimension == scenario name, predicted_score is
mc_mean (fallback: mid) on a 0-100 scale.
"""

from unittest.mock import patch

from app.services.case_predictions import (
    predictions_from_payload,
    record_case_meta,
    record_case_predictions,
    record_predictions_for_report,
)
from app.services.report_agent import ReportManager
from app.services.supabase_client import SupabaseDB


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table):
        self._table = table

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return _Resp(self._table.rows)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.inserts = []
        self.updates = []

    def select(self, *_a, **_k):
        return _FakeQuery(self)

    def insert(self, row):
        self.inserts.append(dict(row))
        return _FakeQuery(self)

    def update(self, fields):
        self.updates.append(dict(fields))
        return _FakeQuery(self)


class _FakeClient:
    def __init__(self, rows_by_table=None):
        self.tables = {}
        self._rows_by_table = rows_by_table or {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = _FakeTable(self._rows_by_table.get(name, []))
        return self.tables[name]


class _RaisingClient:
    def table(self, _name):
        raise RuntimeError("supabase unreachable")


_MC_PAYLOAD = {
    "simulation_requirement": "Forecast the outcome of the 2026 trade deal",
    "scenarios": [
        {
            "name": "Trade deal signed",
            "probability_range": {"low": 40, "mid": 55, "high": 70},
            "_meta": {"mc_mean": 58.5},
        },
        {
            "name": "Trade deal collapses",
            "probability_range": {"low": 20, "mid": 30, "high": 45},
        },
        {
            "name": "Status quo continues",
            "probability_range": {"low": 5, "mid": 15, "high": 25},
            "_meta": {"mc_mean": None},
        },
        {"name": "No probability data", "probability_range": {"mid": "n/a"}},
        {"name": "Broken entry"},
        42,
    ],
}


def _mc_rows(simulation_id="sim_x"):
    return predictions_from_payload(_MC_PAYLOAD, simulation_id)


class TestPredictionsFromPayload:
    def test_mc_mean_used_when_present(self):
        rows = _mc_rows()
        assert rows[0]["predicted_score"] == 58.5

    def test_mid_fallback_when_meta_absent(self):
        rows = _mc_rows()
        assert rows[1]["predicted_score"] == 30

    def test_mid_fallback_when_mc_mean_none(self):
        rows = _mc_rows()
        assert rows[2]["predicted_score"] == 15

    def test_malformed_scenarios_skipped(self):
        rows = _mc_rows()
        assert len(rows) == 3
        assert all(r["dimension"] != "No probability data" for r in rows)
        assert all(r["dimension"] != "Broken entry" for r in rows)

    def test_empty_and_missing_scenarios(self):
        assert predictions_from_payload({}, "sim_x") == []
        assert predictions_from_payload({"scenarios": []}, "sim_x") == []
        assert predictions_from_payload({"scenarios": "not-a-list"}, "sim_x") == []

    def test_predicted_score_on_0_100_scale(self):
        for row in _mc_rows():
            assert 0 <= row["predicted_score"] <= 100

    def test_contract_case_id_and_dimension_exactness(self):
        rows = _mc_rows("sim_abc123")
        assert rows[0]["case_id"] == "sim_abc123"
        assert rows[0]["dimension"] == "Trade deal signed"
        assert rows[1]["dimension"] == "Trade deal collapses"

    def test_rationale_contains_low_mid_high(self):
        rows = _mc_rows()
        assert rows[0]["rationale"] == "probability range low/mid/high: 40/55/70 (percent)"


class TestRecordCasePredictions:
    def test_insert_path(self):
        fake = _FakeClient()
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_predictions("sim_x", _MC_PAYLOAD)
        table = fake.tables["case_predictions"]
        assert [r["dimension"] for r in table.inserts] == [
            "Trade deal signed",
            "Trade deal collapses",
            "Status quo continues",
        ]
        assert table.updates == []
        assert table.inserts[0]["case_id"] == "sim_x"

    def test_update_path_when_score_changed(self):
        existing = _mc_rows()
        existing[1]["predicted_score"] = 99
        fake = _FakeClient({"case_predictions": existing})
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_predictions("sim_x", _MC_PAYLOAD)
        table = fake.tables["case_predictions"]
        assert table.inserts == []
        assert table.updates == [
            {"predicted_score": 30, "rationale": existing[1]["rationale"]}
        ]

    def test_update_path_when_rationale_changed(self):
        existing = _mc_rows()
        existing[0]["rationale"] = "stale"
        fake = _FakeClient({"case_predictions": existing})
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_predictions("sim_x", _MC_PAYLOAD)
        table = fake.tables["case_predictions"]
        assert table.inserts == []
        assert len(table.updates) == 1
        assert table.updates[0]["predicted_score"] == 58.5

    def test_unchanged_path_no_writes(self):
        existing = _mc_rows()
        fake = _FakeClient({"case_predictions": existing})
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_predictions("sim_x", _MC_PAYLOAD)
        table = fake.tables["case_predictions"]
        assert table.inserts == []
        assert table.updates == []

    def test_client_raising_does_not_propagate(self):
        with patch.object(SupabaseDB, "client", return_value=_RaisingClient()):
            record_case_predictions("sim_x", _MC_PAYLOAD)

    def test_no_scenarios_no_writes(self):
        fake = _FakeClient()
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_predictions("sim_x", {})
        assert fake.tables == {}


class TestRecordCaseMeta:
    def test_inserts_when_missing(self):
        fake = _FakeClient()
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_meta("sim_x", "Some requirement text")
        meta_table = fake.tables["historical_cases"]
        assert len(meta_table.inserts) == 1
        assert meta_table.inserts[0]["case_id"] == "sim_x"
        assert meta_table.inserts[0]["title"] == "Some requirement text"
        assert meta_table.inserts[0]["start_year"] == meta_table.inserts[0]["end_year"]

    def test_updates_when_row_exists(self):
        fake = _FakeClient({"historical_cases": [{"case_id": "sim_x", "title": "old"}]})
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_meta("sim_x", "New requirement text")
        meta_table = fake.tables["historical_cases"]
        assert meta_table.inserts == []
        assert len(meta_table.updates) == 1
        assert meta_table.updates[0]["title"] == "New requirement text"

    def test_title_truncated_to_200_chars(self):
        fake = _FakeClient()
        long_requirement = "x" * 500
        with patch.object(SupabaseDB, "client", return_value=fake):
            record_case_meta("sim_x", long_requirement)
        assert len(fake.tables["historical_cases"].inserts[0]["title"]) == 200

    def test_client_raising_does_not_propagate(self):
        with patch.object(SupabaseDB, "client", return_value=_RaisingClient()):
            record_case_meta("sim_x", "Some requirement text")


class TestRecordPredictionsForReport:
    def test_payload_missing_logs_and_returns(self):
        with patch.object(ReportManager, "load_payload_v1", return_value=None):
            record_predictions_for_report("sim_x", "report_1")

    def test_payload_present_records_predictions_and_meta(self):
        fake = _FakeClient()
        with patch.object(ReportManager, "load_payload_v1", return_value=_MC_PAYLOAD), patch.object(
            SupabaseDB, "client", return_value=fake
        ):
            record_predictions_for_report("sim_x", "report_1")
        assert len(fake.tables["case_predictions"].inserts) == 3
        meta_table = fake.tables["historical_cases"]
        assert len(meta_table.inserts) == 1
        meta = meta_table.inserts[0]
        assert meta["case_id"] == "sim_x"
        assert meta["title"] == "Forecast the outcome of the 2026 trade deal"
        assert meta["policy_description"] == "Forecast the outcome of the 2026 trade deal"
        assert meta["sources"] == []

    def test_meta_upserts_when_row_exists(self):
        fake = _FakeClient({"historical_cases": [{"case_id": "sim_x", "title": "old"}]})
        with patch.object(ReportManager, "load_payload_v1", return_value=_MC_PAYLOAD), patch.object(
            SupabaseDB, "client", return_value=fake
        ):
            record_predictions_for_report("sim_x", "report_1")
        meta_table = fake.tables["historical_cases"]
        assert meta_table.inserts == []
        assert len(meta_table.updates) == 1
        assert meta_table.updates[0]["title"] == "Forecast the outcome of the 2026 trade deal"
