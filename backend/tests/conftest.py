"""Shared test fixtures for the Glas Intelligence backend."""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("ENABLE_REPORT_PAYLOAD_V1", "true")

from app import create_app
from app import config as app_config
from app.services.supabase_client import get_supabase_client

# Middleware and services use the module-level Config class (not Flask's TestConfig).
# Placeholders allow client init where needed; empty JWT keeps anonymous auth.
# (Real Supabase HTTP is mocked per-test — see _mock_supabase_client.)
_PLACEHOLDER_SUPABASE_URL = "http://127.0.0.1:54321"
_PLACEHOLDER_SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSJ9.ci-test-placeholder"
)
_PLACEHOLDER_LLM_KEY = "sk-test-ci-placeholder"
_PLACEHOLDER_ZEP_KEY = "zep-test-ci-placeholder"

app_config.Config.SUPABASE_URL = os.environ.get("SUPABASE_URL") or _PLACEHOLDER_SUPABASE_URL
app_config.Config.SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or _PLACEHOLDER_SUPABASE_KEY
app_config.Config.LLM_API_KEY = os.environ.get("LLM_API_KEY") or _PLACEHOLDER_LLM_KEY
app_config.Config.ZEP_API_KEY = os.environ.get("ZEP_API_KEY") or _PLACEHOLDER_ZEP_KEY
app_config.Config.SUPABASE_JWT_SECRET = ""
get_supabase_client.cache_clear()


class TestConfig:
    SECRET_KEY = "test-secret-key"
    DEBUG = False
    TESTING = True
    ENABLE_REPORT_PAYLOAD_V1 = True
    ENABLE_GROUNDING_FEATURES = True
    ENABLE_DECISION_LAYER = False
    SUPABASE_URL = app_config.Config.SUPABASE_URL
    SUPABASE_SERVICE_KEY = app_config.Config.SUPABASE_SERVICE_KEY
    SUPABASE_JWT_SECRET = ""
    SUPABASE_ANON_KEY = ""
    LLM_API_KEY = app_config.Config.LLM_API_KEY
    LLM_BASE_URL = "https://api.openai.com/v1"
    LLM_MODEL_NAME = "gpt-4o-mini"
    ZEP_API_KEY = app_config.Config.ZEP_API_KEY
    STRIPE_SECRET_KEY = ""
    STRIPE_WEBHOOK_SECRET = ""
    STRIPE_PRICE_PAYG = ""
    STRIPE_PRICE_PRO = ""
    STRIPE_PRICE_BUSINESS = ""
    STRIPE_PRICE_PACK_5 = ""
    STRIPE_PRICE_PACK_10 = ""
    STRIPE_PRICE_OVERAGE_PRO = ""
    STRIPE_PRICE_OVERAGE_BUSINESS = ""
    FRONTEND_URL = "http://localhost:3000"
    RESEND_API_KEY = ""
    RESEND_FROM_EMAIL = "test@example.com"
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "test_uploads")
    CORS_ORIGINS = "*"
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}
    DEFAULT_CHUNK_SIZE = 300
    DEFAULT_CHUNK_OVERLAP = 30
    DEFAULT_TARGET_ENTITIES = 50
    MAX_ENRICHMENT_ROUNDS = 3
    OASIS_DEFAULT_MAX_ROUNDS = 10
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), "test_uploads/simulations")
    OASIS_TWITTER_ACTIONS = ["CREATE_POST", "LIKE_POST", "DO_NOTHING"]
    OASIS_REDDIT_ACTIONS = ["CREATE_POST", "LIKE_POST", "DO_NOTHING"]
    FREE_SIMULATION_AGENTS = 25
    FREE_SIMULATION_ROUNDS = 15
    PRO_SIMULATION_AGENTS = 50
    PRO_SIMULATION_ROUNDS = 25
    BUSINESS_SIMULATION_AGENTS = 75
    BUSINESS_SIMULATION_ROUNDS = 30
    ENTERPRISE_SIMULATION_AGENTS = 200
    ENTERPRISE_SIMULATION_ROUNDS = 50
    REPORT_AGENT_MAX_TOOL_CALLS = 5
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = 2
    REPORT_AGENT_TEMPERATURE = 0.5
    GROUNDING_MAX_AGE_HOURS = 168
    GROUNDING_BLOCK_IF_STALE = False
    GROUNDING_WARN_IF_STALE = True
    ENABLE_WEB_ENRICHER = False
    DEEP_RESEARCH_ENABLED = False
    DEEP_RESEARCH_MODEL = "o4-mini-deep-research"
    DEEP_RESEARCH_MAX_TOOL_CALLS = 50
    DEEP_RESEARCH_MAX_OUTPUT_TOKENS = 50000
    JSON_AS_ASCII = False

    @classmethod
    def simulation_limits(cls, plan):
        if plan in ("free", "payg"):
            return cls.FREE_SIMULATION_AGENTS, cls.FREE_SIMULATION_ROUNDS
        if plan == "business":
            return cls.BUSINESS_SIMULATION_AGENTS, cls.BUSINESS_SIMULATION_ROUNDS
        if plan == "enterprise":
            return cls.ENTERPRISE_SIMULATION_AGENTS, cls.ENTERPRISE_SIMULATION_ROUNDS
        return cls.PRO_SIMULATION_AGENTS, cls.PRO_SIMULATION_ROUNDS

    @classmethod
    def validate(cls):
        return [], []


class _EmptyRows:
    data = []


class _MockQueryChain:
    """Fluent Supabase-style chain ending in .execute() -> {data: []}."""

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def execute(self):
        return _EmptyRows()


class _MockTable:
    def select(self, *a, **k):
        return _MockQueryChain()

    def insert(self, *a, **k):
        return _MockQueryChain()

    def update(self, *a, **k):
        return _MockQueryChain()

    def delete(self, *a, **k):
        return _MockQueryChain()


class _MockSupabaseClient:
    def table(self, _name):
        return _MockTable()


@pytest.fixture(autouse=True)
def _mock_supabase_http(monkeypatch):
    """Do not call real Supabase (CI has no DB; placeholder host may not resolve)."""
    from app.services import supabase_client

    monkeypatch.setattr(
        supabase_client.SupabaseDB,
        "client",
        staticmethod(lambda: _MockSupabaseClient()),
    )
    supabase_client.get_supabase_client.cache_clear()


@pytest.fixture
def app():
    """Create a Flask test app."""
    application = create_app(TestConfig)
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Push an application context."""
    with app.app_context():
        yield app
