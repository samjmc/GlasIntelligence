"""
Filesystem snapshot cache for full Zep graph reads (nodes + edges).

Reduces repeated paginated Zep list calls for visualization and entity prep.
See docs/graph-cache.md for invalidation and operations.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum
from typing import Any
from collections.abc import Callable

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("glas.graph_snapshot_cache")

# Envelope key inside written JSON (stripped on read for API compatibility)
_GLAS_CACHE_META = "_glas_cache_meta"

# Current on-disk format (bump when structure changes)
SNAPSHOT_FORMAT_VERSION = 2

_SAFE_GRAPH_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,256}$")


class CacheOutcome(str, Enum):
    DISABLED = "DISABLED"
    BYPASS = "BYPASS"
    HIT = "HIT"
    MISS = "MISS"
    STALE = "STALE"


@dataclass
class CacheReadResult:
    """Result of a cache read attempt."""

    data: dict[str, Any] | None
    outcome: CacheOutcome
    age_seconds: float | None = None


def sanitize_graph_id(graph_id: str) -> str | None:
    """Return graph_id if safe for use as a directory name, else None."""
    if not graph_id or not isinstance(graph_id, str):
        return None
    if not _SAFE_GRAPH_ID_RE.match(graph_id):
        return None
    return graph_id


def _cache_root() -> str:
    root = os.path.join(Config.UPLOAD_FOLDER, "graph_cache")
    return root


def _graph_dir(safe_id: str) -> str:
    return os.path.join(_cache_root(), safe_id)


def _snapshot_path(safe_id: str) -> str:
    return os.path.join(_graph_dir(safe_id), "snapshot.json")


def _generation_path(safe_id: str) -> str:
    return os.path.join(_graph_dir(safe_id), "mutation_generation")


def read_mutation_generation(graph_id: str) -> int:
    """Read global mutation generation for graph_id from disk (0 if missing)."""
    sid = sanitize_graph_id(graph_id)
    if not sid:
        return 0
    path = _generation_path(sid)
    try:
        with open(path, encoding="utf-8") as f:
            return max(0, int(f.read().strip() or "0"))
    except (OSError, ValueError):
        return 0


def bump_mutation_generation(graph_id: str) -> int:
    """
    Atomically increment mutation generation (invalidates snapshots that embed an older generation).
    Returns the new generation value.
    """
    sid = sanitize_graph_id(graph_id)
    if not sid:
        return 0
    d = _graph_dir(sid)
    os.makedirs(d, exist_ok=True)
    path = _generation_path(sid)
    lock = _generation_lock(sid)
    with lock:
        cur = 0
        try:
            with open(path, encoding="utf-8") as f:
                cur = max(0, int(f.read().strip() or "0"))
        except (OSError, ValueError):
            pass
        nxt = cur + 1
        _atomic_write_text(path, str(nxt))
    logger.debug("graph_cache: bumped mutation_generation for %s -> %s", graph_id, nxt)
    return nxt


_gen_locks: dict[str, threading.Lock] = {}
_gen_locks_guard = threading.Lock()


def _generation_lock(sid: str) -> threading.Lock:
    with _gen_locks_guard:
        if sid not in _gen_locks:
            _gen_locks[sid] = threading.Lock()
        return _gen_locks[sid]


_flight_locks: dict[str, threading.Lock] = {}
_flight_guard = threading.Lock()


def _flight_lock(sid: str) -> threading.Lock:
    with _flight_guard:
        if sid not in _flight_locks:
            _flight_locks[sid] = threading.Lock()
        return _flight_locks[sid]


def _atomic_write_text(path: str, text: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _atomic_write_json(path: str, obj: Any) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _sha256_of_payload(payload: dict[str, Any]) -> str:
    # Stable hash of semantic graph content (exclude meta if present)
    body = {k: v for k, v in payload.items() if k != _GLAS_CACHE_META}
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strip_meta_copy(doc: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in doc.items() if k != _GLAS_CACHE_META}
    return out


def _validate_payload(doc: dict[str, Any], graph_id: str, snapshot_path: str) -> dict[str, Any] | None:
    # Residual (harden later): early returns below (bad meta, format_version, graph_id, nodes/edges)
    # do not unlink snapshot_path — stale bad files linger until LRU, invalidate, or manual cleanup.
    # Extend safe unlink + logging to those paths in a cache hardening pass.
    meta = doc.get(_GLAS_CACHE_META)
    if not isinstance(meta, dict):
        return None
    if int(meta.get("format_version", 0)) != SNAPSHOT_FORMAT_VERSION:
        return None
    if doc.get("graph_id") != graph_id:
        return None
    nodes = doc.get("nodes")
    edges = doc.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    raw_hash = meta.get("content_sha256")
    if not raw_hash or not isinstance(raw_hash, str) or not raw_hash.strip():
        logger.warning(
            "graph_cache: missing or empty content_sha256 for %s, rejecting snapshot",
            graph_id,
        )
        try:
            os.unlink(snapshot_path)
        except OSError:
            pass
        return None
    stored_hash = raw_hash.strip()
    computed = _sha256_of_payload(doc)
    if stored_hash != computed:
        logger.warning("graph_cache: sha256 mismatch for %s, ignoring snapshot", graph_id)
        try:
            os.unlink(snapshot_path)
        except OSError:
            pass
        return None
    return doc


def _snapshot_age_seconds(meta: dict[str, Any]) -> float | None:
    ts = meta.get("written_at_unix")
    if ts is None:
        return None
    try:
        return max(0.0, time.time() - float(ts))
    except (TypeError, ValueError):
        return None


def invalidate(graph_id: str) -> None:
    """Remove all cached files for graph_id."""
    sid = sanitize_graph_id(graph_id)
    if not sid:
        return
    d = _graph_dir(sid)
    try:
        shutil.rmtree(d, ignore_errors=True)
        logger.info("graph_cache: invalidated %s", graph_id)
    except OSError as e:
        logger.warning("graph_cache: failed to invalidate %s: %s", graph_id, e)


def _enforce_disk_quota() -> None:
    max_mb = getattr(Config, "GRAPH_SNAPSHOT_MAX_DISK_MB", 0) or 0
    if max_mb <= 0:
        return
    root = _cache_root()
    if not os.path.isdir(root):
        return
    max_bytes = max_mb * 1024 * 1024
    entries: list[tuple[float, str]] = []
    total = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        try:
            du = _dir_size(p)
            mtime = os.path.getmtime(p)
            entries.append((mtime, p))
            total += du
        except OSError:
            continue
    while total > max_bytes and entries:
        entries.sort(key=lambda x: x[0])
        oldest = entries.pop(0)[1]
        try:
            sz = _dir_size(oldest)
            shutil.rmtree(oldest, ignore_errors=True)
            total -= sz
            logger.warning("graph_cache: LRU evicted %s (quota %s MB)", oldest, max_mb)
        except OSError:
            break


def _dir_size(path: str) -> int:
    n = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                n += os.path.getsize(fp)
            except OSError:
                pass
    return n


def try_read_snapshot(
    graph_id: str,
    *,
    for_stale_fallback: bool = False,
) -> CacheReadResult:
    """
    Read snapshot if present and consistent with current mutation_generation.
    If for_stale_fallback, skip generation match (used only after Zep failure, with age cap).
    """
    if not Config.GRAPH_SNAPSHOT_CACHE_ENABLED:
        return CacheReadResult(None, CacheOutcome.DISABLED)

    sid = sanitize_graph_id(graph_id)
    if not sid:
        return CacheReadResult(None, CacheOutcome.MISS)

    path = _snapshot_path(sid)
    if not os.path.isfile(path):
        return CacheReadResult(None, CacheOutcome.MISS)

    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("graph_cache: corrupt snapshot %s: %s", graph_id, e)
        try:
            os.unlink(path)
        except OSError:
            pass
        return CacheReadResult(None, CacheOutcome.MISS)

    if not isinstance(doc, dict):
        return CacheReadResult(None, CacheOutcome.MISS)

    validated = _validate_payload(doc, graph_id, path)
    if not validated:
        return CacheReadResult(None, CacheOutcome.MISS)

    meta = validated[_GLAS_CACHE_META]
    age = _snapshot_age_seconds(meta)
    ttl = int(getattr(Config, "GRAPH_SNAPSHOT_TTL_SECONDS", 86400) or 86400)

    current_gen = read_mutation_generation(graph_id)
    snap_gen = int(meta.get("mutation_generation", 0) or 0)

    if not for_stale_fallback:
        if snap_gen != current_gen:
            return CacheReadResult(None, CacheOutcome.MISS)
        if age is not None and age > ttl:
            return CacheReadResult(None, CacheOutcome.MISS)

    if for_stale_fallback:
        stale_max = int(getattr(Config, "GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS", 604800) or 604800)
        if age is not None and age > stale_max:
            return CacheReadResult(None, CacheOutcome.MISS)

    data = _strip_meta_copy(validated)
    return CacheReadResult(data, CacheOutcome.STALE if for_stale_fallback else CacheOutcome.HIT, age)


def write_snapshot(graph_id: str, data: dict[str, Any]) -> bool:
    """Persist graph payload (API-shaped dict) with current mutation_generation embedded."""
    if not Config.GRAPH_SNAPSHOT_CACHE_ENABLED:
        return False
    sid = sanitize_graph_id(graph_id)
    if not sid:
        return False
    if data.get("graph_id") != graph_id:
        logger.warning("graph_cache: refuse write, graph_id mismatch")
        return False

    try:
        gen = read_mutation_generation(graph_id)
        doc = dict(data)
        doc[_GLAS_CACHE_META] = {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "written_at_unix": time.time(),
            "mutation_generation": gen,
            "content_sha256": _sha256_of_payload(doc),
        }
        path = _snapshot_path(sid)
        _atomic_write_json(path, doc)
        _enforce_disk_quota()
        logger.info("graph_cache: wrote snapshot for %s (gen=%s)", graph_id, gen)
        return True
    except OSError as e:
        if e.errno == 28:  # ENOSPC
            logger.error("graph_cache: disk full, skip write for %s", graph_id)
        else:
            logger.warning("graph_cache: write failed for %s: %s", graph_id, e)
        return False


def try_get_lists_for_entity_reader(graph_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """
    If snapshot is fresh (HIT semantics), return (nodes_data, edges_data) in ZepEntityReader shape.
    Otherwise None (caller should use Zep).
    """
    r = try_read_snapshot(graph_id, for_stale_fallback=False)
    if r.outcome != CacheOutcome.HIT or not r.data:
        return None
    nodes_in = r.data.get("nodes") or []
    edges_in = r.data.get("edges") or []
    nodes_out: list[dict[str, Any]] = []
    for n in nodes_in:
        if not isinstance(n, dict):
            continue
        nodes_out.append(
            {
                "uuid": n.get("uuid", ""),
                "name": n.get("name", "") or "",
                "labels": n.get("labels") or [],
                "summary": n.get("summary", "") or "",
                "attributes": n.get("attributes") or {},
            }
        )
    edges_out: list[dict[str, Any]] = []
    for e in edges_in:
        if not isinstance(e, dict):
            continue
        edges_out.append(
            {
                "uuid": e.get("uuid", ""),
                "name": e.get("name", "") or "",
                "fact": e.get("fact", "") or "",
                "source_node_uuid": e.get("source_node_uuid", ""),
                "target_node_uuid": e.get("target_node_uuid", ""),
                "attributes": e.get("attributes") or {},
            }
        )
    return nodes_out, edges_out


def get_graph_data_cached(
    graph_id: str,
    fetch_from_zep: Callable[[], dict[str, Any]],
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], CacheOutcome, float | None]:
    """
    Single entry for HTTP layer: cache read-through with optional refresh and singleflight.

    Returns (data, outcome, age_seconds_for_hit_or_stale).
    """
    if not Config.GRAPH_SNAPSHOT_CACHE_ENABLED:
        data = fetch_from_zep()
        return data, CacheOutcome.DISABLED, None

    sid = sanitize_graph_id(graph_id)
    if not sid:
        data = fetch_from_zep()
        return data, CacheOutcome.MISS, None

    if refresh:
        ctx = _flight_lock(sid) if Config.GRAPH_SNAPSHOT_SINGLEFLIGHT else nullcontext()
        with ctx:
            data = fetch_from_zep()
            write_snapshot(graph_id, data)
        return data, CacheOutcome.BYPASS, None

    cached = try_read_snapshot(graph_id, for_stale_fallback=False)
    if cached.outcome == CacheOutcome.HIT and cached.data:
        return cached.data, CacheOutcome.HIT, cached.age_seconds

    ctx = _flight_lock(sid) if Config.GRAPH_SNAPSHOT_SINGLEFLIGHT else nullcontext()
    with ctx:
        # Double-check after acquiring flight lock
        cached2 = try_read_snapshot(graph_id, for_stale_fallback=False)
        if cached2.outcome == CacheOutcome.HIT and cached2.data:
            return cached2.data, CacheOutcome.HIT, cached2.age_seconds

        data = fetch_from_zep()
        write_snapshot(graph_id, data)
        return data, CacheOutcome.MISS, None


def try_stale_fallback(graph_id: str) -> CacheReadResult:
    """After Zep failure: return aged snapshot ignoring generation match, within stale max age."""
    return try_read_snapshot(graph_id, for_stale_fallback=True)
