"""
Jev (TypeSafe System One) client.

Jev answers *typed* questions about a blob of text: pick one option
(``choice``), rate on an ordered rubric (``score``), or give a yes/no
probability (``noul``). Every answer carries a calibrated confidence. It
cannot write prose, so it replaces the classification / scoring half of an
LLM call and never the writing half. Callers keep their LLM path as the
fallback for answers below ``Config.JEV_MIN_CONFIDENCE`` and for when Jev is
unconfigured, so switching it off restores the previous behaviour exactly.

Three routes to the same model, chosen by ``Config.JEV_PROVIDER``:

    typesafe    POST {base}/v1/systemone                       model jev-latest
    cloudflare  POST {base}/accounts/{account_id}/ai/run       model typesafe/jev
    vercel      POST {base}/v1/evaluate                        model typesafe-ai/jev

All three return the same ``answers`` map. Vercel names the yes/no type
``boolean`` and its answer field ``probability`` instead of ``noul``;
``_normalise_answer`` papers over that so callers see one shape.
"""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import requests  # type: ignore[import-untyped]

from ..config import Config
from .jev_metrics import LEDGER
from .logger import get_logger

logger = get_logger("glas.jev")

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "typesafe": {"base_url": "https://api.typesafe.ai", "model": "jev-latest"},
    "cloudflare": {"base_url": "https://api.cloudflare.com/client/v4", "model": "typesafe/jev"},
    "vercel": {"base_url": "https://ai-gateway.vercel.sh", "model": "typesafe-ai/jev"},
}

_RETRY_STATUSES = {429, 502, 503, 529}
_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = 1.0
_BACKOFF_CAP_SECONDS = 20.0


def _retry_delay(resp: Any | None, attempt: int) -> float:
    """Seconds to wait before retry ``attempt`` (0-based): Retry-After when the server sent one,
    else exponential backoff with a little jitter so parallel workers do not re-collide."""
    headers = getattr(resp, "headers", None) or {}
    retry_after = headers.get("Retry-After") if hasattr(headers, "get") else None
    if retry_after is not None:
        try:
            return float(min(_BACKOFF_CAP_SECONDS, max(0.0, float(retry_after))))
        except (TypeError, ValueError):
            pass
    return min(_BACKOFF_CAP_SECONDS, _BACKOFF_SECONDS * (2.0**attempt)) + random.uniform(0.0, 0.25)


class JevError(RuntimeError):
    """Raised when Jev returns a non-retryable error or retries are exhausted."""


@dataclass
class JevAnswer:
    """One typed answer.

    ``value`` is the option name for a choice, the interpolated rubric
    position (0-based float) for a score, or P(yes) for a noul.
    ``confidence`` is 0-1; for a noul it is ``max(p, 1 - p)`` because the
    API does not return one.
    """

    kind: str
    value: Any
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)

    @property
    def level(self) -> int:
        """Nearest rubric index for a score answer."""
        return int(round(float(self.value)))


def _normalise_answer(raw: dict[str, Any]) -> JevAnswer:
    kind = str(raw.get("type", ""))
    probabilities = {str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()}

    if kind == "choice":
        value = raw.get("choice")
        confidence = raw.get("confidence")
        if confidence is None:
            confidence = probabilities.get(str(value), 0.0)
        return JevAnswer("choice", value, float(confidence), probabilities)

    if kind == "score":
        value = float(raw.get("score", 0.0))
        confidence = raw.get("confidence")
        if confidence is None:
            confidence = max(probabilities.values(), default=0.0)
        return JevAnswer("score", value, float(confidence), probabilities)

    if kind in ("noul", "boolean"):
        p = raw.get("noul", raw.get("probability"))
        if p is None:
            raise JevError(f"noul answer missing probability: {raw}")
        p = float(p)
        return JevAnswer("noul", p, max(p, 1.0 - p), probabilities)

    raise JevError(f"unknown Jev answer type: {kind!r}")


class JevClient:
    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        account_id: str | None = None,
        timeout: float = 10.0,
        session: Any | None = None,
    ):
        provider = (provider or "typesafe").lower()
        if provider not in PROVIDER_DEFAULTS:
            raise ValueError(f"unknown JEV_PROVIDER {provider!r}; expected one of {sorted(PROVIDER_DEFAULTS)}")
        if not api_key:
            raise ValueError("Jev API key missing")
        if provider == "cloudflare" and not account_id:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID is required for the cloudflare provider")

        defaults = PROVIDER_DEFAULTS[provider]
        self.provider = provider
        self.api_key = api_key
        self.model = model or defaults["model"]
        self.base_url = (base_url or defaults["base_url"]).rstrip("/")
        self.account_id = account_id
        self.timeout = timeout
        self._session = session or requests.Session()

    @classmethod
    def from_config(cls) -> JevClient | None:
        """Build a client from ``Config``; ``None`` when Jev is off or unconfigured."""
        if Config.JEV_MODE == "off" or not Config.JEV_API_KEY:
            return None
        try:
            return cls(
                provider=Config.JEV_PROVIDER,
                api_key=Config.JEV_API_KEY,
                model=Config.JEV_MODEL or None,
                base_url=Config.JEV_BASE_URL or None,
                account_id=Config.CLOUDFLARE_ACCOUNT_ID or None,
                timeout=Config.JEV_TIMEOUT_SECONDS,
            )
        except ValueError as e:
            logger.warning(f"Jev disabled: {e}")
            return None

    # ------------------------------------------------------------------
    # Question builders
    # ------------------------------------------------------------------

    @staticmethod
    def choice_q(instructions: str, options: dict[str, str]) -> dict[str, Any]:
        """A pick-one question. ``options`` maps option name -> description."""
        return {"type": "choice", "instructions": instructions, "criteria": dict(options)}

    @staticmethod
    def score_q(instructions: str, levels: list[str]) -> dict[str, Any]:
        """An ordered-rubric question. ``levels`` run lowest to highest (2-10)."""
        if not 2 <= len(levels) <= 10:
            raise ValueError("a score question needs between 2 and 10 levels")
        return {"type": "score", "instructions": instructions, "criteria": list(levels)}

    @staticmethod
    def noul_q(instructions: str, criteria: dict[str, str] | None = None) -> dict[str, Any]:
        """A yes/no probability question."""
        q: dict[str, Any] = {"type": "noul", "instructions": instructions}
        if criteria:
            q["criteria"] = dict(criteria)
        return q

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def evaluate(
        self,
        state: Any,
        questions: dict[str, dict[str, Any]],
        *,
        site: str = "unlabelled",
    ) -> dict[str, JevAnswer]:
        """Answer every question in ``questions`` against ``state`` in one round trip.

        ``site`` labels the call in the metrics ledger (tokens, latency, failures).
        """
        url, body = self._build_request(state, questions)
        started = time.perf_counter()
        try:
            payload = self._post(url, body)
        except Exception:
            LEDGER.record_jev_call(site, input_tokens=0, latency_ms=(time.perf_counter() - started) * 1000, ok=False)
            raise
        latency_ms = (time.perf_counter() - started) * 1000
        # Cloudflare wraps partner models twice: its REST envelope {"result": ...},
        # then a job record {"state": "Completed", "result": {...}}. Peel until
        # the native {"model", "answers", "usage"} object is in hand.
        while "answers" not in payload and isinstance(payload.get("result"), dict) and payload["result"]:
            payload = payload["result"]
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            job_state = payload.get("state")
            LEDGER.record_jev_call(site, input_tokens=0, latency_ms=latency_ms, ok=False)
            if job_state and job_state != "Completed":
                raise JevError(f"Jev job not completed (state={job_state!r}): {str(payload)[:200]}")
            raise JevError(f"Jev response has no answers map: {str(payload)[:200]}")
        usage = payload.get("usage") or {}
        input_tokens = usage.get("input_tokens", usage.get("inputTokens", 0)) if isinstance(usage, dict) else 0
        LEDGER.record_jev_call(site, input_tokens=int(input_tokens or 0), latency_ms=latency_ms, ok=True)
        return {name: _normalise_answer(raw) for name, raw in answers.items()}

    def evaluate_many(
        self,
        items: list[tuple[Any, dict[str, dict[str, Any]]]],
        max_workers: int | None = None,
        *,
        site: str = "unlabelled",
    ) -> list[dict[str, JevAnswer] | None]:
        """``evaluate`` each ``(state, questions)`` concurrently, preserving order.

        A failed item yields ``None`` rather than failing the batch, so the
        caller can route it to its fallback.
        """
        if not items:
            return []
        workers = max(1, min(max_workers or Config.JEV_MAX_WORKERS, len(items)))

        def _one(item: tuple[Any, dict[str, dict[str, Any]]]) -> dict[str, JevAnswer] | None:
            try:
                return self.evaluate(*item, site=site)
            except Exception as e:
                logger.warning(f"Jev evaluate failed: {e}")
                return None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_one, items))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_request(self, state: Any, questions: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        if self.provider == "cloudflare":
            url = f"{self.base_url}/accounts/{self.account_id}/ai/run"
            return url, {"model": self.model, "input": {"state": state, "questions": questions}}

        if self.provider == "vercel":
            url = f"{self.base_url}/v1/evaluate"
            translated = {
                name: ({**q, "type": "boolean"} if q.get("type") == "noul" else q) for name, q in questions.items()
            }
            return url, {"model": self.model, "state": state, "questions": translated}

        url = f"{self.base_url}/v1/systemone"
        return url, {"model": self.model, "state": state, "questions": questions}

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: str = "no attempts made"
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = self._session.post(url, json=body, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(_retry_delay(None, attempt))
                continue

            if resp.status_code in _RETRY_STATUSES:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(_retry_delay(resp, attempt))
                continue
            if resp.status_code >= 400:
                raise JevError(f"Jev HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            if not isinstance(data, dict):
                raise JevError(f"Jev returned non-object JSON: {str(data)[:200]}")
            return data

        raise JevError(f"Jev request failed after {_MAX_ATTEMPTS} attempts ({last_error})")
