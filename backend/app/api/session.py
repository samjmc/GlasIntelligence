"""Scenario session management — persistent sessions for research + simulation workflows."""

from datetime import datetime, UTC

from flask import Blueprint, request, jsonify, g

from ..config import Config
from ..middleware.auth import require_auth
from ..models.project import ProjectManager
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger

session_bp = Blueprint("session", __name__)
logger = get_logger("glas.session")

STALE_RESEARCH_MINUTES = 30


@session_bp.route("", methods=["POST"])
@require_auth
def create_session():
    """Create a scenario session and deduct one credit."""
    profile = SupabaseDB.get_profile(g.user_id)
    plan = Config.normalize_plan(profile.get("plan", "free") if profile else "free")
    if plan == "free":
        return jsonify({"success": False, "error": "Sessions require a paid plan"}), 403

    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt or len(prompt) < 10:
        return jsonify({"success": False, "error": "Prompt must be at least 10 characters"}), 400

    decision_context = data.get("decision_context") or {}

    if not SupabaseDB.deduct_credit(g.user_id, "Scenario session"):
        profile = SupabaseDB.get_profile(g.user_id)
        return jsonify(
            {
                "success": False,
                "error": "insufficient_credits",
                "credits": profile.get("credits", 0) if profile else 0,
                "message": "You need at least 1 credit to start a session",
            }
        ), 402

    session = SupabaseDB.create_session(g.user_id, prompt, decision_context)
    logger.info(f"Session created: {session['id']} for user {g.user_id}")
    return jsonify({"success": True, "data": session}), 201


@session_bp.route("/active", methods=["GET"])
@require_auth
def get_active_sessions():
    """List the user's active (non-completed, non-abandoned) sessions."""
    sessions = SupabaseDB.get_active_sessions(g.user_id)
    return jsonify({"success": True, "data": sessions})


@session_bp.route("/<session_id>", methods=["GET"])
@require_auth
def get_session(session_id):
    """Get a single session by ID."""
    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404
    return jsonify({"success": True, "data": session})


@session_bp.route("/<session_id>", methods=["PATCH"])
@require_auth
def update_session(session_id):
    """Update session fields (prompt, decision_context)."""
    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    data = request.get_json() or {}
    allowed = {}
    if "prompt" in data:
        allowed["prompt"] = data["prompt"]
    if "decision_context" in data:
        allowed["decision_context"] = data["decision_context"]
    if "bundle_config" in data:
        allowed["bundle_config"] = data["bundle_config"]
    if "simulation_id" in data:
        allowed["simulation_id"] = data["simulation_id"]
    if "project_id" in data:
        allowed["project_id"] = data["project_id"]
        pid = data["project_id"]
        if pid and isinstance(pid, str):
            proj = ProjectManager.get_project(pid)
            if proj and proj.graph_id:
                allowed["graph_id"] = proj.graph_id

    if not allowed:
        return jsonify({"success": False, "error": "No valid fields to update"}), 400

    updated = SupabaseDB.update_session(session_id, **allowed)
    return jsonify({"success": True, "data": updated})


# ── File uploads ──


@session_bp.route("/<session_id>/files", methods=["POST"])
@require_auth
def upload_files(session_id):
    """Upload files to Supabase Storage for this session."""
    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    uploaded = []
    existing_files = session.get("uploaded_files") or []

    for key in request.files:
        f = request.files[key]
        if not f.filename:
            continue
        file_bytes = f.read()
        content_type = f.content_type or "application/octet-stream"
        try:
            storage_path = SupabaseDB.upload_session_file(session_id, f.filename, file_bytes, content_type)
            meta = {
                "name": f.filename,
                "size": len(file_bytes),
                "content_type": content_type,
                "storage_path": storage_path,
            }
            uploaded.append(meta)
            existing_files.append(meta)
        except Exception:
            logger.exception(f"Failed to upload file {f.filename} for session {session_id}")

    if uploaded:
        SupabaseDB.update_session(session_id, uploaded_files=existing_files)

    return jsonify({"success": True, "data": {"uploaded": uploaded, "total": len(existing_files)}})


@session_bp.route("/<session_id>/files/<filename>", methods=["GET"])
@require_auth
def get_file_url(session_id, filename):
    """Get a signed download URL for a session file."""
    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    storage_path = f"{session_id}/{filename}"
    url = SupabaseDB.get_session_file_url(storage_path)
    if not url:
        return jsonify({"success": False, "error": "File not found"}), 404
    return jsonify({"success": True, "data": {"url": url}})


# ── Research within session ──


@session_bp.route("/<session_id>/research", methods=["POST"])
@require_auth
def start_research(session_id):
    """Start deep research within an existing session. Deducts one research credit (free retries on failure)."""
    from ..config import Config

    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    if not Config.DEEP_RESEARCH_ENABLED:
        return jsonify({"success": False, "error": "Deep research is not enabled"}), 403

    rs = session.get("research_status")
    if rs in ("processing", "queued", "claiming"):
        return jsonify({"success": False, "error": "Research is already in progress"}), 409
    if rs == "completed":
        return jsonify({"success": False, "error": "Research already completed. Use the existing dossier."}), 409

    is_retry = rs == "failed"

    # Atomic guard: claim the session for research to prevent double-starts
    # supabase-py 2.x: .or_() doesn't work on UPDATE; .is_() works for NULL, .eq() for strings
    query = SupabaseDB.client().table("scenario_sessions").update({"research_status": "claiming"}).eq("id", session_id)
    if rs is None:
        query = query.is_("research_status", "null")
    else:
        query = query.eq("research_status", rs)
    claim_resp = query.execute()
    if not claim_resp.data:
        return jsonify({"success": False, "error": "Research is already in progress"}), 409

    research_credit_deducted = False
    if not is_retry:
        deduct_ok = SupabaseDB.deduct_research_credit(g.user_id, "Deep research briefing")
        if not deduct_ok:
            SupabaseDB.update_session(session_id, research_status=rs or "none")
            profile = SupabaseDB.get_profile(g.user_id)
            return jsonify(
                {
                    "success": False,
                    "error": "no_research_credits",
                    "research_credits": profile.get("research_credits", 0) if profile else 0,
                    "message": "No research credits remaining. Purchase more to continue.",
                }
            ), 402
        research_credit_deducted = True

    data = request.get_json() or {}
    angle_overrides = data.get("angle_overrides") or None
    if angle_overrides is not None and not isinstance(angle_overrides, dict):
        angle_overrides = None

    prompt = session["prompt"]
    user_id = g.user_id

    scenario_context = None
    bundle_cfg = session.get("bundle_config")
    if bundle_cfg and isinstance(bundle_cfg, dict):
        scenarios = bundle_cfg.get("scenarios", [])
        if scenarios:
            lines = ["The user is running a multi-scenario analysis. Scenarios to research:"]
            for i, sc in enumerate(scenarios, 1):
                title = sc.get("title", f"Scenario {i}")
                desc = sc.get("scenario", sc.get("change_summary", ""))
                lines.append(f"  {i}. {title}: {desc}")
            scenario_context = "\n".join(lines)

    from ..tasks.research_tasks import run_deep_research_task

    profile = SupabaseDB.get_profile(user_id)
    plan = Config.normalize_plan((profile or {}).get("plan", "free"))
    priority_map = {"enterprise": 9, "pro": 5, "free": 1}
    task_priority = priority_map.get(plan, 1)

    try:
        result = run_deep_research_task.apply_async(
            args=[session_id, prompt, user_id],
            kwargs={
                "angle_overrides": angle_overrides,
                "is_retry": is_retry,
                "scenario_context": scenario_context,
            },
            priority=task_priority,
        )
        task_id = result.id

        SupabaseDB.update_session(
            session_id,
            status="researching",
            research_status="queued",
            research_started_at=datetime.now(UTC).isoformat(),
            research_task_id=task_id,
            research_angles=angle_overrides or {},
        )
    except Exception:
        logger.exception(
            "Failed to queue deep research task for session %s",
            session_id,
        )
        revert_rs = rs or "none"
        try:
            SupabaseDB.update_session(session_id, research_status=revert_rs)
        except Exception:
            logger.exception(
                "Failed to revert research_status after queue failure for session %s",
                session_id,
            )
        if research_credit_deducted:
            try:
                SupabaseDB.refund_research_credit(
                    g.user_id,
                    f"Research queue failed — session {session_id}",
                )
            except Exception:
                logger.exception(
                    "Failed to refund research credit after queue failure for session %s",
                    session_id,
                )
        return jsonify(
            {
                "success": False,
                "error": "Failed to queue research task",
            }
        ), 500

    return jsonify({"success": True, "data": {"task_id": task_id, "session_id": session_id}})


@session_bp.route("/<session_id>/research/status", methods=["GET"])
@require_auth
def research_status(session_id):
    """Poll research status from Supabase (Celery task writes state there directly)."""
    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    rs = session.get("research_status")

    if rs == "completed":
        return jsonify(
            {
                "success": True,
                "data": {
                    "status": "completed",
                    "message": "Research complete",
                    "dossier": session.get("research_dossier"),
                },
            }
        )

    if rs == "failed":
        return jsonify(
            {
                "success": True,
                "data": {
                    "status": "failed",
                    "message": "Research failed. You can retry for free.",
                    "can_retry": True,
                },
            }
        )

    if rs == "claiming":
        logger.debug("research/status poll: session %s in claiming", session_id)
        return jsonify(
            {
                "success": True,
                "data": {
                    "status": "claiming",
                    "message": "Research starting — queueing your job...",
                },
            }
        )

    if rs == "queued":
        return jsonify(
            {
                "success": True,
                "data": {
                    "status": "queued",
                    "message": "Research queued — your job will start shortly.",
                },
            }
        )

    if rs == "processing":
        started = session.get("research_started_at")
        if started:
            try:
                started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                elapsed = (datetime.now(UTC) - started_dt).total_seconds() / 60
                if elapsed > STALE_RESEARCH_MINUTES:
                    SupabaseDB.update_session(
                        session_id,
                        research_status="failed",
                        status="active",
                    )
                    user_id = session.get("user_id") or g.user_id
                    SupabaseDB.refund_research_credit(user_id, "Stale research timeout")
                    logger.info(f"Refunded research credit for stale session {session_id} (user {user_id})")
                    return jsonify(
                        {
                            "success": True,
                            "data": {
                                "status": "failed",
                                "message": "Research timed out. You can retry for free.",
                                "can_retry": True,
                            },
                        }
                    )
            except (ValueError, TypeError):
                pass

        return jsonify(
            {
                "success": True,
                "data": {
                    "status": "processing",
                    "message": "Research in progress...",
                },
            }
        )

    return jsonify({"success": True, "data": {"status": "none", "message": "No research started"}})


# ── Session lifecycle ──


@session_bp.route("/<session_id>/abandon", methods=["POST"])
@require_auth
def abandon_session(session_id):
    """Mark a session as abandoned. No refund."""
    session = SupabaseDB.get_session(session_id, user_id=g.user_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    update_fields = {"status": "abandoned"}
    rs = session.get("research_status")
    if rs in ("processing", "claiming", "queued"):
        update_fields["research_status"] = "failed"

    SupabaseDB.update_session(session_id, **update_fields)
    logger.info(f"Session {session_id} abandoned by user {g.user_id}")
    return jsonify({"success": True})
