"""Shared test fixtures for the Glas Intelligence backend."""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("ENABLE_REPORT_PAYLOAD_V1", "true")
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")

from app import create_app


class TestConfig:
    SECRET_KEY = "test-secret-key"
    DEBUG = False
    TESTING = True
    ENABLE_REPORT_PAYLOAD_V1 = True
    ENABLE_GROUNDING_FEATURES = True
    ENABLE_DECISION_LAYER = False
    SUPABASE_URL = ""
    SUPABASE_SERVICE_KEY = ""
    SUPABASE_JWT_SECRET = "test-jwt-secret"
    SUPABASE_ANON_KEY = ""
    LLM_API_KEY = ""
    LLM_BASE_URL = "https://api.openai.com/v1"
    LLM_MODEL_NAME = "gpt-4o-mini"
    ZEP_API_KEY = ""
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
