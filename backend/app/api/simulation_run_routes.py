"""Simulation run control, run status, timeline, agent stats, and SQLite post/comment routes."""

import os
import traceback

from flask import g, jsonify, request

from . import simulation_bp
from .simulation_helpers import check_simulation_prepared
from ..config import Config
from ..middleware.auth import require_auth
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger

logger = get_logger("glas.api.simulation")


# ============== Simulation Run Control Endpoints ==============


@simulation_bp.route("/start", methods=["POST"])
@require_auth
def start_simulation():
    """
    Start running simulation

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",          // required
            "platform": "parallel",                // optional: twitter / reddit / parallel (default)
            "max_rounds": 100,                     // optional: max simulation rounds, to truncate long simulations
            "enable_graph_memory_update": false,   // optional: whether to dynamically update Agent activity to Zep graph memory
            "force": false,                        // optional: force restart (stops running simulation and cleans logs)
            "time_config": {}                      // optional: merged into simulation_config.json time_config before run (e.g. time_scale)
        }

    About force parameter:
        - When enabled, if simulation is running or completed, it will be stopped and run logs cleaned
        - Cleaned content includes: run_state.json, actions.jsonl, simulation.log, etc.
        - Does not clean config files (simulation_config.json) or profile files
        - Useful for scenarios requiring simulation re-run

    About enable_graph_memory_update:
        - When enabled, all Agent activities (posts, comments, likes, etc.) are updated to Zep graph in real-time
        - This lets the graph "remember" the simulation process for subsequent analysis or AI conversations
        - Requires the simulation's associated project to have a valid graph_id
        - Uses batch update mechanism to reduce API calls

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,
                "force_restarted": true
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        platform = data.get("platform", "parallel")
        max_rounds = data.get("max_rounds")
        enable_graph_memory_update = data.get("enable_graph_memory_update", False)
        force = data.get("force", False)
        time_config_patch = data.get("time_config")
        if time_config_patch is not None and not isinstance(time_config_patch, dict):
            return jsonify({"success": False, "error": "time_config must be an object"}), 400

        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({"success": False, "error": "max_rounds must be a positive integer"}), 400
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "max_rounds must be a valid integer"}), 400

        if platform not in ["twitter", "reddit", "parallel"]:
            return jsonify(
                {"success": False, "error": f"Invalid platform type: {platform}, options: twitter/reddit/parallel"}
            ), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({"success": False, "error": f"Simulation not found: {simulation_id}"}), 404

        force_restarted = False

        if state.status != SimulationStatus.READY:
            is_prepared, prepare_info = check_simulation_prepared(simulation_id)

            if is_prepared:
                if state.status == SimulationStatus.RUNNING:
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        if force:
                            logger.info(f"Force mode: stopping running simulation {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"Warning while stopping simulation: {str(e)}")
                        else:
                            return jsonify(
                                {
                                    "success": False,
                                    "error": "Simulation is running, please call /stop first, or use force=true to force restart",
                                }
                            ), 400

                if force:
                    logger.info(f"Force mode: cleaning simulation logs {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"Warning while cleaning logs: {cleanup_result.get('errors')}")
                    force_restarted = True

                logger.info(
                    f"Simulation {simulation_id} preparation complete, resetting status to ready (original status: {state.status.value})"
                )
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Simulation not ready, current status: {state.status.value}, please call /prepare first",
                    }
                ), 400

        graph_id = None
        if enable_graph_memory_update:
            graph_id = state.graph_id
            if not graph_id:
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id

            if not graph_id:
                logger.warning(
                    "Simulation %s: graph memory update requested but no graph_id on simulation or project; "
                    "starting without live Zep graph writes",
                    simulation_id,
                )
                enable_graph_memory_update = False
            else:
                logger.info(f"Graph memory update enabled: simulation_id={simulation_id}, graph_id={graph_id}")

        session_id = data.get("session_id")
        credit_covered = False
        session_row = None
        if session_id:
            session_row = SupabaseDB.get_session(session_id, user_id=g.user_id)
            if session_row and session_row.get("simulation_count", 0) == 0:
                credit_covered = True

        if not credit_covered:
            if not SupabaseDB.deduct_credit(g.user_id, "Simulation run"):
                profile = SupabaseDB.get_profile(g.user_id)
                return jsonify(
                    {
                        "success": False,
                        "error": "insufficient_credits",
                        "credits": profile.get("credits", 0) if profile else 0,
                        "message": "You need at least 1 credit to run a simulation",
                    }
                ), 402

        if session_row:
            new_count = session_row.get("simulation_count", 0) + 1
            SupabaseDB.update_session(
                session_id,
                simulation_id=simulation_id,
                status="simulating",
                simulation_count=new_count,
            )

        profile = SupabaseDB.get_profile(g.user_id)
        user_plan = Config.normalize_plan(profile.get("plan", "free") if profile else "free")

        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id,
            user_plan=user_plan,
            time_config_patch=time_config_patch,
        )

        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)

        response_data = run_state.to_dict()
        if max_rounds:
            response_data["max_rounds_applied"] = max_rounds
        response_data["graph_memory_update_enabled"] = SimulationRunner._graph_memory_enabled.get(simulation_id, False)
        response_data["force_restarted"] = force_restarted
        if response_data["graph_memory_update_enabled"] and graph_id:
            response_data["graph_id"] = graph_id

        return jsonify({"success": True, "data": response_data})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except Exception as e:
        logger.error(f"Failed to start simulation: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/stop", methods=["POST"])
@require_auth
def stop_simulation():
    """
    Stop simulation

    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // required
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        run_state = SimulationRunner.stop_simulation(simulation_id)

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)

        return jsonify({"success": True, "data": run_state.to_dict()})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except Exception as e:
        logger.error(f"Failed to stop simulation: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Real-time Status Monitoring Endpoints ==============


@simulation_bp.route("/<simulation_id>/run-status", methods=["GET"])
@require_auth
def get_run_status(simulation_id: str):
    """
    Get simulation run real-time status (for frontend polling)

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)

        if not run_state:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "runner_status": "idle",
                        "current_round": 0,
                        "total_rounds": 0,
                        "progress_percent": 0,
                        "twitter_actions_count": 0,
                        "reddit_actions_count": 0,
                        "total_actions_count": 0,
                    },
                }
            )

        result = run_state.to_dict()

        if run_state.runner_status.value in ("completed", "failed"):
            _mark_session_completed_for_sim(simulation_id, run_state.runner_status.value)

        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Failed to get run status: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


def _mark_session_completed_for_sim(simulation_id: str, runner_status: str = "completed"):
    """If a session references this simulation, mark it completed or sim_failed (idempotent)."""
    session_status = "completed" if runner_status == "completed" else "sim_failed"
    try:
        resp = (
            SupabaseDB.client()
            .table("scenario_sessions")
            .update({"status": session_status})
            .eq("simulation_id", simulation_id)
            .eq("status", "simulating")
            .execute()
        )
        if resp.data:
            logger.info(f"Session marked {session_status} for simulation {simulation_id}")
    except Exception:
        logger.warning(f"Failed to mark session {session_status} for simulation {simulation_id}", exc_info=True)


@simulation_bp.route("/<simulation_id>/run-status/detail", methods=["GET"])
@require_auth
def get_run_status_detail(simulation_id: str):
    """
    Get detailed simulation run status (including all actions)

    Used for frontend real-time activity display

    Query parameters:
        platform: Filter by platform (twitter/reddit, optional)

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [...],
                "twitter_actions": [...],
                "reddit_actions": [...]
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get("platform")

        if not run_state:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "runner_status": "idle",
                        "all_actions": [],
                        "twitter_actions": [],
                        "reddit_actions": [],
                    },
                }
            )

        all_actions = SimulationRunner.get_all_actions(simulation_id=simulation_id, platform=platform_filter)

        twitter_actions = (
            SimulationRunner.get_all_actions(simulation_id=simulation_id, platform="twitter")
            if not platform_filter or platform_filter == "twitter"
            else []
        )

        reddit_actions = (
            SimulationRunner.get_all_actions(simulation_id=simulation_id, platform="reddit")
            if not platform_filter or platform_filter == "reddit"
            else []
        )

        current_round = run_state.current_round
        recent_actions = (
            SimulationRunner.get_all_actions(
                simulation_id=simulation_id, platform=platform_filter, round_num=current_round
            )
            if current_round > 0
            else []
        )

        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        result["recent_actions"] = [a.to_dict() for a in recent_actions]

        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Failed to get detailed status: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/<simulation_id>/actions", methods=["GET"])
@require_auth
def get_simulation_actions(simulation_id: str):
    """
    Get Agent action history from simulation

    Query parameters:
        limit: Result count (default 100)
        offset: Offset (default 0)
        platform: Filter by platform (twitter/reddit)
        agent_id: Filter by Agent ID
        round_num: Filter by round number

    Returns:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)
        platform = request.args.get("platform")
        agent_id = request.args.get("agent_id", type=int)
        round_num = request.args.get("round_num", type=int)

        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

        return jsonify({"success": True, "data": {"count": len(actions), "actions": [a.to_dict() for a in actions]}})

    except Exception as e:
        logger.error(f"Failed to get action history: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/<simulation_id>/timeline", methods=["GET"])
@require_auth
def get_simulation_timeline(simulation_id: str):
    """
    Get simulation timeline (summarized by round)

    Used for frontend progress bar and timeline view display

    Query parameters:
        start_round: Starting round (default 0)
        end_round: Ending round (default all)

    Returns per-round summary info
    """
    try:
        start_round = request.args.get("start_round", 0, type=int)
        end_round = request.args.get("end_round", type=int)

        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id, start_round=start_round, end_round=end_round
        )

        return jsonify({"success": True, "data": {"rounds_count": len(timeline), "timeline": timeline}})

    except Exception as e:
        logger.error(f"Failed to get timeline: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/<simulation_id>/agent-stats", methods=["GET"])
@require_auth
def get_agent_stats(simulation_id: str):
    """
    Get per-Agent statistics

    Used for frontend Agent activity ranking, action distribution, etc.
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)

        return jsonify({"success": True, "data": {"agents_count": len(stats), "stats": stats}})

    except Exception as e:
        logger.error(f"Failed to get Agent statistics: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Database Query Endpoints ==============


@simulation_bp.route("/<simulation_id>/posts", methods=["GET"])
@require_auth
def get_simulation_posts(simulation_id: str):
    """
    Get posts from simulation

    Query parameters:
        platform: Platform type (twitter/reddit)
        limit: Result count (default 50)
        offset: Offset

    Returns post list (read from SQLite database)
    """
    try:
        platform = request.args.get("platform", "reddit")
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        sim_dir = os.path.join(os.path.dirname(__file__), f"../../uploads/simulations/{simulation_id}")

        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)

        if not os.path.exists(db_path):
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "platform": platform,
                        "count": 0,
                        "posts": [],
                        "message": "Database does not exist, simulation may not have run yet",
                    },
                }
            )

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )

            posts = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]

        except sqlite3.OperationalError:
            posts = []
            total = 0

        conn.close()

        return jsonify(
            {"success": True, "data": {"platform": platform, "total": total, "count": len(posts), "posts": posts}}
        )

    except Exception as e:
        logger.error(f"Failed to get posts: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/<simulation_id>/comments", methods=["GET"])
@require_auth
def get_simulation_comments(simulation_id: str):
    """
    Get comments from simulation (Reddit only)

    Query parameters:
        post_id: Filter by post ID (optional)
        limit: Result count
        offset: Offset
    """
    try:
        post_id = request.args.get("post_id")
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        sim_dir = os.path.join(os.path.dirname(__file__), f"../../uploads/simulations/{simulation_id}")

        db_path = os.path.join(sim_dir, "reddit_simulation.db")

        if not os.path.exists(db_path):
            return jsonify({"success": True, "data": {"count": 0, "comments": []}})

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if post_id:
                cursor.execute(
                    """
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """,
                    (post_id, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """,
                    (limit, offset),
                )

            comments = [dict(row) for row in cursor.fetchall()]

        except sqlite3.OperationalError:
            comments = []

        conn.close()

        return jsonify({"success": True, "data": {"count": len(comments), "comments": comments}})

    except Exception as e:
        logger.error(f"Failed to get comments: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
