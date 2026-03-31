"""Industry feed API routes."""

import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
from ..middleware.auth import require_auth
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger

feed_bp = Blueprint('feed', __name__)
logger = get_logger('glas.api.feed')

FREE_MONTHLY_VIEWS = 3


def _admin_user_ids():
    return {x.strip() for x in os.environ.get('ADMIN_USER_IDS', '').split(',') if x.strip()}


def _effective_feed_plan(user_id, profile):
    """
    Normalized plan for feed access control.
    Admins always get a paid tier so the feed unlocks even if profiles.plan was not synced.
    """
    if user_id and user_id in _admin_user_ids():
        return 'enterprise'
    if not profile:
        return 'free'
    raw = profile.get('plan') or 'free'
    p = str(raw).strip().lower()
    if p in ('', 'null', 'none'):
        return 'free'
    return p


def _feed_has_full_access(plan_effective: str) -> bool:
    return plan_effective != 'free'


def _get_user_plan():
    """Return (user_id, plan_effective, profile) for the current request."""
    user_id = getattr(g, 'user_id', None)
    if not user_id or user_id == 'anonymous':
        return None, 'free', None
    profile = SupabaseDB.get_profile(user_id)
    plan = _effective_feed_plan(user_id, profile)
    return user_id, plan, profile


def _count_free_views_this_month(user_id):
    """Count how many feed simulations a free user has viewed this month."""
    if not user_id:
        return 0
    try:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        resp = (SupabaseDB.client().table("feed_views")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .gte("viewed_at", month_start)
                .execute())
        return resp.count or 0
    except Exception:
        return 0


def _record_view(user_id, feed_id):
    """Record that a user viewed a feed simulation."""
    if not user_id:
        return
    try:
        SupabaseDB.client().table("feed_views").upsert({
            "user_id": user_id,
            "feed_simulation_id": feed_id,
            "viewed_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,feed_simulation_id").execute()
    except Exception as e:
        logger.warning(f"Failed to record feed view: {e}")


@feed_bp.route('/industries', methods=['GET'])
def list_industries():
    """List available industries."""
    try:
        resp = SupabaseDB.client().table("industries").select("*").execute()
        return jsonify({"success": True, "data": resp.data or []})
    except Exception as e:
        return jsonify({"success": True, "data": []})


@feed_bp.route('/simulations', methods=['GET'])
def list_feed_simulations():
    """List published feed simulations with tiered access."""
    industry_id = request.args.get('industry_id')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    sim_type = request.args.get('type', 'macro')

    try:
        q = (SupabaseDB.client().table("feed_simulations")
             .select("*")
             .eq("is_published", True)
             .order("published_at", desc=True)
             .range(offset, offset + limit - 1))

        if industry_id:
            q = q.eq("industry_id", industry_id)

        resp = q.execute()
        items = resp.data or []

        user_id, plan, profile = _get_user_plan()

        views_used = 0
        views_limit = None
        if not _feed_has_full_access(plan) and user_id:
            views_used = _count_free_views_this_month(user_id)
            views_limit = FREE_MONTHLY_VIEWS

        for item in items:
            is_industry_specific = item.get('is_industry_specific', False)

            if not _feed_has_full_access(plan):
                item.pop('report_id', None)
                item.pop('simulation_id', None)
                item['access'] = 'summary'
            else:
                item['access'] = 'full'

        return jsonify({
            "success": True,
            "data": items,
            "plan": plan,
            "views_used": views_used,
            "views_limit": views_limit,
            "count": len(items),
        })
    except Exception as e:
        logger.error(f"Feed list error: {e}")
        return jsonify({"success": True, "data": [], "count": 0})


@feed_bp.route('/simulations/<feed_id>', methods=['GET'])
def get_feed_simulation(feed_id):
    """Get a single feed simulation with tiered access gating."""
    try:
        resp = (SupabaseDB.client().table("feed_simulations")
                .select("*")
                .eq("id", feed_id)
                .eq("is_published", True)
                .execute())

        if not resp.data:
            return jsonify({"success": False, "error": "Not found"}), 404

        item = resp.data[0]
        user_id, plan, profile = _get_user_plan()
        is_industry_specific = item.get('is_industry_specific', False)

        if not _feed_has_full_access(plan):
            if user_id:
                views_used = _count_free_views_this_month(user_id)
                if views_used >= FREE_MONTHLY_VIEWS:
                    return jsonify({
                        "success": False,
                        "error": "Monthly view limit reached",
                        "upgrade_required": True,
                        "views_used": views_used,
                        "views_limit": FREE_MONTHLY_VIEWS,
                    }), 403
                _record_view(user_id, feed_id)

            item.pop('report_id', None)
            item.pop('simulation_id', None)
            item['access'] = 'summary'

        else:
            item['access'] = 'full'

        return jsonify({"success": True, "data": item})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Admin endpoints (for the platform owner) ---

@feed_bp.route('/admin/simulations', methods=['POST'])
@require_auth
def create_feed_simulation():
    """Create a new feed simulation entry (admin only)."""
    if not _is_admin(g.user_id):
        return jsonify({"success": False, "error": "Admin access required"}), 403

    data = request.get_json() or {}
    required = ['title', 'industry_id', 'scenario_description']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {missing}"}), 400

    row = {
        'title': data['title'],
        'industry_id': data['industry_id'],
        'scenario_description': data['scenario_description'],
        'summary': data.get('summary', ''),
        'is_published': False,
    }

    try:
        resp = SupabaseDB.client().table("feed_simulations").insert(row).execute()
        return jsonify({"success": True, "data": resp.data[0] if resp.data else row})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@feed_bp.route('/admin/simulations/<feed_id>/publish', methods=['POST'])
@require_auth
def publish_feed_simulation(feed_id):
    """Publish a feed simulation (admin only)."""
    if not _is_admin(g.user_id):
        return jsonify({"success": False, "error": "Admin access required"}), 403

    try:
        resp = (SupabaseDB.client().table("feed_simulations")
                .update({"is_published": True, "published_at": datetime.utcnow().isoformat()})
                .eq("id", feed_id)
                .execute())
        return jsonify({"success": True, "data": resp.data[0] if resp.data else {}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@feed_bp.route('/admin/simulations', methods=['GET'])
@require_auth
def list_admin_simulations():
    """List all feed simulations including unpublished (admin only)."""
    if not _is_admin(g.user_id):
        return jsonify({"success": False, "error": "Admin access required"}), 403

    try:
        resp = (SupabaseDB.client().table("feed_simulations")
                .select("*")
                .order("created_at", desc=True)
                .execute())
        return jsonify({"success": True, "data": resp.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _is_admin(user_id):
    """Check if user is admin. Uses ADMIN_USER_IDS env var."""
    return bool(user_id and user_id in _admin_user_ids())
