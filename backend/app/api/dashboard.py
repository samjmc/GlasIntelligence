"""User dashboard API routes."""

from flask import Blueprint, g, jsonify

from ..config import Config
from ..middleware.auth import require_auth
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger
from .simulation_access import caller_may_see, simulation_owner

dashboard_bp = Blueprint("dashboard", __name__)
logger = get_logger("glas.api.dashboard")

RECENT_LIMIT = 10


def _recent_projects() -> list[dict]:
    # From disk, like the owner check: the Supabase projects table is never written.
    projects = [p for p in ProjectManager.list_projects(limit=None) if caller_may_see(p.user_id)]
    return [
        {"id": p.project_id, "name": p.name, "status": getattr(p.status, "value", p.status), "created_at": p.created_at}
        for p in projects[:RECENT_LIMIT]
    ]


def _recent_simulations() -> list[dict]:
    sims = [s for s in SimulationManager().list_simulations() if caller_may_see(simulation_owner(s.simulation_id))]
    sims.sort(key=lambda s: s.created_at or "", reverse=True)
    rows = []
    for s in sims[:RECENT_LIMIT]:
        project = ProjectManager.get_project(s.project_id) if s.project_id else None
        rows.append(
            {
                "id": s.simulation_id,
                "project_id": s.project_id,
                "title": project.name if project else None,
                "status": s.status.value,
                "created_at": s.created_at,
            }
        )
    return rows


@dashboard_bp.route("/overview", methods=["GET"])
@require_auth
def dashboard_overview():
    """Get user dashboard data."""
    user_id = g.user_id

    profile = SupabaseDB.get_profile(user_id) or {}
    projects = _recent_projects()
    simulations = _recent_simulations()

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
