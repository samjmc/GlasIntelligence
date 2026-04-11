"""Source materials agent — suggests documents and generates research briefings."""

import json
import re
import threading

from flask import Blueprint, request, jsonify, g
from openai import OpenAI
from ..middleware.auth import require_auth, optional_auth
from ..services.supabase_client import SupabaseDB
from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

source_agent_bp = Blueprint('source_agent', __name__)
logger = get_logger('glas.source_agent')

SUGGEST_SYSTEM_PROMPT = """You are a research analyst for Glas Intelligence, a scenario simulation platform.
The user will describe a scenario they want to simulate. Your job is to suggest 3-5 specific source documents
they should gather to feed into the simulation engine.

For each suggestion, provide:
- title: A specific document name (e.g. "Ofgem Price Cap Q4 2025 Decision Letter")
- why: One sentence on why this document is relevant to the simulation
- where: Where to find it (specific URL or organization)
- type: One of "regulatory", "market_data", "news", "academic", "internal"

Respond in JSON format: { "suggestions": [ { "title": "...", "why": "...", "where": "...", "type": "..." } ] }
Be specific and actionable. Reference real organizations and sources when possible."""

RESEARCH_SYSTEM_PROMPT = """You are a senior research analyst preparing a briefing document for a scenario simulation.
The user will describe a scenario. You must produce a comprehensive markdown briefing covering:

1. **Background & Context** — What is this scenario about? Key facts and recent developments.
2. **Key Stakeholders** — Who are the major players? What are their positions and interests?
3. **Current State** — What is the status quo? Key data points, regulations, market conditions.
4. **Scenario Variables** — What could change? What are the key decision points?
5. **Historical Precedents** — Similar situations that have played out before.

Write 800-1200 words. Use specific names, dates, and figures where possible.
This briefing will be fed into a multi-agent simulation engine, so focus on information that helps
model stakeholder behavior and reactions."""


def _get_llm_client():
    if not Config.LLM_API_KEY:
        return None
    return OpenAI(api_key=Config.LLM_API_KEY, base_url=Config.LLM_BASE_URL)


@source_agent_bp.route('/suggest-sources', methods=['POST'])
@optional_auth
def suggest_sources():
    """Suggest source documents for a given scenario. Available to all users."""
    client = _get_llm_client()
    if not client:
        return jsonify({"success": False, "error": "LLM not configured"}), 503

    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()

    if not prompt or len(prompt) < 10:
        return jsonify({"success": False, "error": "Please describe your scenario in more detail"}), 400

    try:
        response = client.chat.completions.create(
            model=Config.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SUGGEST_SYSTEM_PROMPT},
                {"role": "user", "content": f"Scenario: {prompt}"},
            ],
            temperature=0.7,
            max_tokens=800,
            response_format={"type": "json_object"},
        )

        if not response.choices:
            return jsonify({"success": False, "error": "No response from LLM"}), 502
        result = json.loads(response.choices[0].message.content)
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"suggest-sources failed: {e}")
        return jsonify({"success": False, "error": "Failed to analyze scenario"}), 500


@source_agent_bp.route('/auto-research', methods=['POST'])
@require_auth
def auto_research():
    """Generate a research briefing. Requires auth + paid plan (does not deduct credits)."""
    profile = SupabaseDB.get_profile(g.user_id)
    plan = Config.normalize_plan(profile.get('plan', 'free') if profile else 'free')

    if plan == 'free':
        return jsonify({
            "success": False,
            "error": "Auto-research requires a Pro or Business subscription",
        }), 403

    client = _get_llm_client()
    if not client:
        return jsonify({"success": False, "error": "LLM not configured"}), 503

    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()

    if not prompt or len(prompt) < 10:
        return jsonify({"success": False, "error": "Please describe your scenario in more detail"}), 400

    try:
        response = client.chat.completions.create(
            model=Config.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                {"role": "user", "content": f"Prepare a research briefing for this scenario: {prompt}"},
            ],
            temperature=0.5,
            max_tokens=2500,
        )

        if not response.choices:
            return jsonify({"success": False, "error": "No response from LLM"}), 502
        content_md = response.choices[0].message.content
        safe_title = re.sub(r'[^\w\-]', '_', prompt[:60])
        filename = f"briefing_{safe_title}.md"

        return jsonify({
            "success": True,
            "data": {
                "title": f"Research Briefing: {prompt[:80]}",
                "content_md": content_md,
                "filename": filename,
            },
        })

    except Exception as e:
        logger.error(f"auto-research failed: {e}")
        return jsonify({"success": False, "error": "Failed to generate briefing"}), 500


# ============== Deep Research (OpenAI Responses API) ==============

@source_agent_bp.route('/deep-research', methods=['POST'])
@require_auth
def start_deep_research():
    """Launch deep research as a background task. Requires auth + paid plan."""
    if not Config.DEEP_RESEARCH_ENABLED:
        return jsonify({"success": False, "error": "Deep research is not enabled"}), 403

    profile = SupabaseDB.get_profile(g.user_id)
    plan = Config.normalize_plan(profile.get('plan', 'free') if profile else 'free')
    if plan == 'free':
        return jsonify({
            "success": False,
            "error": "Deep research requires a Pro or Business subscription",
        }), 403

    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt or len(prompt) < 10:
        return jsonify({"success": False, "error": "Please describe your scenario in more detail"}), 400

    tm = TaskManager()
    task_id = tm.create_task("deep_research")
    tm.update_task(task_id, status=TaskStatus.PROCESSING, message="Starting deep research...")

    def _run():
        try:
            tm.update_task(task_id, message="Research in progress...")
            from ..services.deep_research_agent import DeepResearchAgent
            agent = DeepResearchAgent()
            dossier = agent.run(prompt)
            tm.complete_task(task_id, dossier)
        except Exception as exc:
            logger.exception("Deep research background task failed")
            tm.fail_task(task_id, "Deep research failed. Please try again.")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"success": True, "data": {"task_id": task_id}})


@source_agent_bp.route('/deep-research/status/<task_id>', methods=['GET'])
@require_auth
def deep_research_status(task_id):
    """Poll deep research task status."""
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": "Task not found"}), 404
    return jsonify({"success": True, "data": task.to_dict()})


@source_agent_bp.route('/deep-research/result/<task_id>', methods=['GET'])
@require_auth
def deep_research_result(task_id):
    """Retrieve completed deep research dossier."""
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": "Task not found"}), 404
    if task.status != TaskStatus.COMPLETED:
        return jsonify({"success": False, "error": f"Task not complete (status: {task.status.value})"}), 400
    return jsonify({"success": True, "data": task.result})
