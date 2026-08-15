"""JWT authentication middleware using Supabase."""

import functools
from flask import request, jsonify, g
import jwt
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("glas.auth")

ANONYMOUS_USER_ID = "anonymous"

# JWKS is fetched from Supabase once and cached: creating a fresh PyJWKClient
# per request fetches the keys on every call, and a flaky fetch means
# intermittent 401s on otherwise-valid ES256 tokens.
_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        jwks_url = Config.SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        _jwks_client = jwt.PyJWKClient(jwks_url)
    return _jwks_client


def _get_signing_key(token: str):
    """Fetch the signing key with a bounded retry — JWKS fetches over a flaky
    network (SSL EOF / broken pipe) would otherwise turn into spurious 401s."""
    jwks_client = _get_jwks_client()
    last_err = None
    for attempt in range(3):
        try:
            return jwks_client.get_signing_key_from_jwt(token)
        except Exception as e:
            last_err = e
            if attempt < 2:
                import time
                time.sleep(0.5 * (attempt + 1))
    raise last_err


def _get_jwt_secret() -> str:
    return Config.SUPABASE_JWT_SECRET


def _decode_supabase_jwt(token: str) -> dict:
    secret = _get_jwt_secret()
    if not secret:
        raise ValueError("SUPABASE_JWT_SECRET not configured")

    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "HS256")

    if alg == "HS256":
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")

    jwks_client = _get_jwks_client()
    signing_key = _get_signing_key(token)
    return jwt.decode(token, signing_key.key, algorithms=[alg], audience="authenticated")


def extract_user_from_request():
    """Extract user_id from Authorization header. Sets g.user_id and g.user_email."""
    auth_header = request.headers.get("Authorization", "")

    if not Config.SUPABASE_URL or not Config.SUPABASE_JWT_SECRET:
        g.user_id = ANONYMOUS_USER_ID
        g.user_email = ""
        return

    if not auth_header.startswith("Bearer "):
        g.user_id = None
        g.user_email = None
        return

    token = auth_header[7:]
    try:
        payload = _decode_supabase_jwt(token)
        g.user_id = payload.get("sub")
        g.user_email = payload.get("email", "")
    except Exception as e:
        logger.warning(f"JWT decode failed: {e}")
        g.user_id = None
        g.user_email = None


def require_auth(f):
    """Decorator that rejects unauthenticated requests."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not Config.SUPABASE_URL or not Config.SUPABASE_JWT_SECRET:
            g.user_id = ANONYMOUS_USER_ID
            g.user_email = ""
            return f(*args, **kwargs)

        if not getattr(g, "user_id", None):
            return jsonify({"success": False, "error": "Authentication required"}), 401
        return f(*args, **kwargs)

    return wrapper


def optional_auth(f):
    """Decorator that allows unauthenticated requests (user_id may be None)."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper
