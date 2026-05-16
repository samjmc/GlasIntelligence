"""Deep research Celery task — runs in the celery-worker container, survives web server restarts."""

from datetime import datetime, UTC

from ..celery_app import celery_app
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger

logger = get_logger("glas.tasks.research")


@celery_app.task(
    bind=True,
    name="glas.deep_research",
    acks_late=True,
    max_retries=0,
    # Align with OpenAI client timeout (~45 min); complex geopolitical research often runs 30–40+ min
    soft_time_limit=2700,
    time_limit=2760,
)
def run_deep_research_task(
    self, session_id, prompt, user_id, angle_overrides=None, is_retry=False, scenario_context=None
):
    """Execute deep research for a scenario session.

    Writes all state to Supabase so the web server can poll without
    needing in-memory TaskManager access.
    """
    session = SupabaseDB.get_session(session_id)
    if not session:
        logger.warning(f"Session {session_id} not found — aborting research task")
        try:
            SupabaseDB.update_session(
                session_id,
                research_status="failed",
            )
        except Exception:
            logger.exception(
                "Failed to mark research_status failed for missing session %s",
                session_id,
            )
        return
    if session.get("research_status") == "completed":
        logger.info(f"Session {session_id}: research already completed, skipping")
        return

    try:
        logger.info(f"Session {session_id}: worker picked up research task, transitioning to processing")
        SupabaseDB.update_session(
            session_id,
            research_status="processing",
            status="researching",
        )

        if angle_overrides is not None and not isinstance(angle_overrides, dict):
            angle_overrides = None

        context = ""
        if scenario_context:
            context = scenario_context

        from ..config import Config

        if Config.DEEP_RESEARCH_ENABLED:
            from ..services.deep_research_agent import DeepResearchAgent
            agent = DeepResearchAgent()
        else:
            from ..services.llm_research_agent import LLMResearchAgent
            agent = LLMResearchAgent()

        dossier = agent.run(prompt, context=context, angle_overrides=angle_overrides)

        if dossier.get("error"):
            raise RuntimeError("Research agent returned error flag")

        # Guard against silent failures: agent occasionally returns a "successful"
        # response with no text content (final empty message item, refusal, etc.).
        # Treat that as a failure so the credit is refunded and the user can retry,
        # rather than persisting a useless dossier and showing "..." in the UI.
        if not (dossier.get("summary_md") or "").strip():
            raise RuntimeError("Research agent returned empty summary_md")

        SupabaseDB.update_session(
            session_id,
            research_status="completed",
            research_dossier=dossier,
            research_completed_at=datetime.now(UTC).isoformat(),
            status="research_complete",
        )
        logger.info(f"Session {session_id}: research completed successfully")

    except Exception:
        logger.exception(f"Session {session_id}: research failed")
        SupabaseDB.update_session(
            session_id,
            research_status="failed",
            status="active",
        )
        if not is_retry:
            SupabaseDB.refund_research_credit(user_id, f"Research failed — session {session_id}")
            logger.info(f"Session {session_id}: refunded research credit to {user_id}")
