"""Decision bundle API routes for grouping related simulations."""

import json
import re
from flask import Blueprint, request, jsonify, g
from ..middleware.auth import require_auth
from ..services.supabase_client import SupabaseDB
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

bundle_bp = Blueprint('bundle', __name__)
logger = get_logger('glas.api.bundle')

BUNDLE_SCENARIO_PROMPT = """\
You are a decision analysis strategist. Given a user's decision context, generate 3-5 simulation \
scenarios that together form a comprehensive analysis of the decision.

The scenarios should cover:
- The base case (most likely outcome)
- An optimistic scenario
- A pessimistic / stress-test scenario
- At least one scenario testing a different variable (e.g. timing, scale, competitor response)

Return ONLY valid JSON array:
[{"title": "...", "scenario": "...", "change_summary": "..."}]

Each scenario must be specific, actionable, and include concrete parameters where possible.
"""


@bundle_bp.route('/create', methods=['POST'])
@require_auth
def create_bundle():
    """Create a decision bundle with LLM-generated sub-scenarios."""
    try:
        data = request.get_json() or {}
        title = data.get('title', '').strip()
        decision_context = data.get('decision_context', '').strip()

        if not decision_context:
            return jsonify({"success": False, "error": "decision_context is required"}), 400

        if not title:
            title = decision_context[:80] + ('...' if len(decision_context) > 80 else '')

        llm = LLMClient()
        raw = llm.chat(
            messages=[
                {"role": "system", "content": BUNDLE_SCENARIO_PROMPT},
                {"role": "user", "content": decision_context},
            ],
            temperature=0.7,
            max_tokens=1500,
        )

        try:
            suggested = json.loads(raw)
        except json.JSONDecodeError:
            suggested = []
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    suggested = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

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


@bundle_bp.route('/<bundle_id>', methods=['GET'])
@require_auth
def get_bundle(bundle_id):
    """Get a decision bundle by ID."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404

    total = len(bundle.get('suggested_scenarios', []))
    completed = len(bundle.get('completed_scenarios', []))
    bundle['progress'] = {"total": total, "completed": completed}

    return jsonify({"success": True, "data": bundle})


@bundle_bp.route('/<bundle_id>/complete-scenario', methods=['POST'])
@require_auth
def complete_scenario(bundle_id):
    """Mark a bundle scenario as completed."""
    try:
        data = request.get_json() or {}
        scenario_index = data.get('scenario_index')
        simulation_id = data.get('simulation_id', '')
        report_id = data.get('report_id', '')

        if scenario_index is None:
            return jsonify({"success": False, "error": "scenario_index is required"}), 400

        bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
        if not bundle:
            return jsonify({"success": False, "error": "Bundle not found"}), 404

        suggested = bundle.get('suggested_scenarios', [])
        if scenario_index < 0 or scenario_index >= len(suggested):
            return jsonify({"success": False, "error": "Invalid scenario_index"}), 400

        completed = bundle.get('completed_scenarios', [])
        if any(c.get('scenario_index') == scenario_index for c in completed):
            return jsonify({"success": False, "error": "Scenario already completed"}), 409
        completed.append({
            "scenario_index": scenario_index,
            "title": suggested[scenario_index].get('title', ''),
            "simulation_id": simulation_id,
            "report_id": report_id,
        })

        status = 'completed' if len(completed) >= len(suggested) else 'in_progress'
        SupabaseDB.update_bundle(bundle_id, completed_scenarios=completed, status=status)

        return jsonify({"success": True, "data": {"completed": len(completed), "total": len(suggested)}})

    except Exception as e:
        logger.error(f"Complete scenario failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to update bundle"}), 500


@bundle_bp.route('/list', methods=['GET'])
@require_auth
def list_bundles():
    """List user's decision bundles."""
    bundles = SupabaseDB.list_bundles(g.user_id)
    for b in bundles:
        total = len(b.get('suggested_scenarios', []))
        completed = len(b.get('completed_scenarios', []))
        b['progress'] = {"total": total, "completed": completed}
    return jsonify({"success": True, "data": bundles})


@bundle_bp.route('/<bundle_id>', methods=['DELETE'])
@require_auth
def delete_bundle(bundle_id):
    """Delete a decision bundle."""
    bundle = SupabaseDB.get_bundle(bundle_id, g.user_id)
    if not bundle:
        return jsonify({"success": False, "error": "Bundle not found"}), 404
    SupabaseDB.delete_bundle(bundle_id, g.user_id)
    return jsonify({"success": True})
