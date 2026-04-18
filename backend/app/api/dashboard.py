"""User dashboard API routes."""

from flask import Blueprint, jsonify, g
from ..config import Config
from ..middleware.auth import require_auth
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger

dashboard_bp = Blueprint("dashboard", __name__)
logger = get_logger("glas.api.dashboard")


@dashboard_bp.route("/overview", methods=["GET"])
@require_auth
def dashboard_overview():
    """Get user dashboard data."""
    user_id = g.user_id

    profile = SupabaseDB.get_profile(user_id) or {}
    projects = SupabaseDB.list_projects(user_id, limit=10)
    simulations = SupabaseDB.list_simulations(user_id, limit=10)

    credit_resp = (
        SupabaseDB.client()
        .table("credit_transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "profile": {
                    "email": profile.get("email", ""),
                    "display_name": profile.get("display_name", ""),
                    "plan": Config.normalize_plan(profile.get("plan", "free")),
                    "credits": profile.get("credits", 0),
                    "research_credits": profile.get("research_credits", 0),
                },
                "recent_projects": projects,
                "recent_simulations": simulations,
                "credit_history": credit_resp.data or [],
            },
        }
    )


@dashboard_bp.route("/usage", methods=["GET"])
@require_auth
def usage_stats():
    """Get usage statistics for the current billing period."""
    user_id = g.user_id

    from datetime import datetime

    period_start = (datetime.utcnow().replace(day=1)).isoformat()

    usage_resp = (
        SupabaseDB.client()
        .table("credit_transactions")
        .select("*")
        .eq("user_id", user_id)
        .eq("type", "usage")
        .gte("created_at", period_start)
        .execute()
    )

    simulations_this_month = len(usage_resp.data) if usage_resp.data else 0
    profile = SupabaseDB.get_profile(user_id) or {}

    return jsonify(
        {
            "success": True,
            "data": {
                "simulations_this_month": simulations_this_month,
                "credits_remaining": profile.get("credits", 0),
                "research_credits_remaining": profile.get("research_credits", 0),
                "plan": Config.normalize_plan(profile.get("plan", "free")),
            },
        }
    )
