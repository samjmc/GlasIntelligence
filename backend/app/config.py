"""
Configuration management
Load configuration from .env file in project root
"""

import logging
import os

from dotenv import load_dotenv

# Stdlib bootstrap: warnings during `class Config` body run before module end. Replaced with
# get_logger("glas.config") at EOF (safe once Config exists; avoids cycle with top-of-file utils import).
_log = logging.getLogger("glas.config")


def _safe_int(val, default: int, *, env_key: str | None = None) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        if env_key is not None:
            _log.warning(
                "Config env %s has invalid value %r; using default %s",
                env_key,
                val,
                default,
            )
        return default


def _safe_float(val, default: float, *, env_key: str | None = None) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        if env_key is not None:
            _log.warning(
                "Config env %s has invalid value %r; using default %s",
                env_key,
                val,
                default,
            )
        return default


# Load .env file from project root
# Path: .env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), "../../.env")

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=False)
else:
    load_dotenv(override=False)


class Config:
    """Flask configuration class"""

    # Flask config
    SECRET_KEY = os.environ.get("SECRET_KEY", "glas-intelligence-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() == "true"

    # JSON config - disable ASCII escape so non-ASCII displays directly (not as \uXXXX)
    JSON_AS_ASCII = False

    # LLM config (unified OpenAI format)
    LLM_API_KEY = os.environ.get("LLM_API_KEY")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")

    # Supabase config
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

    # Stripe config
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_PAYG = os.environ.get("STRIPE_PRICE_PAYG", "")
    STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")
    STRIPE_PRICE_BUSINESS = os.environ.get("STRIPE_PRICE_BUSINESS", "")
    STRIPE_PRICE_PACK_5 = os.environ.get("STRIPE_PRICE_PACK_5", "")
    STRIPE_PRICE_PACK_10 = os.environ.get("STRIPE_PRICE_PACK_10", "")
    STRIPE_PRICE_OVERAGE_PRO = os.environ.get("STRIPE_PRICE_OVERAGE_PRO", "")
    STRIPE_PRICE_OVERAGE_BUSINESS = os.environ.get("STRIPE_PRICE_OVERAGE_BUSINESS", "")
    STRIPE_PRICE_RESEARCH_1 = os.environ.get("STRIPE_PRICE_RESEARCH_1", "")
    STRIPE_PRICE_RESEARCH_5 = os.environ.get("STRIPE_PRICE_RESEARCH_5", "")
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    # Resend email config
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@glasinsight.com")

    # Knowledge-graph backend: "zep" (default) or "fake" (in memory, tests only).
    # See app/services/graph_store.
    GRAPH_BACKEND = os.environ.get("GRAPH_BACKEND", "zep")

    # Zep config
    ZEP_API_KEY = os.environ.get("ZEP_API_KEY")
    ZEP_GRAPH_MEMORY_BATCH_SIZE = _safe_int(
        os.environ.get("ZEP_GRAPH_MEMORY_BATCH_SIZE", "5"),
        5,
        env_key="ZEP_GRAPH_MEMORY_BATCH_SIZE",
    )
    ZEP_GRAPH_MEMORY_SEND_INTERVAL_SEC = _safe_float(
        os.environ.get("ZEP_GRAPH_MEMORY_SEND_INTERVAL_SEC", "0.5"),
        0.5,
        env_key="ZEP_GRAPH_MEMORY_SEND_INTERVAL_SEC",
    )

    # Graph snapshot cache (filesystem under uploads/graph_cache/) — cuts Zep list API usage
    GRAPH_SNAPSHOT_CACHE_ENABLED = os.environ.get("GRAPH_SNAPSHOT_CACHE_ENABLED", "1").lower() in (
        "1",
        "true",
        "yes",
    )
    # 7 days: mutation-generation bumps are the primary invalidation; the TTL is
    # only a time-based safety net, and every miss is a paid Zep read (5106829).
    GRAPH_SNAPSHOT_TTL_SECONDS = _safe_int(
        os.environ.get("GRAPH_SNAPSHOT_TTL_SECONDS", "604800"),
        604800,
        env_key="GRAPH_SNAPSHOT_TTL_SECONDS",
    )
    GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS = _safe_int(
        os.environ.get("GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS", "604800"),
        604800,
        env_key="GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS",
    )
    GRAPH_SNAPSHOT_MAX_DISK_MB = _safe_int(
        os.environ.get("GRAPH_SNAPSHOT_MAX_DISK_MB", "512"),
        512,
        env_key="GRAPH_SNAPSHOT_MAX_DISK_MB",
    )
    GRAPH_SNAPSHOT_SINGLEFLIGHT = os.environ.get("GRAPH_SNAPSHOT_SINGLEFLIGHT", "1").lower() in (
        "1",
        "true",
        "yes",
    )

    # File upload config
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    # Text processing config
    DEFAULT_CHUNK_SIZE = 300  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 30  # Default overlap size
    DEFAULT_TARGET_ENTITIES = _safe_int(
        os.environ.get("DEFAULT_TARGET_ENTITIES", "50"),
        50,
        env_key="DEFAULT_TARGET_ENTITIES",
    )
    MAX_ENRICHMENT_ROUNDS = _safe_int(
        os.environ.get("MAX_ENRICHMENT_ROUNDS", "3"),
        3,
        env_key="MAX_ENRICHMENT_ROUNDS",
    )

    # OASIS simulation config
    OASIS_DEFAULT_MAX_ROUNDS = _safe_int(
        os.environ.get("OASIS_DEFAULT_MAX_ROUNDS", "10"),
        10,
        env_key="OASIS_DEFAULT_MAX_ROUNDS",
    )
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), "../uploads/simulations")

    # OASIS platform available actions config
    OASIS_TWITTER_ACTIONS = ["CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST"]
    OASIS_REDDIT_ACTIONS = [
        "LIKE_POST",
        "DISLIKE_POST",
        "CREATE_POST",
        "CREATE_COMMENT",
        "LIKE_COMMENT",
        "DISLIKE_COMMENT",
        "SEARCH_POSTS",
        "SEARCH_USER",
        "TREND",
        "REFRESH",
        "DO_NOTHING",
        "FOLLOW",
        "MUTE",
    ]

    # Agent tools config
    ENABLE_AGENT_TOOLS = os.environ.get("ENABLE_AGENT_TOOLS", "true").lower() in ("1", "true", "yes")
    AGENT_TOOLS_MAX_ITERATIONS = _safe_int(
        os.environ.get("AGENT_TOOLS_MAX_ITERATIONS", "3"),
        3,
        env_key="AGENT_TOOLS_MAX_ITERATIONS",
    )

    # Simulation cost caps per plan
    FREE_SIMULATION_AGENTS = _safe_int(
        os.environ.get("FREE_SIMULATION_AGENTS", "25"),
        25,
        env_key="FREE_SIMULATION_AGENTS",
    )
    FREE_SIMULATION_ROUNDS = _safe_int(
        os.environ.get("FREE_SIMULATION_ROUNDS", "15"),
        15,
        env_key="FREE_SIMULATION_ROUNDS",
    )
    PRO_SIMULATION_AGENTS = _safe_int(
        os.environ.get("PRO_SIMULATION_AGENTS", "50"),
        50,
        env_key="PRO_SIMULATION_AGENTS",
    )
    PRO_SIMULATION_ROUNDS = _safe_int(
        os.environ.get("PRO_SIMULATION_ROUNDS", "25"),
        25,
        env_key="PRO_SIMULATION_ROUNDS",
    )
    BUSINESS_SIMULATION_AGENTS = _safe_int(
        os.environ.get("BUSINESS_SIMULATION_AGENTS", "75"),
        75,
        env_key="BUSINESS_SIMULATION_AGENTS",
    )
    BUSINESS_SIMULATION_ROUNDS = _safe_int(
        os.environ.get("BUSINESS_SIMULATION_ROUNDS", "30"),
        30,
        env_key="BUSINESS_SIMULATION_ROUNDS",
    )
    ENTERPRISE_SIMULATION_AGENTS = _safe_int(
        os.environ.get("ENTERPRISE_SIMULATION_AGENTS", "200"),
        200,
        env_key="ENTERPRISE_SIMULATION_AGENTS",
    )
    ENTERPRISE_SIMULATION_ROUNDS = _safe_int(
        os.environ.get("ENTERPRISE_SIMULATION_ROUNDS", "50"),
        50,
        env_key="ENTERPRISE_SIMULATION_ROUNDS",
    )

    @classmethod
    def normalize_plan(cls, plan: str | None) -> str:
        """Lowercase/strip profiles.plan for comparisons (e.g. 'Enterprise' stored in Supabase)."""
        if plan is None:
            return "free"
        p = str(plan).strip().lower()
        if p in ("", "null", "none", "undefined"):
            return "free"
        return p

    @classmethod
    def simulation_limits(cls, plan: str | None) -> tuple:
        """Return (max_agents, max_rounds) for a given plan."""
        plan = cls.normalize_plan(plan)
        if plan in ("free", "payg"):
            return cls.FREE_SIMULATION_AGENTS, cls.FREE_SIMULATION_ROUNDS
        if plan == "business":
            return cls.BUSINESS_SIMULATION_AGENTS, cls.BUSINESS_SIMULATION_ROUNDS
        if plan == "enterprise":
            return cls.ENTERPRISE_SIMULATION_AGENTS, cls.ENTERPRISE_SIMULATION_ROUNDS
        return cls.PRO_SIMULATION_AGENTS, cls.PRO_SIMULATION_ROUNDS

    # Report Agent config
    REPORT_AGENT_MAX_TOOL_CALLS = _safe_int(
        os.environ.get("REPORT_AGENT_MAX_TOOL_CALLS", "5"),
        5,
        env_key="REPORT_AGENT_MAX_TOOL_CALLS",
    )
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = _safe_int(
        os.environ.get("REPORT_AGENT_MAX_REFLECTION_ROUNDS", "2"),
        2,
        env_key="REPORT_AGENT_MAX_REFLECTION_ROUNDS",
    )
    REPORT_AGENT_TEMPERATURE = _safe_float(
        os.environ.get("REPORT_AGENT_TEMPERATURE", "0.5"),
        0.5,
        env_key="REPORT_AGENT_TEMPERATURE",
    )

    # Valued-output report payload v1 + grounding (domain-agnostic)
    ENABLE_REPORT_PAYLOAD_V1 = os.environ.get("ENABLE_REPORT_PAYLOAD_V1", "true").lower() in ("1", "true", "yes")
    ENABLE_GROUNDING_FEATURES = os.environ.get("ENABLE_GROUNDING_FEATURES", "true").lower() in ("1", "true", "yes")
    GROUNDING_MAX_AGE_HOURS = _safe_float(
        os.environ.get("GROUNDING_MAX_AGE_HOURS", "168"),
        168.0,
        env_key="GROUNDING_MAX_AGE_HOURS",
    )  # 7 days default
    GROUNDING_BLOCK_IF_STALE = os.environ.get("GROUNDING_BLOCK_IF_STALE", "false").lower() in ("1", "true", "yes")
    GROUNDING_WARN_IF_STALE = os.environ.get("GROUNDING_WARN_IF_STALE", "true").lower() in ("1", "true", "yes")
    ENABLE_WEB_ENRICHER = os.environ.get("ENABLE_WEB_ENRICHER", "false").lower() in ("1", "true", "yes")

    # Deep Research (OpenAI Responses API)
    DEEP_RESEARCH_ENABLED = os.environ.get("DEEP_RESEARCH_ENABLED", "false").lower() in ("1", "true", "yes")
    DEEP_RESEARCH_MODEL = os.environ.get("DEEP_RESEARCH_MODEL", "o4-mini-deep-research")
    DEEP_RESEARCH_MAX_TOOL_CALLS = _safe_int(
        os.environ.get("DEEP_RESEARCH_MAX_TOOL_CALLS", "50"),
        50,
        env_key="DEEP_RESEARCH_MAX_TOOL_CALLS",
    )
    # Deep research models burn output tokens on internal reasoning + tool calls
    # before emitting the final report. The system prompt asks for up to 15k words
    # (~20-30k tokens) on top of that.
    #
    # Tuning history:
    # - 16000: too low, model hit the cap mid-reasoning and returned empty dossiers (PR #14).
    # - 100000: solved the empty-dossier issue but blew the OpenAI org TPM budget.
    #   OpenAI charges (input + max_output_tokens) against the per-minute token
    #   limit AT REQUEST TIME, regardless of actual usage. With Tier 1's 200k TPM,
    #   each 100k-output request reserved over half the budget, and 2 concurrent
    #   attempts (or one in-flight + one retry) triggered persistent 429s.
    # - 50000 (current): comfortably fits a 15k-word (~22k token) report plus
    #   reasoning headroom, while letting 3 concurrent requests fit in 200k TPM.
    DEEP_RESEARCH_MAX_OUTPUT_TOKENS = _safe_int(
        os.environ.get("DEEP_RESEARCH_MAX_OUTPUT_TOKENS", "50000"),
        50000,
        env_key="DEEP_RESEARCH_MAX_OUTPUT_TOKENS",
    )
    RESEARCH_CLASSIFICATION_MODEL = os.environ.get("RESEARCH_CLASSIFICATION_MODEL", "gpt-4o-mini")

    # Tavily Search Research (iterative search + LLM refinement)
    TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
    # Entity knowledge-expansion: an LLM pass names additional real
    # stakeholders beyond the research text, each verified by a live Tavily
    # search before entering the graph (see services/entity_expansion.py).
    ENTITY_EXPANSION_ENABLED = os.environ.get("ENTITY_EXPANSION_ENABLED", "true").lower() in ("1", "true", "yes")
    ENTITY_EXPANSION_TARGET = _safe_int(
        os.environ.get("ENTITY_EXPANSION_TARGET", "20"),
        20,
        env_key="ENTITY_EXPANSION_TARGET",
    )
    # Directly materialize verified inventory entities as graph nodes via Zep's
    # add_nodes API (instead of relying solely on NER extraction from episodes,
    # which misses organisation names — see services/graph_enrichment_service.py).
    GRAPH_MATERIALIZE_INVENTORY_ENABLED = os.environ.get("GRAPH_MATERIALIZE_INVENTORY_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    SEARCH_RESEARCH_ENABLED = bool(TAVILY_API_KEY)
    # Model for the search-research chain (query gen, synthesis, critique,
    # verification). Defaults to the general LLM model; for Claude runs set it
    # explicitly (e.g. claude-sonnet-5).
    SEARCH_RESEARCH_MODEL = os.environ.get("SEARCH_RESEARCH_MODEL") or os.environ.get("LLM_MODEL_NAME") or "gpt-4o-mini"
    SEARCH_RESEARCH_MAX_ROUNDS = _safe_int(
        os.environ.get("SEARCH_RESEARCH_MAX_ROUNDS", "3"),
        3,
        env_key="SEARCH_RESEARCH_MAX_ROUNDS",
    )
    SEARCH_RESEARCH_QUALITY_THRESHOLD = _safe_float(
        os.environ.get("SEARCH_RESEARCH_QUALITY_THRESHOLD", "7.5"),
        7.5,
        env_key="SEARCH_RESEARCH_QUALITY_THRESHOLD",
    )

    # Decision layer
    ENABLE_DECISION_LAYER = os.environ.get("ENABLE_DECISION_LAYER", "false").lower() in ("1", "true", "yes")

    # Probability guardrails (post-LLM caps / ordering for estimate_risks)
    ENABLE_CALIBRATION_GUARDRAILS = os.environ.get("ENABLE_CALIBRATION_GUARDRAILS", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Correlation discount heuristic: average pairwise correlation assumed when
    # combining likelihood ratios without a correlation matrix (default 0.5,
    # no formal derivation; preserved for behavioral compatibility).
    CORRELATION_DEFAULT_AVG_CORRELATION = _safe_float(
        os.environ.get("CORRELATION_DEFAULT_AVG_CORRELATION", "0.5"),
        0.5,
        env_key="CORRELATION_DEFAULT_AVG_CORRELATION",
    )

    # Jev (TypeSafe System One): typed classification / scoring with calibrated
    # confidence, used as a fast path in front of the LLM for bounded decisions
    # (agent tool roles, stance classification, risk likelihood/impact). Off by
    # default; when off or unconfigured every caller keeps its LLM path
    # unchanged. Reach it via TypeSafe direct, Cloudflare Workers AI or Vercel
    # AI Gateway — see utils/jev_client.py.
    JEV_ENABLED = os.environ.get("JEV_ENABLED", "false").lower() in ("1", "true", "yes")
    JEV_PROVIDER = os.environ.get("JEV_PROVIDER", "typesafe").lower()  # typesafe | cloudflare | vercel
    JEV_API_KEY = os.environ.get("JEV_API_KEY", "")
    JEV_MODEL = os.environ.get("JEV_MODEL", "")  # empty -> provider default
    JEV_BASE_URL = os.environ.get("JEV_BASE_URL", "")  # empty -> provider default
    CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    # A Jev answer below this confidence is handed to the LLM path for that item.
    JEV_MIN_CONFIDENCE = _safe_float(
        os.environ.get("JEV_MIN_CONFIDENCE", "0.6"),
        0.6,
        env_key="JEV_MIN_CONFIDENCE",
    )
    JEV_TIMEOUT_SECONDS = _safe_float(
        os.environ.get("JEV_TIMEOUT_SECONDS", "10"),
        10.0,
        env_key="JEV_TIMEOUT_SECONDS",
    )
    JEV_MAX_WORKERS = _safe_int(
        os.environ.get("JEV_MAX_WORKERS", "8"),
        8,
        env_key="JEV_MAX_WORKERS",
    )
    # off | shadow | active.  shadow = run Jev AND the LLM on every item, record
    # agreement in the metrics ledger, but keep using the LLM's answer — the safe
    # way to measure a new gate before trusting it.  JEV_ENABLED=true is an alias
    # for active when JEV_MODE is not set.
    JEV_MODE = (os.environ.get("JEV_MODE") or ("active" if JEV_ENABLED else "off")).lower()
    # Comma-separated gate names (see utils/jev_gate.py call sites) to force back to
    # the pure-LLM path while the rest stay on JEV_MODE.
    JEV_DISABLED_SITES = frozenset(s.strip() for s in os.environ.get("JEV_DISABLED_SITES", "").split(",") if s.strip())
    # Reference prices (USD per million tokens) used ONLY to estimate spend in the
    # Jev metrics ledger.  LLM defaults are DeepSeek chat list prices; Jev is the
    # published input price with free output.
    JEV_LLM_PRICE_IN_PER_MTOK = _safe_float(
        os.environ.get("JEV_LLM_PRICE_IN_PER_MTOK", "0.27"), 0.27, env_key="JEV_LLM_PRICE_IN_PER_MTOK"
    )
    JEV_LLM_PRICE_OUT_PER_MTOK = _safe_float(
        os.environ.get("JEV_LLM_PRICE_OUT_PER_MTOK", "1.10"), 1.10, env_key="JEV_LLM_PRICE_OUT_PER_MTOK"
    )
    JEV_PRICE_IN_PER_MTOK = _safe_float(
        os.environ.get("JEV_PRICE_IN_PER_MTOK", "0.042"), 0.042, env_key="JEV_PRICE_IN_PER_MTOK"
    )

    # Multi-scenario bundle executive synthesis (reports + LLM merge + branch weights)
    ENABLE_BUNDLE_SYNTHESIS = os.environ.get("ENABLE_BUNDLE_SYNTHESIS", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    @classmethod
    def validate(cls):
        """Validate configuration. Returns (errors, warnings)."""
        errors = []
        warnings = []
        if not cls.LLM_API_KEY:
            warnings.append("LLM_API_KEY not set — LLM features disabled")
        if not cls.ZEP_API_KEY:
            warnings.append("ZEP_API_KEY not set — graph/simulation features disabled")
        return errors, warnings


from .utils.logger import get_logger as _get_app_logger  # noqa: E402 - see bootstrap note at top of file

_log = _get_app_logger("glas.config")
