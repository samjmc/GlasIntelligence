"""Interview, env status, follow-up suggestions, and reminder routes for simulation API."""

import json
import re
import traceback

from flask import g, jsonify, request

from . import simulation_bp
from .simulation_helpers import optimize_interview_prompt
from ..middleware.auth import require_auth
from ..models.project import ProjectManager
from ..services import offline_interview
from ..services.offline_interview import SimulationNotFoundError
from ..services.report_agent import ReportManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..services.supabase_client import SupabaseDB
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("glas.api.simulation")


# ============== Interview Endpoints ==============


@simulation_bp.route("/interview", methods=["POST"])
@require_auth
def interview_agent():
    """
    Interview a single Agent

    Works for any simulation whose directory still exists. While the OASIS process is
    alive (wait-for-command mode) the live agent answers over IPC ("mode": "live");
    once it has exited the agent is rebuilt from the recorded run ("mode": "reconstructed").
    See services/offline_interview.py.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // required
            "agent_id": 0,                     // required, Agent ID
            "prompt": "What do you think about this?",  // required, interview question
            "platform": "twitter",             // optional, specify platform (twitter/reddit)
                                               // when not specified: dual-platform simulation interviews both platforms
            "timeout": 60                      // optional, timeout in seconds, default 60
        }

    Returns (no platform specified, dual-platform mode):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "What do you think about this?",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    Returns (platform specified):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "What do you think about this?",
                "result": {
                    "agent_id": 0,
                    "response": "I think...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        agent_id = data.get("agent_id")
        prompt = data.get("prompt")
        platform = data.get("platform")
        timeout = data.get("timeout", 60)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        if agent_id is None:
            return jsonify({"success": False, "error": "Please provide agent_id"}), 400

        if not prompt:
            return jsonify({"success": False, "error": "Please provide prompt (interview question)"}), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify({"success": False, "error": "platform parameter must be 'twitter' or 'reddit'"}), 400

        optimized_prompt = optimize_interview_prompt(prompt)

        result = offline_interview.interview_single(
            simulation_id=simulation_id, agent_id=agent_id, prompt=optimized_prompt, platform=platform, timeout=timeout
        )

        return jsonify({"success": result.get("success", False), "data": result})

    except SimulationNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except TimeoutError as e:
        return jsonify({"success": False, "error": f"Interview response timed out: {str(e)}"}), 504

    except Exception as e:
        logger.error(f"Interview failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/interview/batch", methods=["POST"])
@require_auth
def interview_agents_batch():
    """
    Batch interview multiple Agents

    Live over IPC while the OASIS process is alive, otherwise reconstructed from the
    recorded run; ``data.mode`` says which ("live" | "reconstructed").

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // required
            "interviews": [                    // required, interview list
                {
                    "agent_id": 0,
                    "prompt": "What do you think about A?",
                    "platform": "twitter"      // optional, specify platform for this Agent
                },
                {
                    "agent_id": 1,
                    "prompt": "What do you think about B?"  // no platform uses default
                }
            ],
            "platform": "reddit",              // optional, default platform (overridden by per-item platform)
                                               // when not specified: dual-platform simulation interviews each Agent on both platforms
            "timeout": 120                     // optional, timeout in seconds, default 120
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        interviews = data.get("interviews")
        platform = data.get("platform")
        timeout = data.get("timeout", 120)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({"success": False, "error": "Please provide interviews (interview list)"}), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify({"success": False, "error": "platform parameter must be 'twitter' or 'reddit'"}), 400

        for i, interview in enumerate(interviews):
            if "agent_id" not in interview:
                return jsonify({"success": False, "error": f"Interview list item {i + 1} missing agent_id"}), 400
            if "prompt" not in interview:
                return jsonify({"success": False, "error": f"Interview list item {i + 1} missing prompt"}), 400
            item_platform = interview.get("platform")
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify(
                    {"success": False, "error": f"Interview list item {i + 1} platform must be 'twitter' or 'reddit'"}
                ), 400

        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview["prompt"] = optimize_interview_prompt(interview.get("prompt", ""))
            optimized_interviews.append(optimized_interview)

        result = offline_interview.interview_batch(
            simulation_id=simulation_id, interviews=optimized_interviews, platform=platform, timeout=timeout
        )

        return jsonify({"success": result.get("success", False), "data": result})

    except SimulationNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except TimeoutError as e:
        return jsonify({"success": False, "error": f"Batch interview response timed out: {str(e)}"}), 504

    except Exception as e:
        logger.error(f"Batch interview failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/interview/all", methods=["POST"])
@require_auth
def interview_all_agents():
    """
    Global interview - Interview all Agents with the same question

    Live over IPC while the OASIS process is alive, otherwise reconstructed from the
    recorded run; ``data.mode`` says which ("live" | "reconstructed").

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",            // required
            "prompt": "What is your overall view on this?",  // required, interview question (same for all Agents)
            "platform": "reddit",                   // optional, specify platform (twitter/reddit)
                                                    // when not specified: dual-platform simulation interviews each Agent on both platforms
            "timeout": 180                          // optional, timeout in seconds, default 180
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        prompt = data.get("prompt")
        platform = data.get("platform")
        timeout = data.get("timeout", 180)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        if not prompt:
            return jsonify({"success": False, "error": "Please provide prompt (interview question)"}), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify({"success": False, "error": "platform parameter must be 'twitter' or 'reddit'"}), 400

        optimized_prompt = optimize_interview_prompt(prompt)

        result = offline_interview.interview_all(
            simulation_id=simulation_id, prompt=optimized_prompt, platform=platform, timeout=timeout
        )

        return jsonify({"success": result.get("success", False), "data": result})

    except SimulationNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except TimeoutError as e:
        return jsonify({"success": False, "error": f"Global interview response timed out: {str(e)}"}), 504

    except Exception as e:
        logger.error(f"Global interview failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/interview/history", methods=["POST"])
@require_auth
def get_interview_history():
    """
    Get interview history records

    Reads all interview records from simulation database

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // required
            "platform": "reddit",          // optional, platform type (reddit/twitter)
                                           // when not specified, returns history from both platforms
            "agent_id": 0,                 // optional, only get history for this Agent
            "limit": 100                   // optional, result count, default 100
        }

    Returns:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "I think...",
                        "prompt": "What do you think about this?",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        platform = data.get("platform")
        agent_id = data.get("agent_id")
        limit = data.get("limit", 100)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id, platform=platform, agent_id=agent_id, limit=limit
        )

        return jsonify({"success": True, "data": {"count": len(history), "history": history}})

    except Exception as e:
        logger.error(f"Failed to get interview history: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/env-status", methods=["POST"])
@require_auth
def get_env_status():
    """
    Get simulation environment status

    Check if simulation environment is alive (can receive Interview commands)

    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // required
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "interview_available": true,         // interviews can be answered right now
                "interview_mode": "live",            // "live" | "reconstructed" | null
                "message": "Environment is running, ready to receive Interview commands"
            }
        }

    ``env_alive`` / ``twitter_available`` / ``reddit_available`` keep their old meaning (the
    OASIS process); ``interview_available`` is what a caller should gate interviews on.
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        interview = offline_interview.interview_status(simulation_id)
        env_alive = interview["interview_mode"] == offline_interview.InterviewMode.LIVE

        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "Environment is running, ready to receive Interview commands"
        elif interview["interview_available"]:
            message = "Environment has closed; interviews are answered from the recorded run"
        else:
            message = "Environment is not running or has been closed"

        return jsonify(
            {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "env_alive": env_alive,
                    "twitter_available": env_status.get("twitter_available", False),
                    "reddit_available": env_status.get("reddit_available", False),
                    "interview_available": interview["interview_available"],
                    "interview_mode": interview["interview_mode"],
                    "message": message,
                },
            }
        )

    except Exception as e:
        logger.error(f"Failed to get environment status: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/close-env", methods=["POST"])
@require_auth
def close_simulation_env():
    """
    Close simulation environment

    Sends a close-environment command to the simulation for graceful exit from wait-for-command mode.

    Note: This differs from /stop. /stop forcefully terminates the process,
    while this endpoint lets the simulation gracefully close the environment and exit.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // required
            "timeout": 30                  // optional, timeout in seconds, default 30
        }

    Returns:
        {
            "success": true,
            "data": {
                "message": "Environment close command sent",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        timeout = data.get("timeout", 30)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        result = SimulationRunner.close_simulation_env(simulation_id=simulation_id, timeout=timeout)

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)

        return jsonify({"success": result.get("success", False), "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except Exception as e:
        logger.error(f"Failed to close environment: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Follow-Up Suggestions ==============
