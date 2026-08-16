"""
Case prediction recording for the calibration pipeline.

Every completed report writes its scenario probability estimates into the
live ``case_predictions`` table so grading scripts can evaluate forecast
calibration against historical outcomes. Failures are swallowed and logged —
prediction recording must never break or delay the report flow.
"""

from datetime import datetime
from typing import Any, cast

from ..utils.logger import get_logger
from .report_agent import ReportManager
from .supabase_client import SupabaseDB

logger = get_logger("glas.case_predictions")


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fmt(value: Any) -> str:
    if not _is_numeric(value):
        return "-"
    return str(int(value)) if float(value).is_integer() else str(value)


def predictions_from_payload(payload: dict, simulation_id: str) -> list[dict]:
    """Extract case_predictions rows from a report payload v1 (pure function)."""
    rows: list[dict] = []
    scenarios = payload.get("scenarios") or []
    if not isinstance(scenarios, list):
        return rows
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        probability_range = scenario.get("probability_range")
        if not isinstance(probability_range, dict):
            continue
        mid = probability_range.get("mid")
        if not _is_numeric(mid):
            continue
        name = scenario.get("name")
        if name is None:
            continue
        meta = scenario.get("_meta") or {}
        mc_mean = meta.get("mc_mean") if isinstance(meta, dict) else None
        predicted_score = mc_mean if _is_numeric(mc_mean) else mid
        low = probability_range.get("low")
        high = probability_range.get("high")
        rows.append(
            {
                "case_id": simulation_id,
                "dimension": name,
                "predicted_score": predicted_score,
                "rationale": (
                    f"probability range low/mid/high: {_fmt(low)}/{_fmt(mid)}/{_fmt(high)} (percent)"
                ),
            }
        )
    return rows


def record_case_predictions(simulation_id: str, payload: dict) -> None:
    """Insert missing and update changed (case_id, dimension) prediction rows."""
    predictions = predictions_from_payload(payload, simulation_id)
    if not predictions:
        return
    try:
        client = SupabaseDB.client()
        resp = client.table("case_predictions").select("*").eq("case_id", simulation_id).execute()
        existing_rows = cast(list[dict[str, Any]], resp.data or [])
        existing = {row.get("dimension"): row for row in existing_rows}
        table = client.table("case_predictions")
        for prediction in predictions:
            dimension = prediction["dimension"]
            row = existing.get(dimension)
            if row is None:
                table.insert(prediction).execute()
            elif (
                row.get("predicted_score") != prediction["predicted_score"]
                or row.get("rationale") != prediction["rationale"]
            ):
                table.update(
                    {
                        "predicted_score": prediction["predicted_score"],
                        "rationale": prediction["rationale"],
                    }
                ).eq("case_id", simulation_id).eq("dimension", dimension).execute()
    except Exception as e:
        logger.warning("Failed to record case predictions for case_id=%s: %s", simulation_id, e)


def record_case_meta(simulation_id: str, requirement: str) -> None:
    """Upsert the historical_cases row for a simulation (title, requirement, years)."""
    try:
        client = SupabaseDB.client()
        resp = client.table("historical_cases").select("*").eq("case_id", simulation_id).execute()
        year = datetime.now().year
        fields: dict[str, Any] = {
            "case_id": simulation_id,
            "title": requirement[:200],
            "policy_description": requirement,
            "start_year": year,
            "end_year": year,
            "key_year": year,
            "sources": [],
        }
        if resp.data:
            client.table("historical_cases").update(fields).eq("case_id", simulation_id).execute()
        else:
            client.table("historical_cases").insert(fields).execute()
    except Exception as e:
        logger.warning("Failed to record case meta for case_id=%s: %s", simulation_id, e)


def record_predictions_for_report(simulation_id: str, report_id: str) -> None:
    """Load the report payload and record predictions + case meta for it."""
    try:
        payload = ReportManager.load_payload_v1(report_id)
    except Exception as e:
        logger.warning("Failed to load payload v1 for report %s: %s", report_id, e)
        return
    if not payload:
        logger.warning("No payload v1 found for report %s; skipping case predictions", report_id)
        return
    record_case_predictions(simulation_id, payload)
    record_case_meta(simulation_id, payload.get("simulation_requirement", ""))
