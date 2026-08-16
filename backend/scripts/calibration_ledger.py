"""
Calibration ledger CLI: record manual outcomes and grade predictions.

Two subcommands:

    python backend/scripts/calibration_ledger.py record-outcome <case_id> <dimension> <actual_score>
    python backend/scripts/calibration_ledger.py grade

- ``record-outcome`` upserts a ``case_outcomes`` row by (case_id, dimension);
  actual_score must be numeric in [0, 100].
- ``grade`` (default) matches ``case_predictions`` against ``case_outcomes`` by
  (case_id, dimension), computes accuracy/bias metrics via
  ``app.services.calibration_grading.compute_calibration_grades``, and inserts
  one ``calibration_runs`` row. ``weight_adjustments`` stays null — the
  feed-back-into-future-predictions step is a documented out-of-scope boundary.

Requires the repo `.env` with SUPABASE_URL and SUPABASE_SERVICE_KEY.
"""

import argparse
import os
import sys
from datetime import UTC, datetime

# Shared bootstrap (see scripts/lib/paths.py): puts backend/ on sys.path so
# `from app.services...` imports work when run as a standalone script.
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_lib_dir = os.path.join(_scripts_dir, "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
from paths import init_script_paths  # noqa: E402

_scripts_dir, _backend_dir, _project_root = init_script_paths(__file__)  # noqa: F841

# Load the repo .env so SupabaseDB.client() gets SUPABASE_URL / SUPABASE_SERVICE_KEY.
from dotenv import load_dotenv  # noqa: E402

_env_file = os.path.join(_project_root, ".env")
if os.path.exists(_env_file):
    load_dotenv(_env_file)
else:
    _backend_env = os.path.join(_backend_dir, ".env")
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)

from app.services.calibration_grading import compute_calibration_grades  # noqa: E402
from app.services.supabase_client import SupabaseDB  # noqa: E402


def _row_summary(row: dict) -> str:
    return (
        f"id={row.get('id')} case_id={row.get('case_id')} "
        f"dimension={row.get('dimension')} actual_score={row.get('actual_score')}"
    )


def cmd_record_outcome(args: argparse.Namespace) -> int:
    """Upsert one case_outcomes row by (case_id, dimension)."""
    try:
        actual_score = float(args.actual_score)
    except (TypeError, ValueError):
        print(f"Error: actual_score must be numeric, got {args.actual_score!r}", file=sys.stderr)
        return 2
    if not 0.0 <= actual_score <= 100.0:
        print(f"Error: actual_score must be in [0, 100], got {args.actual_score}", file=sys.stderr)
        return 2

    client = SupabaseDB.client()
    existing = (
        client.table("case_outcomes")
        .select("*")
        .eq("case_id", args.case_id)
        .eq("dimension", args.dimension)
        .execute()
    )
    if existing.data:
        updated = (
            client.table("case_outcomes")
            .update({"actual_score": actual_score})
            .eq("case_id", args.case_id)
            .eq("dimension", args.dimension)
            .execute()
        )
        row = (updated.data or existing.data)[0]
        print(f"Updated case_outcome: {_row_summary(row)}")
    else:
        inserted = (
            client.table("case_outcomes")
            .insert({"case_id": args.case_id, "dimension": args.dimension, "actual_score": actual_score})
            .execute()
        )
        row = (inserted.data or [{"case_id": args.case_id, "dimension": args.dimension, "actual_score": actual_score}])[0]
        print(f"Inserted case_outcome: {_row_summary(row)}")
    return 0


def _prediction_window(preds: list[dict], outcomes: list[dict]) -> str:
    stamps = [row.get("created_at") for row in preds + outcomes if row.get("created_at")]
    if not stamps:
        return "n/a"
    return f"{min(stamps)} .. {max(stamps)}"


def _matched_case_ids(preds: list[dict], outcomes: list[dict]) -> set:
    outcome_keys = {(row.get("case_id"), row.get("dimension")) for row in outcomes}
    return {row.get("case_id") for row in preds if (row.get("case_id"), row.get("dimension")) in outcome_keys}


def _build_notes(grades: dict, preds: list[dict], outcomes: list[dict], cases: list[dict]) -> str:
    lines = [
        f"predictions graded: {grades['n_predictions']}",
        f"date window (prediction/outcome created_at): {_prediction_window(preds, outcomes)}",
        "weight_adjustments: null (feed-back step is out of scope by design)",
    ]
    matched_ids = _matched_case_ids(preds, outcomes)
    if matched_ids:
        title_by_id = {row.get("case_id"): row.get("title") or row.get("case_id") for row in cases}
        titles = ", ".join(f"{title_by_id.get(cid, cid)} ({cid})" for cid in sorted(matched_ids))
        lines.append(f"cases graded: {titles}")
    binary = grades.get("binary")
    if binary:
        lines.append(
            f"binary cohort: n={binary['n']}, brier={binary['brier']:.4f}, "
            f"mean_log_score={binary['mean_log_score']:.4f}"
        )
    return "\n".join(lines)


def cmd_grade(args: argparse.Namespace) -> int:
    """Match predictions to outcomes and insert one calibration_runs row."""
    client = SupabaseDB.client()
    preds = (client.table("case_predictions").select("*").execute().data) or []
    outcomes = (client.table("case_outcomes").select("*").execute().data) or []
    cases = (client.table("historical_cases").select("*").execute().data) or []

    grades = compute_calibration_grades(preds, outcomes)
    if grades["n_predictions"] == 0:
        print(
            "Nothing to grade: no (case_id, dimension) pairs match between "
            "case_predictions and case_outcomes."
        )
        return 0

    row = {
        "run_date": datetime.now(UTC).isoformat(),
        "total_cases": grades["total_cases"],
        "overall_accuracy": grades["overall_accuracy"],
        "dimension_accuracies": grades["dimension_accuracies"],
        "dimension_biases": grades["dimension_biases"],
        "notes": _build_notes(grades, preds, outcomes, cases),
    }
    inserted = client.table("calibration_runs").insert(row).execute()
    result = (inserted.data or [row])[0]
    print(f"Inserted calibration_runs id={result.get('id')}")
    print(f"  total_cases={grades['total_cases']} n_predictions={grades['n_predictions']}")
    print(f"  overall_accuracy={grades['overall_accuracy']:.4f}")
    print(f"  dimension_accuracies={grades['dimension_accuracies']}")
    print(f"  dimension_biases={grades['dimension_biases']}")
    if "binary" in grades:
        binary = grades["binary"]
        print(
            f"  binary cohort: n={binary['n']} brier={binary['brier']:.4f} "
            f"mean_log_score={binary['mean_log_score']:.4f}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calibration_ledger",
        description="Record case outcomes and grade case predictions into calibration_runs.",
    )
    subparsers = parser.add_subparsers(dest="command")

    grade_parser = subparsers.add_parser("grade", help="grade predictions vs outcomes into calibration_runs (default)")
    grade_parser.set_defaults(func=cmd_grade)

    record_parser = subparsers.add_parser("record-outcome", help="upsert a case_outcomes row")
    record_parser.add_argument("case_id", help="simulation_id string")
    record_parser.add_argument("dimension", help="scenario name string, as in the report payload")
    record_parser.add_argument("actual_score", help="resolved score, numeric in [0, 100]")
    record_parser.set_defaults(func=cmd_record_outcome)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "grade"
        args.func = cmd_grade
    try:
        return int(args.func(args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
