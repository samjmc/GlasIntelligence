"""Shared helpers for simulation API routes (prep checks, interview prompt prefix)."""

from __future__ import annotations

from ..utils.logger import get_logger

logger = get_logger("glas.api.simulation")

INTERVIEW_PROMPT_PREFIX = (
    "Based on your persona, memories, and past actions, respond directly in text without using any tools: "
)


def optimize_interview_prompt(prompt: str) -> str:
    """Add prefix so interviewee agents answer in plain text without tool calls."""
    if not prompt:
        return prompt
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def required_prepared_files(simulation_dir: str) -> list[str]:
    """Files a prepared simulation must have: only the profile files of its enabled platforms.

    Runs are reddit only (twitter was dropped), so prepare no longer writes
    twitter_profiles.csv. Requiring it made every finished or failed simulation
    "not prepared": restart returned 400 and /prepare rebuilt all personas.
    """
    import json
    import os

    enable_reddit, enable_twitter = True, False
    try:
        with open(os.path.join(simulation_dir, "state.json"), encoding="utf-8") as f:
            state = json.load(f)
        enable_reddit = state.get("enable_reddit", True)
        enable_twitter = state.get("enable_twitter", False)
    except (OSError, ValueError):
        pass  # state.json missing or unreadable: the caller reports it as missing
    files = ["state.json", "simulation_config.json"]
    if enable_reddit:
        files.append("reddit_profiles.json")
    if enable_twitter:
        files.append("twitter_profiles.csv")
    return files


def check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Check if simulation preparation is complete.

    Returns:
        (is_prepared: bool, info: dict)
    """
    import json
    import os
    from datetime import datetime

    from ..config import Config

    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

    if not os.path.exists(simulation_dir):
        return False, {"reason": "Simulation directory not found"}

    required_files = required_prepared_files(simulation_dir)

    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)

    if missing_files:
        return False, {
            "reason": "Missing required files",
            "missing_files": missing_files,
            "existing_files": existing_files,
        }

    state_file = os.path.join(simulation_dir, "state.json")
    try:
        with open(state_file, encoding="utf-8") as f:
            state_data = json.load(f)

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)

        logger.debug(
            f"Checking simulation preparation status: {simulation_id}, status={status}, config_generated={config_generated}"
        )

        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")

            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, encoding="utf-8") as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, "w", encoding="utf-8") as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Auto-updated simulation status: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"Auto-update status failed: {e}")

            logger.info(
                f"Simulation {simulation_id} check result: preparation complete (status={status}, config_generated={config_generated})"
            )
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files,
            }
        else:
            logger.warning(
                f"Simulation {simulation_id} check result: preparation incomplete (status={status}, config_generated={config_generated})"
            )
            return False, {
                "reason": f"Status not in prepared list or config_generated is false: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated,
            }

    except Exception as e:
        return False, {"reason": f"Failed to read state file: {str(e)}"}
