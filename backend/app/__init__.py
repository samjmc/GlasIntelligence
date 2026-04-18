"""
Glas Intelligence Backend - Flask application factory
"""

import os
import warnings

warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def _init_sentry(app):
    """Initialize Sentry error tracking if DSN is configured."""
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration(), CeleryIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            send_default_pii=False,
        )
    except ImportError:
        pass


def _init_prometheus(app):
    """Initialize Prometheus metrics endpoint at /api/metrics."""
    if os.environ.get("ENABLE_PROMETHEUS", "").lower() not in ("1", "true", "yes"):
        return
    try:
        from prometheus_flask_exporter import PrometheusMetrics

        PrometheusMetrics(app, path="/api/metrics")
    except ImportError:
        pass


def create_app(config_class=Config):
    """Flask application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
        app.json.ensure_ascii = False

    _init_sentry(app)

    logger = setup_logger("glas")

    is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    debug_mode = app.config.get("DEBUG", False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("Glas Intelligence Backend starting...")
        logger.info("=" * 50)

    # Enable CORS
    allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    CORS(app, resources={r"/api/*": {"origins": [o.strip() for o in allowed_origins]}})

    from .middleware.auth import extract_user_from_request

    app.before_request(extract_user_from_request)

    # Register simulation process cleanup (ensure all simulation processes are terminated on server shutdown)
    from .services.simulation_runner import SimulationRunner

    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup registered")

    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger("glas.request")
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and "json" in request.content_type:
            logger.debug(f"Request body: {request.get_json(silent=True)}")

    @app.after_request
    def log_response(response):
        logger = get_logger("glas.request")
        logger.debug(f"Response: {response.status_code}")
        return response

    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp

    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    app.register_blueprint(report_bp, url_prefix="/api/report")

    from .api.billing import billing_bp

    app.register_blueprint(billing_bp, url_prefix="/api/billing")

    from .api.bundle import bundle_bp

    app.register_blueprint(bundle_bp, url_prefix="/api/bundle")

    from .api.feed import feed_bp

    app.register_blueprint(feed_bp, url_prefix="/api/feed")

    from .api.dashboard import dashboard_bp

    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")

    from .api.source_agent import source_agent_bp

    app.register_blueprint(source_agent_bp, url_prefix="/api/source")

    from .api.session import session_bp

    app.register_blueprint(session_bp, url_prefix="/api/session")

    _init_prometheus(app)

    @app.route("/health")
    def health():
        return {
            "status": "ok",
            "service": "Glas Intelligence Backend",
            "cors_locked": os.environ.get("CORS_ORIGINS", "*") != "*",
        }

    _recover_orphaned_research(logger)
    _sweep_stale_simulating_sessions(logger)

    if should_log_startup:
        logger.info("Glas Intelligence Backend startup complete")

    return app


def _recover_orphaned_research(logger):
    """Re-queue any sessions stuck in 'processing' or 'claiming' from a previous crash or deploy."""
    try:
        from .services.supabase_client import SupabaseDB
        from .tasks.research_tasks import run_deep_research_task
        from celery.result import AsyncResult

        rows = (
            SupabaseDB.client()
            .table("scenario_sessions")
            .select("id,user_id,prompt,research_task_id,research_angles,research_status")
            .in_("research_status", ["processing", "claiming"])
            .execute()
        )
        if not rows.data:
            return

        for session in rows.data:
            rs = session.get("research_status")

            if rs == "claiming":
                logger.info(f"Recovery: session {session['id']} stuck in 'claiming', marking failed")
                SupabaseDB.update_session(session["id"], research_status="failed", status="active")
                continue

            old_task_id = session.get("research_task_id")
            if old_task_id:
                state = AsyncResult(old_task_id).state
                if state in ("STARTED", "RETRY"):
                    logger.info(f"Recovery: session {session['id']} has active Celery task {old_task_id} ({state}), skipping")
                    continue

            logger.info(f"Recovery: re-queuing research for session {session['id']}")
            run_deep_research_task.delay(
                session["id"],
                session["prompt"],
                session["user_id"],
                angle_overrides=session.get("research_angles") or None,
                is_retry=True,
            )
    except Exception:
        logger.warning("Startup research recovery failed", exc_info=True)


STALE_SIMULATING_HOURS = 4


def _sweep_stale_simulating_sessions(logger):
    """Mark sessions stuck in 'simulating' for too long as 'sim_failed'."""
    try:
        from datetime import datetime, UTC, timedelta
        from .services.supabase_client import SupabaseDB

        cutoff = (datetime.now(UTC) - timedelta(hours=STALE_SIMULATING_HOURS)).isoformat()
        resp = (
            SupabaseDB.client()
            .table("scenario_sessions")
            .update({"status": "sim_failed"})
            .eq("status", "simulating")
            .lt("updated_at", cutoff)
            .execute()
        )
        if resp.data:
            logger.info(f"Swept {len(resp.data)} stale simulating session(s) to sim_failed")
    except Exception:
        logger.warning("Stale simulating session sweep failed", exc_info=True)
