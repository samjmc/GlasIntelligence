"""Records a real run to a time-indexed tape the browser can replay.

Enabled only when DEMO_RECORD=1. Writes periodically (every FLUSH_EVERY
entries, or at the end of the run) so a crashed run leaves a usable partial
tape without the O(n²) cost of flushing the entire tape on every response.

normalise_path must stay byte-identical in behaviour to normalisePath() in
frontend/src/demo/tape.js. If one changes, change the other.

Query strings are preserved in the recorded path where present so the
browser replayer can disambiguate cursor-based endpoints (e.g. agent-log
?from_line=N). The replayer tries the query-aware key first, then falls
back to the stripped key — the plan's "stripped except where disambiguated" rule.

Secret scrubbing: response bodies are scanned before recording. Real UUIDs are
rewritten to stable demo IDs (consistent within a single recording so referential
integrity survives). Bearer tokens, API keys, and Stripe IDs are redacted.
"""

import atexit
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
from collections.abc import Callable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Flush the tape after this many new entries (IMPORTANT 5 — prevents O(n²) per-response flush).
FLUSH_EVERY = 20

# ── Path normalisation ───────────────────────────────────────────────────────
# A path segment is an ID if it is a UUID, a demo id, an all-digit id, or a long
# opaque token. Recorder and replayer share this rule, so a false positive is
# symmetric — but two distinct endpoints collapsing to one key would silently
# serve the wrong response, so the opaque rule requires at least one digit.
# Without that, "/api/simulation/suggest-followups" (17 chars) becomes
# "/api/simulation/:id".
#
# MINOR 8 fixes:
#   - \d → [0-9]  Python's \d matches non-ASCII digits (٠١٢ etc); JS \d does not.
#   - $  → \Z     Python's $ matches before a trailing \n (from Werkzeug percent-decode
#                 of %0A); \Z is unconditional end-of-string. The comment below becomes
#                 true only after these fixes.
# NOTE: DEMO must be anchored at start only (^demo[_-]) — an unanchored match
# would hit mid-string and diverge from the JS counterpart.
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_DEMO = re.compile(r"^demo[_-]")
_DIGITS = re.compile(r"^[0-9]+\Z")
_OPAQUE = re.compile(r"^(?=.*[0-9])[A-Za-z0-9_-]{16,}\Z")


def normalise_path(path: str) -> str:
    """Normalise only the path portion (no query string).

    Must stay behaviourally identical to normalisePath() in
    frontend/src/demo/tape.js (modulo MINOR 8 fixes above).
    Shared test cases are duplicated verbatim in
    backend/tests/test_demo_recorder.py::test_normalise_path — change both or neither.
    """
    path = path.split("?", 1)[0]
    segments = path.split("/")
    out = []
    for seg in segments:
        if seg and (
            _UUID.match(seg) or _DEMO.match(seg) or _DIGITS.match(seg) or _OPAQUE.match(seg)
        ):
            out.append(":id")
        else:
            out.append(seg)
    return "/".join(out)


def canonical_query(query_string: str) -> str:
    """Return a sorted, re-encoded query string for stable index keys.

    Must stay behaviourally identical to canonicalQuery() in
    frontend/src/demo/tape.js. Both sort by key and re-encode with
    percent-encoding so 'from_line=0' and 'from_line%3D0' collapse to
    the same key.
    """
    if not query_string:
        return ""
    pairs = urllib.parse.parse_qsl(query_string, keep_blank_values=True)
    pairs.sort(key=lambda kv: kv[0])
    return urllib.parse.urlencode(pairs)


# ── Secret scrubbing ─────────────────────────────────────────────────────────

# Patterns that identify secrets inline in values.
_BEARER = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_API_KEY = re.compile(r"\b(sk|pk|rk)_[A-Za-z0-9_-]{16,}")
_STRIPE_CUS = re.compile(r"\bcus_[A-Za-z0-9]{8,}")
_STRIPE_SUB = re.compile(r"\bsub_[A-Za-z0-9]{8,}")
_REAL_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# Stable prefix for rewritten UUIDs — chosen to be recognisable in a tape.
_DEMO_UUID_PREFIX = "demo0000"


def _stable_demo_uuid(real_uuid: str, _cache: dict = {}) -> str:  # noqa: B006
    """Map a real UUID to a stable demo UUID.

    The same input always returns the same output within a process invocation
    (memoised in ``_cache``), preserving referential integrity across the tape.
    The output is a well-formed UUID built from the first 28 hex chars of the
    SHA-256 of the input, prefixed with a recognisable demo marker.
    """
    if real_uuid in _cache:
        return _cache[real_uuid]
    digest = hashlib.sha256(real_uuid.encode()).hexdigest()
    demo = f"{_DEMO_UUID_PREFIX}-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:24]}"
    _cache[real_uuid] = demo
    return demo


def scrub_body(obj):
    """Recursively scrub secrets from a decoded JSON value.

    - Bearer tokens and API keys → "<REDACTED>"
    - Stripe cus_/sub_ ids → "<REDACTED>"
    - Real UUIDs → stable demo UUIDs (same input → same output so referential
      integrity across the tape survives)
    """
    if isinstance(obj, dict):
        return {k: scrub_body(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_body(item) for item in obj]
    if isinstance(obj, str):
        s = obj
        s = _BEARER.sub("<REDACTED>", s)
        s = _API_KEY.sub("<REDACTED>", s)
        s = _STRIPE_CUS.sub("<REDACTED>", s)
        s = _STRIPE_SUB.sub("<REDACTED>", s)
        s = _REAL_UUID.sub(lambda m: _stable_demo_uuid(m.group(0)), s)
        return s
    return obj


# ── Recorder ─────────────────────────────────────────────────────────────────

def init_recorder(app, out_path: str, scenario: str) -> "Callable[[], None]":
    """Initialise the demo recorder.

    Returns a ``close()`` callable that flushes the tail of the tape and
    de-registers the atexit handler.  In production, closing happens via atexit
    when the recording process exits.  In tests, call ``close()`` after the
    test client requests so you can read a complete tape without waiting for
    process exit.
    """
    start = time.monotonic()
    entries: list[dict] = []
    unflushed: list[int] = [0]  # mutable counter (int in a list for closure capture)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    def flush() -> None:
        tmp = out_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "scenario": scenario,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "entries": entries,
                },
                fh,
            )
        os.replace(tmp, out_path)
        unflushed[0] = 0

    @app.after_request
    def _record(response):
        from flask import request

        if not request.path.startswith("/api/"):
            return response
        if "json" not in (response.content_type or ""):
            return response

        try:
            body = json.loads(response.get_data(as_text=True))
        except (ValueError, UnicodeDecodeError):
            return response

        # Build the key path: normalised path + canonical query string.
        # The query string is preserved so the browser replayer can
        # disambiguate cursor-based endpoints (e.g. agent-log?from_line=N).
        npath = normalise_path(request.path)
        cq = canonical_query(request.query_string.decode("utf-8", errors="replace"))
        recorded_path = f"{npath}?{cq}" if cq else npath

        entries.append(
            {
                "t_ms": int((time.monotonic() - start) * 1000),
                "method": request.method,
                "path": recorded_path,
                "status": response.status_code,
                "body": scrub_body(body),
            }
        )

        unflushed[0] += 1
        if unflushed[0] >= FLUSH_EVERY:
            # Guarded flush: an I/O failure must not crash the request pipeline.
            try:
                flush()
            except OSError as e:
                logger.error(f"Failed to flush demo tape: {e}")
        return response

    # Register a final flush on process exit so the tail of the tape (the last
    # < FLUSH_EVERY entries not yet written by the batched flush) is not lost.
    # This is guarded (log-only on failure) to avoid masking the exit code.
    def _final_flush():
        if unflushed[0] > 0:
            try:
                flush()
            except OSError as e:
                logger.error(f"Failed to write final demo tape on exit: {e}")

    atexit.register(_final_flush)

    def close() -> None:
        """Flush any unwritten tail and de-register the atexit handler."""
        atexit.unregister(_final_flush)
        _final_flush()

    # Init-time flush is fail-fast: if we cannot write the empty tape the
    # recording is already broken and the operator should fix the path now
    # rather than discover the problem after a full run.
    flush()
    return close
