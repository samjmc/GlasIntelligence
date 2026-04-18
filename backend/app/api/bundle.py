"""Decision bundle API routes for grouping related simulations."""

import json
import re
import uuid
from flask import Blueprint, request, jsonify, g
from ..config import Config
from ..middleware.auth import require_auth
from ..services.supabase_client import SupabaseDB
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from datetime import UTC

bundle_bp = Blueprint("bundle", __name__)
logger = get_logger("glas.api.bundle")

BUNDLE_SCENARIO_PROMPT_TEMPLATE = """\
You are a decision analysis strategist. Given a user's decision context, generate exactly \
{scenario_count} simulation scenarios that together form a comprehensive analysis.

The scenarios should cover:
- The base case (most likely outcome)
- An optimistic scenario
- A pessimistic / stress-test scenario
- Additional scenarios testing different variables (e.g. timing, scale, geopolitical shifts, \
competitor response, regulatory change)

Return ONLY a valid JSON array with exactly {scenario_count} items:
[{{"title": "...", "scenario": "...", "change_summary": "..."}}]

Each scenario must be specific, actionable, and include concrete parameters where possible. \
The "scenario" field should be a full simulation prompt (2-4 sentences) that can run independently. \
The "change_summary" field should be a one-line description of what this scenario tests.
"""


@bundle_bp.route("/create", methods=["POST"])
@require_auth
def create_bundle():
    """Create a decision bundle with LLM-generated sub-scenarios."""
    try:
        data = request.get_json() or {}
        title = data.get("title", "").strip()
        decision_context = data.get("decision_context", "").strip()
        scenario_count = data.get("scenario_count", 5)

        if not decision_context:
            return jsonify({"success": False, "error": "decision_context is required"}), 400

        try:
            scenario_count = max(2, min(7, int(scenario_count)))
        except (ValueError, TypeError):
            scenario_count = 5

        if not title:
            title = decision_context[:80] + ("..." if len(decision_context) > 80 else "")

        system_prompt = BUNDLE_SCENARIO_PROMPT_TEMPLATE.format(scenario_count=scenario_count)

        llm = LLMClient()
        raw = llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": decision_context},
            ],
            temperature=0.7,
            max_tokens=2500,
        )

        try:
            suggested = json.loads(raw)
        except json.JSONDecodeError:
            suggested = []
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    suggested = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        if not isinstance(suggested, list):
            return jsonify(
                {"success": False, "error": "LLM returned invalid scenario format; expected a JSON array"},
            ), 422
        _expected_keys = ("title", "scenario", "change_summary")
        for _idx, _item in enumerate(suggested):
            if not isinstance(_item, dict):
                return jsonify(
                    {"success": False, "error": f"Scenario {_idx} must be an object"},
                ), 422
            if not all(_k in _item for _k in _expected_keys):
                return jsonify(
                    {
                        "success": False,
                        "error": f"Scenario {_idx} must include keys: title, scenario, change_summary",
                    },
                ), 422

        bundle = SupabaseDB.create_bundle(
            user_id=g.user_id,
            title=title,
            decision_context=decision_context,
            suggested_scenarios=suggested,
        )

        return jsonify({"success": True, "data": bundle})

    except Exception as e:
        logger.error(f"Bundle creation failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to create bundle"}), 500


@bundle_bp.route("/<bundle_id>", methods=["GET"])
@require_auth
def get_bundle(bundle_id):
    """Get a decision bundle by ID."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404

    total = len(bundle.get("suggested_scenarios", []))
    completed = len(bundle.get("completed_scenarios", []))
    bundle["progress"] = {"total": total, "completed": completed}

    return jsonify({"success": True, "data": bundle})


@bundle_bp.route("/<bundle_id>", methods=["PATCH"])
@require_auth
def update_bundle_route(bundle_id):
    """Update a decision bundle (scenarios, status, etc.)."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404

    data = request.get_json() or {}
    allowed = {"suggested_scenarios", "status", "title"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({"success": False, "error": "No valid fields to update"}), 400

    SupabaseDB.update_bundle(bundle_id, **fields)
    return jsonify({"success": True})


@bundle_bp.route("/<bundle_id>/complete-scenario", methods=["POST"])
@require_auth
def complete_scenario(bundle_id):
    """Mark a bundle scenario as completed."""
    try:
        data = request.get_json() or {}
        scenario_index = data.get("scenario_index")
        simulation_id = data.get("simulation_id", "")
        report_id = data.get("report_id", "")

        if scenario_index is None:
            return jsonify({"success": False, "error": "scenario_index is required"}), 400

        session_id = data.get("session_id")
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required"}), 400
        if not SupabaseDB.get_session(session_id, user_id=g.user_id):
            return jsonify({"success": False, "error": "Session not found"}), 404

        bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
        if not bundle:
            return jsonify({"success": False, "error": "Bundle not found"}), 404

        suggested = bundle.get("suggested_scenarios", [])
        if scenario_index < 0 or scenario_index >= len(suggested):
            return jsonify({"success": False, "error": "Invalid scenario_index"}), 400

        completed = bundle.get("completed_scenarios", [])
        if any(c.get("scenario_index") == scenario_index for c in completed):
            return jsonify({"success": False, "error": "Scenario already completed"}), 409
        sc = suggested[scenario_index]
        title = sc.get("title", "") if isinstance(sc, dict) else ""
        completed.append(
            {
                "scenario_index": scenario_index,
                "title": title,
                "simulation_id": simulation_id,
                "report_id": report_id,
            }
        )

        status = "completed" if len(completed) >= len(suggested) else "in_progress"
        SupabaseDB.update_bundle(bundle_id, completed_scenarios=completed, status=status)

        return jsonify({"success": True, "data": {"completed": len(completed), "total": len(suggested)}})

    except Exception as e:
        logger.error(f"Complete scenario failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to update bundle"}), 500


@bundle_bp.route("/list", methods=["GET"])
@require_auth
def list_bundles():
    """List user's decision bundles."""
    bundles = SupabaseDB.list_bundles(g.user_id)
    for b in bundles:
        total = len(b.get("suggested_scenarios", []))
        completed = len(b.get("completed_scenarios", []))
        b["progress"] = {"total": total, "completed": completed}
    return jsonify({"success": True, "data": bundles})


@bundle_bp.route("/<bundle_id>", methods=["DELETE"])
@require_auth
def delete_bundle(bundle_id):
    """Delete a decision bundle."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404
    SupabaseDB.delete_bundle(bundle_id, g.user_id)
    return jsonify({"success": True})


@bundle_bp.route("/<bundle_id>/run", methods=["POST"])
@require_auth
def run_bundle(bundle_id):
    """Start executing all scenarios in a bundle sequentially via Celery."""
    dispatched = False
    enqueued = False
    try:
        bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
        if not bundle:
            return jsonify({"success": False, "error": "Bundle not found"}), 404

        if bundle.get("status") == "running":
            return jsonify({"success": False, "error": "Bundle is already running"}), 409

        data = request.get_json() or {}
        session_id = data.get("session_id")
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required"}), 400

        if not SupabaseDB.get_session(session_id, user_id=g.user_id):
            return jsonify({"success": False, "error": "Session not found"}), 404

        scenarios = bundle.get("suggested_scenarios", [])
        if not scenarios:
            return jsonify({"success": False, "error": "Bundle has no scenarios"}), 400

        from datetime import datetime

        from ..tasks.bundle_tasks import run_bundle_task

        # Predetermined task id: persist celery_task_id before enqueue so workers never read
        # the row before the id matches self.request.id (avoids idempotency false abort).
        task_id = str(uuid.uuid4())
        SupabaseDB.update_bundle(
            bundle_id,
            status="running",
            completed_scenarios=[],
            session_id=session_id,
            celery_task_id=task_id,
            started_at=datetime.now(UTC).isoformat(),
        )
        dispatched = True

        try:
            run_bundle_task.apply_async(
                args=(bundle_id, session_id, g.user_id),
                task_id=task_id,
            )
        except Exception as dispatch_err:
            logger.error(f"Bundle task dispatch failed: {dispatch_err}", exc_info=True)
            SupabaseDB.update_bundle(bundle_id, status="failed", error="Failed to dispatch task")
            return jsonify({"success": False, "error": "Failed to start bundle"}), 500

        enqueued = True

        return jsonify(
            {
                "success": True,
                "data": {
                    "bundle_id": bundle_id,
                    "task_id": task_id,
                    "total_scenarios": len(scenarios),
                    "status": "running",
                },
            }
        )

    except Exception as e:
        if dispatched:
            logger.error(
                "Bundle run failed after bundle row was set to running; Celery may still be executing: %s",
                e,
                exc_info=True,
            )
        elif enqueued:
            logger.error(
                "Bundle run failed after Celery enqueue (bundle row was already running): %s",
                e,
                exc_info=True,
            )
            try:
                SupabaseDB.update_bundle(
                    bundle_id,
                    status="failed",
                    error="Post-dispatch DB update failed",
                )
            except Exception:
                logger.exception("Failed to mark bundle failed after post-dispatch error")
        else:
            logger.error(f"Bundle run failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to start bundle"}), 500


@bundle_bp.route("/<bundle_id>/status", methods=["GET"])
@require_auth
def bundle_status(bundle_id):
    """Get detailed bundle execution status."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404

    suggested = bundle.get("suggested_scenarios") or []
    completed = bundle.get("completed_scenarios") or []
    completed_indices = {c.get("scenario_index") for c in completed}

    current_running = bundle.get("current_scenario_index")
    current_sim_id = bundle.get("current_simulation_id")

    scenario_statuses = []
    for i, sc in enumerate(suggested):
        if i in completed_indices:
            match = next((c for c in completed if c.get("scenario_index") == i), {})
            status = "failed" if match.get("failed") else "completed"
            sim_id = match.get("simulation_id")
        elif current_running is not None and i == current_running:
            status = "running"
            sim_id = current_sim_id
        elif bundle.get("status") in ("completed", "completed_with_errors", "failed"):
            status = "skipped"
            sim_id = None
        else:
            status = "pending"
            sim_id = None
        title = sc.get("title", "") if isinstance(sc, dict) else ""
        scenario_statuses.append(
            {
                "index": i,
                "title": title,
                "status": status,
                "simulation_id": sim_id,
            }
        )

    completed_ok = sum(1 for s in scenario_statuses if s["status"] == "completed")

    return jsonify(
        {
            "success": True,
            "data": {
                "bundle_id": bundle_id,
                "title": bundle.get("title", ""),
                "status": bundle.get("status", "in_progress"),
                "total": len(suggested),
                "completed": completed_ok,
                "scenarios": scenario_statuses,
                "error": bundle.get("error"),
                "started_at": bundle.get("started_at"),
            },
        }
    )


@bundle_bp.route("/<bundle_id>/comparison", methods=["GET"])
@require_auth
def bundle_comparison(bundle_id):
    """Get comparison data for all completed scenarios in a bundle."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404

    completed = bundle.get("completed_scenarios") or []
    if not completed:
        return jsonify({"success": True, "data": {"scenarios": [], "bundle_id": bundle_id}})

    from ..services.simulation_manager import SimulationManager
    from ..services.simulation_runner import SimulationRunner

    suggested = bundle.get("suggested_scenarios") or []
    results = []
    manager = SimulationManager()
    for entry in completed:
        sim_id = entry.get("simulation_id")
        if not sim_id or entry.get("failed"):
            continue
        sim_state = manager.get_simulation(sim_id)
        if not sim_state:
            continue

        idx = entry.get("scenario_index")
        change_summary = ""
        if isinstance(idx, int) and 0 <= idx < len(suggested):
            sc = suggested[idx]
            if isinstance(sc, dict):
                change_summary = (sc.get("change_summary") or "").strip()

        run_state = SimulationRunner.get_run_state(sim_id)
        rounds_done = int(getattr(sim_state, "current_round", 0) or 0)
        rounds_planned = 0
        actions_total = 0
        runner_status = None
        twitter_done = reddit_done = False
        if run_state:
            runner_status = run_state.runner_status.value
            rounds_done = max(
                rounds_done,
                int(run_state.current_round or 0),
                int(run_state.twitter_current_round or 0),
                int(run_state.reddit_current_round or 0),
            )
            rounds_planned = int(run_state.total_rounds or 0)
            actions_total = int((run_state.twitter_actions_count or 0) + (run_state.reddit_actions_count or 0))
            twitter_done = bool(run_state.twitter_completed)
            reddit_done = bool(run_state.reddit_completed)

        if rounds_planned <= 0:
            cfg = manager.get_simulation_config(sim_id)
            if cfg and isinstance(cfg.get("time_config"), dict):
                tc = cfg["time_config"]
                try:
                    total_dur = int(tc.get("total_duration", 0) or 0)
                    per_round = max(1, int(tc.get("per_round", 1) or 1))
                    if total_dur > 0:
                        rounds_planned = total_dur // per_round
                except (TypeError, ValueError):
                    pass

        results.append(
            {
                "scenario_index": entry.get("scenario_index"),
                "title": entry.get("title", ""),
                "change_summary": change_summary,
                "simulation_id": sim_id,
                "report_id": entry.get("report_id"),
                "status": "completed",
                "final_state": {
                    # Legacy field: highest round reached (was wrong when only state.json was read)
                    "total_rounds": rounds_done,
                    "rounds_completed": rounds_done,
                    "rounds_planned": rounds_planned,
                    "total_actions": actions_total,
                    "runner_status": runner_status,
                    "twitter_completed": twitter_done,
                    "reddit_completed": reddit_done,
                    "entities_count": sim_state.entities_count,
                    "profiles_count": sim_state.profiles_count,
                    "status": sim_state.status.value,
                },
            }
        )

    return jsonify(
        {
            "success": True,
            "data": {
                "bundle_id": bundle_id,
                "title": bundle.get("title", ""),
                "decision_context": bundle.get("decision_context", ""),
                "total_scenarios": len(suggested),
                "completed_count": len(results),
                "scenarios": results,
                "synthesis": bundle.get("synthesis"),
            },
        }
    )


@bundle_bp.route("/<bundle_id>/synthesis", methods=["GET"])
@require_auth
def get_bundle_synthesis(bundle_id):
    """Return persisted bundle executive synthesis (JSON), if any."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404
    syn = bundle.get("synthesis")
    if not syn:
        return jsonify({"success": False, "error": "No synthesis for this bundle"}), 404
    return jsonify({"success": True, "data": syn})


@bundle_bp.route("/<bundle_id>/synthesis/weights", methods=["PATCH"])
@require_auth
def patch_bundle_synthesis_weights(bundle_id):
    """Update branch weights; server recomputes marginals from stored mappings and payloads."""
    if not Config.ENABLE_BUNDLE_SYNTHESIS:
        return jsonify({"success": False, "error": "Bundle synthesis is disabled"}), 403
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404
    synthesis = bundle.get("synthesis")
    if not synthesis:
        return jsonify({"success": False, "error": "No synthesis for this bundle"}), 404
    data = request.get_json() or {}
    raw_weights = data.get("branch_weights")
    if not isinstance(raw_weights, list) or not raw_weights:
        return jsonify({"success": False, "error": "branch_weights (non-empty list) is required"}), 400
    for i, w in enumerate(raw_weights):
        if not isinstance(w, dict):
            return jsonify(
                {
                    "success": False,
                    "error": f"branch_weights[{i}] must be an object, not {type(w).__name__}",
                }
            ), 400

    from ..services.bundle_synthesis import load_payloads_from_bundle, recompute_marginals_from_weights

    # Hardening gap: load_payloads_from_bundle is outside the try below — failures here still
    # propagate as unhandled errors. Future pass: wrap with try/except or extend the same block.
    payloads = load_payloads_from_bundle(bundle)
    if len(payloads) < 2:
        return jsonify({"success": False, "error": "Not enough scenario payloads to recompute marginals"}), 400

    try:
        updated = recompute_marginals_from_weights(synthesis, raw_weights, payloads)
        SupabaseDB.update_bundle(bundle_id, synthesis=updated)
    except Exception:
        logger.exception("Failed to recompute synthesis weights for bundle %s", bundle_id)
        return jsonify({"success": False, "error": "Failed to recompute synthesis weights"}), 500
    return jsonify({"success": True, "data": updated})
