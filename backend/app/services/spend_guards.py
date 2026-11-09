"""Spend guards for free usage: free runs and free briefings spend the owner's LLM balance.

Free runs pause for the rest of the UTC day once FREE_RUNS_PER_DAY have started site-wide,
and free runs and briefings pause while the LLM provider balance is known to be below
LLM_MIN_BALANCE_FOR_FREE_USD. An unknown balance (not DeepSeek, or the check failed) never
blocks. Paid usage is never paused here.
"""

import threading
import time

import requests  # type: ignore[import-untyped]

from ..config import Config
from ..utils.logger import get_logger
from .supabase_client import SupabaseDB

logger = get_logger("glas.spend_guards")

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"
BALANCE_TIMEOUT_SECONDS = 5

# paused_reason values reported by /api/billing/can-simulate
PAUSED_DAILY_CAP = "daily_cap"
PAUSED_LOW_BALANCE = "low_balance"

_balance_lock = threading.Lock()
_balance_cache: tuple[float, float | None] | None = None  # (time.monotonic() when read, balance)


def _fetch_llm_balance_usd() -> float | None:
    """The provider's USD balance, or None if not DeepSeek or the call fails. Never logs the key."""
    if "deepseek" not in (Config.LLM_BASE_URL or "").lower() or not Config.LLM_API_KEY:
        return None
    try:
        resp = requests.get(
            DEEPSEEK_BALANCE_URL,
            headers={"Authorization": f"Bearer {Config.LLM_API_KEY}"},
            timeout=BALANCE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("is_available") is False:
            return 0.0
        for info in body.get("balance_infos") or []:
            if info.get("currency") == "USD":
                return float(info["total_balance"])
    except Exception as e:
        logger.warning(f"LLM balance check failed: {type(e).__name__}")
    return None


def llm_balance_usd() -> float | None:
    """The provider's USD balance, read at most once per LLM_BALANCE_CACHE_SECONDS."""
    global _balance_cache
    with _balance_lock:
        now = time.monotonic()
        if _balance_cache is None or now - _balance_cache[0] >= Config.LLM_BALANCE_CACHE_SECONDS:
            _balance_cache = (now, _fetch_llm_balance_usd())
        return _balance_cache[1]


def llm_balance_low() -> bool:
    """True only when the balance is known and below the floor for free usage."""
    balance = llm_balance_usd()
    return balance is not None and balance < Config.LLM_MIN_BALANCE_FOR_FREE_USD


def free_runs_paused_reason() -> str | None:
    """Why free runs are paused right now (PAUSED_LOW_BALANCE or PAUSED_DAILY_CAP), or None."""
    if llm_balance_low():
        return PAUSED_LOW_BALANCE
    try:
        if SupabaseDB.count_free_runs_today() >= Config.FREE_RUNS_PER_DAY:
            return PAUSED_DAILY_CAP
    except Exception as e:
        # Cannot count today's free runs, so do not give away more (like has_free_simulation_remaining).
        logger.warning(f"Free run daily count failed: {e}")
        return PAUSED_DAILY_CAP
    return None
