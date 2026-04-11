"""
Configuration management
Load configuration from .env file in project root
"""

import os
from dotenv import load_dotenv

# Load .env file from project root
# Path: .env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root, try loading env vars (for production)
    load_dotenv(override=True)


class Config:
    """Flask configuration class"""
    
    # Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'glas-intelligence-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON config - disable ASCII escape so non-ASCII displays directly (not as \uXXXX)
    JSON_AS_ASCII = False
    
    # LLM config (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Supabase config
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
    SUPABASE_JWT_SECRET = os.environ.get('SUPABASE_JWT_SECRET', '')
    SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
    
    # Stripe config
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    STRIPE_PRICE_PAYG = os.environ.get('STRIPE_PRICE_PAYG', '')
    STRIPE_PRICE_PRO = os.environ.get('STRIPE_PRICE_PRO', '')
    STRIPE_PRICE_BUSINESS = os.environ.get('STRIPE_PRICE_BUSINESS', '')
    STRIPE_PRICE_PACK_5 = os.environ.get('STRIPE_PRICE_PACK_5', '')
    STRIPE_PRICE_PACK_10 = os.environ.get('STRIPE_PRICE_PACK_10', '')
    STRIPE_PRICE_OVERAGE_PRO = os.environ.get('STRIPE_PRICE_OVERAGE_PRO', '')
    STRIPE_PRICE_OVERAGE_BUSINESS = os.environ.get('STRIPE_PRICE_OVERAGE_BUSINESS', '')
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
    
    # Resend email config
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
    RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'noreply@glasinsight.com')
    
    # Zep config
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # File upload config
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # Text processing config
    DEFAULT_CHUNK_SIZE = 300  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 30  # Default overlap size
    DEFAULT_TARGET_ENTITIES = int(os.environ.get('DEFAULT_TARGET_ENTITIES', '50'))
    MAX_ENRICHMENT_ROUNDS = int(os.environ.get('MAX_ENRICHMENT_ROUNDS', '3'))
    
    # OASIS simulation config
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS platform available actions config
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Simulation cost caps per plan
    FREE_SIMULATION_AGENTS = int(os.environ.get('FREE_SIMULATION_AGENTS', '25'))
    FREE_SIMULATION_ROUNDS = int(os.environ.get('FREE_SIMULATION_ROUNDS', '15'))
    PRO_SIMULATION_AGENTS = int(os.environ.get('PRO_SIMULATION_AGENTS', '50'))
    PRO_SIMULATION_ROUNDS = int(os.environ.get('PRO_SIMULATION_ROUNDS', '25'))
    BUSINESS_SIMULATION_AGENTS = int(os.environ.get('BUSINESS_SIMULATION_AGENTS', '75'))
    BUSINESS_SIMULATION_ROUNDS = int(os.environ.get('BUSINESS_SIMULATION_ROUNDS', '30'))
    ENTERPRISE_SIMULATION_AGENTS = int(os.environ.get('ENTERPRISE_SIMULATION_AGENTS', '200'))
    ENTERPRISE_SIMULATION_ROUNDS = int(os.environ.get('ENTERPRISE_SIMULATION_ROUNDS', '50'))
    
    @classmethod
    def normalize_plan(cls, plan: str | None) -> str:
        """Lowercase/strip profiles.plan (e.g. manual Supabase value 'Enterprise')."""
        if plan is None:
            return 'free'
        p = str(plan).strip().lower()
        if p in ('', 'null', 'none', 'undefined'):
            return 'free'
        return p

    @classmethod
    def simulation_limits(cls, plan: str | None) -> tuple:
        """Return (max_agents, max_rounds) for a given plan."""
        plan = cls.normalize_plan(plan)
        if plan in ('free', 'payg'):
            return cls.FREE_SIMULATION_AGENTS, cls.FREE_SIMULATION_ROUNDS
        if plan == 'business':
            return cls.BUSINESS_SIMULATION_AGENTS, cls.BUSINESS_SIMULATION_ROUNDS
        if plan == 'enterprise':
            return cls.ENTERPRISE_SIMULATION_AGENTS, cls.ENTERPRISE_SIMULATION_ROUNDS
        return cls.PRO_SIMULATION_AGENTS, cls.PRO_SIMULATION_ROUNDS
    
    # Report Agent config
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    # Valued-output report payload v1 + grounding (domain-agnostic)
    ENABLE_REPORT_PAYLOAD_V1 = os.environ.get('ENABLE_REPORT_PAYLOAD_V1', 'true').lower() in ('1', 'true', 'yes')
    ENABLE_GROUNDING_FEATURES = os.environ.get('ENABLE_GROUNDING_FEATURES', 'true').lower() in ('1', 'true', 'yes')
    GROUNDING_MAX_AGE_HOURS = float(os.environ.get('GROUNDING_MAX_AGE_HOURS', '168'))  # 7 days default
    GROUNDING_BLOCK_IF_STALE = os.environ.get('GROUNDING_BLOCK_IF_STALE', 'false').lower() in ('1', 'true', 'yes')
    GROUNDING_WARN_IF_STALE = os.environ.get('GROUNDING_WARN_IF_STALE', 'true').lower() in ('1', 'true', 'yes')
    ENABLE_WEB_ENRICHER = os.environ.get('ENABLE_WEB_ENRICHER', 'false').lower() in ('1', 'true', 'yes')
    
    # Deep Research (OpenAI Responses API)
    DEEP_RESEARCH_ENABLED = os.environ.get('DEEP_RESEARCH_ENABLED', 'false').lower() in ('1', 'true', 'yes')
    DEEP_RESEARCH_MODEL = os.environ.get('DEEP_RESEARCH_MODEL', 'o4-mini-deep-research')
    DEEP_RESEARCH_MAX_TOOL_CALLS = int(os.environ.get('DEEP_RESEARCH_MAX_TOOL_CALLS', '50'))
    
    # Decision layer
    ENABLE_DECISION_LAYER = os.environ.get('ENABLE_DECISION_LAYER', 'false').lower() in ('1', 'true', 'yes')
    
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

